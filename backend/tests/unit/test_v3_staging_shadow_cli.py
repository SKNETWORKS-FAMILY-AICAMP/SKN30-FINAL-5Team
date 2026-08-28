from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, RegenerationContext
from backend.app.modules.decisions.v3_evaluation_fixtures import (
    V3SyntheticShadowFixture,
    build_synthetic_fixture_bundle,
)
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowExecutionRequest,
    V3ShadowExecutionResult,
)
from backend.app.modules.decisions.v3_staging_evidence import (
    V3StagingShadowRunManifest,
    V3StagingShadowRunStatusCode,
    file_sha256,
)
from backend.scripts import run_v3_staging_shadow as staging_cli

FIXED_TIME = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class CountingRunner:
    def __init__(self, fixtures: tuple[V3SyntheticShadowFixture, ...]) -> None:
        self.results = {
            item.case.scenario_code: self._staging_result(item.stored_result) for item in fixtures
        }
        self.calls = 0

    @staticmethod
    def _staging_result(result: V3ShadowExecutionResult) -> V3ShadowExecutionResult:
        metrics = tuple(
            metric.model_copy(
                update={
                    "provider_code": "OPENAI",
                    "model_version": "approved-model-v1",
                }
            )
            for metric in result.invocation_metrics
        )
        payload = result.model_dump(exclude={"result_hash"})
        payload.update(
            {
                "graph_version": "v3-langgraph-shadow-v2",
                "provider_code": "OPENAI",
                "model_version": "approved-model-v1",
                "invocation_metrics": metrics,
            }
        )
        return V3ShadowExecutionResult.create(**payload)

    async def execute(
        self,
        request: V3ShadowExecutionRequest,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> V3ShadowExecutionResult:
        del constraint_envelope, exercise_pool, regeneration_context
        self.calls += 1
        return self.results[request.case.scenario_code]


class RaisingRunner(CountingRunner):
    async def execute(
        self,
        request: V3ShadowExecutionRequest,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> V3ShadowExecutionResult:
        del request, constraint_envelope, exercise_pool, regeneration_context
        self.calls += 1
        raise RuntimeError("provider-raw-error-and-secret-sentinel")


class TimeoutRunner(CountingRunner):
    async def execute(
        self,
        request: V3ShadowExecutionRequest,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> V3ShadowExecutionResult:
        del request, constraint_envelope, exercise_pool, regeneration_context
        self.calls += 1
        raise TimeoutError("provider-timeout-raw-sentinel")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "staging",
        "llm_agents_enabled": True,
        "llm_agents_provider_code": "OPENAI",
        "llm_agents_model_code": "approved-model-v1",
        "llm_agents_approved_model_codes": ("approved-model-v1",),
        "llm_agents_max_attempts": 2,
        "v3_langgraph_enabled": True,
        "v3_shadow_evaluation_enabled": True,
        "openai_api_key": SecretStr("staging-key-sentinel"),
    }
    values.update(overrides)
    return Settings(**values)


def _args(run_id: str, *, repeat_count: int = 1, allow: bool = True) -> list[str]:
    values = [
        "--run-id",
        run_id,
        "--repeat-count",
        str(repeat_count),
        "--maximum-provider-calls",
        str(320 * repeat_count),
    ]
    if allow:
        values.append("--allow-provider-calls")
    return values


def _manifest(root: Path, run_id: str) -> dict[str, object]:
    return json.loads(
        (root / "outputs" / "v3-shadow" / run_id / "staging_run_manifest.json").read_text(
            encoding="utf-8"
        )
    )


def test_default_execution_is_provider_zero_call(tmp_path: Path) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)

    exit_code = staging_cli.main(
        _args("default-zero-call", allow=False),
        settings=_settings(),
        runner=runner,
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 2
    assert runner.calls == 0
    assert _manifest(tmp_path, "default-zero-call")["failure_code"] == "OPT_IN_REQUIRED"


@pytest.mark.parametrize(
    ("overrides", "failure_code"),
    (
        ({"app_env": "test"}, "ENVIRONMENT_NOT_STAGING"),
        ({"llm_agents_enabled": False}, "LLM_AGENTS_DISABLED"),
        ({"llm_agents_provider_code": "UNCONFIGURED"}, "PROVIDER_NOT_OPENAI"),
        ({"llm_agents_approved_model_codes": ()}, "MODEL_NOT_APPROVED"),
        ({"v3_langgraph_enabled": False}, "LANGGRAPH_DISABLED"),
        ({"v3_shadow_evaluation_enabled": False}, "SHADOW_EVALUATION_DISABLED"),
        ({"openai_api_key": None}, "CREDENTIAL_MISSING"),
    ),
)
def test_each_missing_settings_gate_is_zero_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    failure_code: str,
) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)
    constructor = Mock(side_effect=AssertionError("provider construction is forbidden"))
    monkeypatch.setattr(staging_cli, "build_v3_shadow_runtime", constructor)
    run_id = f"missing-{failure_code.lower()}"

    exit_code = staging_cli.main(
        _args(run_id),
        settings=_settings(**overrides),
        runner=runner,
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 2
    assert runner.calls == 0
    constructor.assert_not_called()
    assert _manifest(tmp_path, run_id)["failure_code"] == failure_code


def test_provider_budget_shortfall_blocks_before_runner_or_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)
    args = _args("budget-shortfall")
    args[args.index("320")] = "319"

    exit_code = staging_cli.main(
        args,
        settings=_settings(),
        runner=runner,
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 2
    assert runner.calls == 0
    assert "PROVIDER_CALL_BUDGET_EXCEEDED" in capsys.readouterr().err
    assert not (tmp_path / "outputs").exists()


def test_request_and_execution_settings_mismatch_is_blocked_before_runner(
    tmp_path: Path,
) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)
    request = staging_cli.build_staging_request(
        bundle=bundle,
        settings=_settings(),
        run_id="request-context-mismatch",
        repeat_count=1,
        maximum_provider_calls=320,
        started_at=FIXED_TIME,
    )
    changed_settings = _settings(
        llm_agents_model_code="approved-model-v2",
        llm_agents_approved_model_codes=("approved-model-v2",),
    )

    manifest, _ = asyncio.run(
        staging_cli.run_staging_shadow(
            request=request,
            bundle=bundle,
            settings=changed_settings,
            workspace_root=tmp_path,
            allow_provider_calls=True,
            run_timeout_seconds=30,
            runner=runner,
            now=lambda: FIXED_TIME,
        )
    )

    assert manifest.failure_code == "RESULT_CONTRACT_MISMATCH"
    assert runner.calls == 0


@pytest.mark.parametrize("repeat_count", (1, 2))
def test_fake_runner_writes_complete_hashed_evidence(
    tmp_path: Path,
    repeat_count: int,
) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)
    run_id = f"fake-success-{repeat_count}"

    exit_code = staging_cli.main(
        _args(run_id, repeat_count=repeat_count),
        settings=_settings(),
        runner=runner,
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 0
    assert runner.calls == 20 * repeat_count
    manifest = _manifest(tmp_path, run_id)
    manifest_path = tmp_path / "outputs" / "v3-shadow" / run_id / "staging_run_manifest.json"
    V3StagingShadowRunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status_code"] == V3StagingShadowRunStatusCode.SUCCEEDED
    assert manifest["actual_result_count"] == 20 * repeat_count
    assert len(manifest["manifest_hash"]) == 64
    files = {item["file_name"]: item for item in manifest["files"]}
    assert set(files) == {
        "results.jsonl",
        "summary.json",
        "summary.md",
        "expert_review_template.jsonl",
        "manifest.json",
    }
    assert files["results.jsonl"]["record_count"] == 20 * repeat_count
    assert all(len(item["sha256"]) == 64 for item in files.values())
    output_directory = tmp_path / "outputs" / "v3-shadow" / run_id
    assert all(
        item["sha256"] == file_sha256((output_directory / file_name).read_bytes())
        for file_name, item in files.items()
    )
    results = (output_directory / "results.jsonl").read_text(encoding="utf-8")
    safety_terminal = next(
        json.loads(line)
        for line in results.splitlines()
        if json.loads(line)["scenario_code"] == "SAFETY_VETO_PRECEDENCE"
    )
    assert safety_terminal["usage"]["provider_call_count"] == 0
    partial_specialist = next(
        json.loads(line)
        for line in results.splitlines()
        if json.loads(line)["scenario_code"] == "PROVIDER_INVALID_STRUCTURED_OUTPUT"
    )
    assert partial_specialist["fallback_used"] is True
    assert all(
        metric["role_code"] != "COORDINATOR" for metric in partial_specialist["invocation_metrics"]
    )


def test_provider_failure_is_sanitized_and_never_marks_partial_success(tmp_path: Path) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = RaisingRunner(bundle.fixtures)

    exit_code = staging_cli.main(
        _args("provider-failure"),
        settings=_settings(),
        runner=runner,
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 2
    manifest_path = (
        tmp_path / "outputs" / "v3-shadow" / "provider-failure" / "staging_run_manifest.json"
    )
    text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(text)
    assert manifest["status_code"] == "FAILED"
    assert manifest["failure_code"] == "PROVIDER_FAILURE"
    assert manifest["actual_result_count"] == 0
    assert "provider-raw-error" not in text
    assert "staging-key-sentinel" not in text


def test_provider_timeout_uses_sanitized_nonzero_failure(tmp_path: Path) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = TimeoutRunner(bundle.fixtures)

    exit_code = staging_cli.main(
        _args("provider-timeout"),
        settings=_settings(),
        runner=runner,
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 2
    text = (
        tmp_path / "outputs" / "v3-shadow" / "provider-timeout" / "staging_run_manifest.json"
    ).read_text(encoding="utf-8")
    assert json.loads(text)["failure_code"] == "RUN_TIMEOUT"
    assert "provider-timeout-raw-sentinel" not in text


def test_provider_construction_failure_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    constructor = Mock(side_effect=RuntimeError("constructor-secret-sentinel"))
    monkeypatch.setattr(staging_cli, "build_v3_shadow_runtime", constructor)

    exit_code = staging_cli.main(
        _args("constructor-failure"),
        settings=_settings(),
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 2
    text = (
        tmp_path / "outputs" / "v3-shadow" / "constructor-failure" / "staging_run_manifest.json"
    ).read_text(encoding="utf-8")
    assert json.loads(text)["failure_code"] == "PROVIDER_FAILURE"
    assert "constructor-secret-sentinel" not in text


def test_invalid_settings_do_not_print_validation_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    constructor = Mock(side_effect=ValueError("settings-secret-sentinel"))
    monkeypatch.setattr(staging_cli, "Settings", constructor)

    exit_code = staging_cli.main(_args("invalid-settings"), workspace_root=tmp_path)

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "INTERNAL_FAILURE" in captured.err
    assert "settings-secret-sentinel" not in captured.err


def test_keyboard_interrupt_writes_sanitized_failure_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupt(coroutine: Coroutine[object, object, object]) -> object:
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(staging_cli.asyncio, "run", interrupt)

    exit_code = staging_cli.main(
        _args("interrupted-run"),
        settings=_settings(),
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 130
    assert "INTERRUPTED" in capsys.readouterr().err
    manifest = _manifest(tmp_path, "interrupted-run")
    assert manifest["failure_code"] == "INTERRUPTED"
    assert manifest["actual_provider_call_count"] is None


def test_partial_result_collection_cannot_be_marked_successful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)

    async def partial_results(*_: object, **__: object) -> tuple[V3ShadowExecutionResult, ...]:
        return (runner.results["HEALTHY_ORIGINAL"],)

    monkeypatch.setattr(staging_cli, "collect_results", partial_results)

    exit_code = staging_cli.main(
        _args("partial-results"),
        settings=_settings(),
        runner=runner,
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 2
    manifest = _manifest(tmp_path, "partial-results")
    assert manifest["status_code"] == "FAILED"
    assert manifest["failure_code"] == "PARTIAL_RESULTS"
    assert manifest["actual_result_count"] == 1


def test_path_traversal_is_rejected_without_creating_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)

    exit_code = staging_cli.main(
        _args("../escaped"),
        settings=_settings(),
        runner=runner,
        workspace_root=tmp_path,
        now=lambda: FIXED_TIME,
    )

    assert exit_code == 2
    assert runner.calls == 0
    assert "OUTPUT_PATH_INVALID" in capsys.readouterr().err
    assert not (tmp_path / "escaped").exists()


def test_existing_run_directory_is_never_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)
    run_id = "one-shot-only"
    assert (
        staging_cli.main(
            _args(run_id, allow=False),
            settings=_settings(),
            runner=runner,
            workspace_root=tmp_path,
            now=lambda: FIXED_TIME,
        )
        == 2
    )
    original = _manifest(tmp_path, run_id)

    assert (
        staging_cli.main(
            _args(run_id),
            settings=_settings(),
            runner=runner,
            workspace_root=tmp_path,
            now=lambda: FIXED_TIME,
        )
        == 2
    )
    assert "RUN_ALREADY_EXISTS" in capsys.readouterr().err
    assert _manifest(tmp_path, run_id) == original
    assert runner.calls == 0


def test_fake_runner_path_never_opens_network_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_network(*_: object, **__: object) -> object:
        raise AssertionError("network access is forbidden in staging unit tests")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)

    assert (
        staging_cli.main(
            _args("no-network"),
            settings=_settings(),
            runner=runner,
            workspace_root=tmp_path,
            now=lambda: FIXED_TIME,
        )
        == 0
    )
    assert runner.calls == 20


def test_staging_script_is_not_imported_by_fastapi_startup() -> None:
    startup_sources = tuple(Path("backend/app").rglob("*.py"))
    assert all(
        "run_v3_staging_shadow" not in source.read_text(encoding="utf-8")
        for source in startup_sources
    )
