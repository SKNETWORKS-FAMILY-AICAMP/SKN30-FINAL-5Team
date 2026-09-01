"""Collect one-shot V3 staging shadow evidence behind explicit fail-closed gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic_core import to_jsonable_python

from backend.app.core.config import Settings
from backend.app.domain.agents.retrieval import ExercisePoolSnapshot
from backend.app.domain.agents.v3_contracts import ConstraintEnvelope, RegenerationContext
from backend.app.integrations.langgraph.shadow_runtime import (
    V3ShadowRuntime,
    V3ShadowRuntimeVersions,
    build_v3_shadow_runtime,
)
from backend.app.modules.decisions.v3_evaluation_fixtures import (
    V3SyntheticFixtureBundle,
    build_synthetic_fixture_bundle,
)
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowExecutionRequest,
    V3ShadowExecutionResult,
    V3ShadowRunnerPort,
)
from backend.app.modules.decisions.v3_staging_evidence import (
    STAGING_INVOCATION_SLOTS_PER_CASE,
    STAGING_MAX_PROVIDER_CALLS,
    STAGING_MAX_REPEAT_COUNT,
    V3ProviderCallBudget,
    V3StagingEvidenceFile,
    V3StagingShadowFailureCode,
    V3StagingShadowRunManifest,
    V3StagingShadowRunRequest,
    V3StagingShadowRunStatusCode,
    file_sha256,
    validate_staging_evidence_privacy,
)
from backend.scripts.run_v3_shadow_evaluation import (
    HARNESS_VERSION,
    collect_results,
    write_reports,
)

STAGING_MANIFEST_FILE_NAME = "staging_run_manifest.json"
DEFAULT_RUN_TIMEOUT_SECONDS = 1800
MAX_RUN_TIMEOUT_SECONDS = 3600


class _StagingCliError(ValueError):
    def __init__(self, code: V3StagingShadowFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(slots=True)
class _RuntimeRunner:
    runtime: V3ShadowRuntime
    versions: V3ShadowRuntimeVersions
    model_version: str

    async def execute(
        self,
        request: V3ShadowExecutionRequest,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> V3ShadowExecutionResult:
        # Rebind server-owned execution metadata for a current staging run while
        # preserving every immutable synthetic case, envelope, and pool hash.
        staging_request = request.model_copy(
            update={
                "graph_version": self.versions.graph_version,
                "provider_code": "OPENAI",
                "model_version": self.model_version,
                "snapshot_is_fresh": True,
            }
        )
        return await self.runtime.execute(
            staging_request,
            constraint_envelope=constraint_envelope,
            exercise_pool=exercise_pool,
            regeneration_context=regeneration_context,
        )


@dataclass(slots=True)
class _ObservedRunner:
    runner: V3ShadowRunnerPort
    result_count: int = 0
    provider_call_count: int = 0

    async def execute(
        self,
        request: V3ShadowExecutionRequest,
        *,
        constraint_envelope: ConstraintEnvelope,
        exercise_pool: ExercisePoolSnapshot,
        regeneration_context: RegenerationContext | None = None,
    ) -> V3ShadowExecutionResult:
        result = await self.runner.execute(
            request,
            constraint_envelope=constraint_envelope,
            exercise_pool=exercise_pool,
            regeneration_context=regeneration_context,
        )
        self.result_count += 1
        self.provider_call_count += result.usage.provider_call_count
        return result


def staging_gate_failure(
    settings: Settings,
    *,
    allow_provider_calls: bool,
) -> V3StagingShadowFailureCode | None:
    """Return the first missing gate without constructing a provider object."""

    if not allow_provider_calls:
        return V3StagingShadowFailureCode.OPT_IN_REQUIRED
    if settings.app_env != "staging":
        return V3StagingShadowFailureCode.ENVIRONMENT_NOT_STAGING
    if not settings.llm_agents_enabled:
        return V3StagingShadowFailureCode.LLM_AGENTS_DISABLED
    if settings.llm_agents_provider_code != "OPENAI":
        return V3StagingShadowFailureCode.PROVIDER_NOT_OPENAI
    if settings.llm_agents_model_code not in settings.llm_agents_approved_model_codes:
        return V3StagingShadowFailureCode.MODEL_NOT_APPROVED
    if not settings.v3_langgraph_enabled:
        return V3StagingShadowFailureCode.LANGGRAPH_DISABLED
    if not settings.v3_shadow_evaluation_enabled:
        return V3StagingShadowFailureCode.SHADOW_EVALUATION_DISABLED
    if settings.openai_api_key is None:
        return V3StagingShadowFailureCode.CREDENTIAL_MISSING
    return None


def _request_matches_execution_context(
    request: V3StagingShadowRunRequest,
    *,
    bundle: V3SyntheticFixtureBundle,
    settings: Settings,
) -> bool:
    first = bundle.fixtures[0]
    return all(
        (
            request.fixture_version == bundle.fixture_version,
            request.harness_version == HARNESS_VERSION,
            request.graph_version == V3ShadowRuntimeVersions().graph_version,
            request.policy_version == first.constraint_envelope.policy_version,
            request.catalog_version == first.constraint_envelope.catalog_version,
            request.prompt_version == first.request.prompt_version,
            request.provider_code == "OPENAI",
            request.model_version == settings.llm_agents_model_code,
            request.fixture_case_count == len(bundle.fixtures),
            request.expected_case_count == len(bundle.fixtures) * request.repeat_count,
            request.provider_call_budget.maximum_attempts_per_invocation
            == settings.llm_agents_max_attempts,
        )
    )


def build_staging_request(
    *,
    bundle: V3SyntheticFixtureBundle,
    settings: Settings,
    run_id: str,
    repeat_count: int,
    maximum_provider_calls: int,
    started_at: datetime,
) -> V3StagingShadowRunRequest:
    expected_case_count = len(bundle.fixtures) * repeat_count
    budget = V3ProviderCallBudget.create(
        expected_case_count=expected_case_count,
        maximum_attempts_per_invocation=settings.llm_agents_max_attempts,
        maximum_provider_call_budget=maximum_provider_calls,
    )
    first = bundle.fixtures[0]
    versions = V3ShadowRuntimeVersions()
    return V3StagingShadowRunRequest.create(
        run_id=run_id,
        fixture_version=bundle.fixture_version,
        harness_version=HARNESS_VERSION,
        graph_version=versions.graph_version,
        policy_version=first.constraint_envelope.policy_version,
        catalog_version=first.constraint_envelope.catalog_version,
        prompt_version=first.request.prompt_version,
        provider_code="OPENAI",
        model_version=settings.llm_agents_model_code,
        fixture_case_count=len(bundle.fixtures),
        repeat_count=repeat_count,
        expected_case_count=expected_case_count,
        provider_call_budget=budget,
        started_at=started_at,
    )


def resolve_output_directory(workspace_root: Path, *, run_id: str) -> Path:
    output_root = (workspace_root / "outputs" / "v3-shadow").resolve()
    output_directory = (output_root / run_id).resolve()
    if output_root not in output_directory.parents:
        raise _StagingCliError(V3StagingShadowFailureCode.OUTPUT_PATH_INVALID)
    return output_directory


def _record_count(path: Path, *, result_count: int) -> int:
    if path.name in {"results.jsonl", "expert_review_template.jsonl"}:
        return result_count
    return 1


def _evidence_files(
    paths: tuple[Path, ...],
    *,
    result_count: int,
) -> tuple[V3StagingEvidenceFile, ...]:
    return tuple(
        sorted(
            (
                V3StagingEvidenceFile(
                    file_name=path.name,
                    sha256=file_sha256(path.read_bytes()),
                    record_count=_record_count(path, result_count=result_count),
                )
                for path in paths
            ),
            key=lambda item: item.file_name,
        )
    )


def _results_match_request(
    results: tuple[V3ShadowExecutionResult, ...],
    *,
    request: V3StagingShadowRunRequest,
    bundle: V3SyntheticFixtureBundle,
) -> bool:
    expected_cases = Counter(
        (fixture.case.scenario_code, fixture.case.case_hash)
        for _ in range(request.repeat_count)
        for fixture in bundle.fixtures
    )
    actual_cases = Counter((result.scenario_code, result.case_hash) for result in results)
    return expected_cases == actual_cases and all(
        (
            result.graph_version == request.graph_version
            and result.policy_version == request.policy_version
            and result.catalog_version == request.catalog_version
            and result.prompt_version == request.prompt_version
            and result.provider_code == request.provider_code
            and result.model_version == request.model_version
            and all(
                metric.provider_code == request.provider_code
                and metric.model_version == request.model_version
                for metric in result.invocation_metrics
            )
        )
        for result in results
    )


def _write_manifest(output_directory: Path, manifest: V3StagingShadowRunManifest) -> Path:
    validate_staging_evidence_privacy(manifest)
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / STAGING_MANIFEST_FILE_NAME
    path.write_text(
        json.dumps(
            to_jsonable_python(manifest),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _failure_manifest(
    request: V3StagingShadowRunRequest,
    *,
    failure_code: V3StagingShadowFailureCode,
    finished_at: datetime,
    actual_result_count: int = 0,
    actual_provider_call_count: int | None = 0,
) -> V3StagingShadowRunManifest:
    return V3StagingShadowRunManifest.create(
        request,
        actual_result_count=actual_result_count,
        actual_provider_call_count=actual_provider_call_count,
        finished_at=finished_at,
        status_code=V3StagingShadowRunStatusCode.FAILED,
        failure_code=failure_code,
        files=(),
    )


async def run_staging_shadow(
    *,
    request: V3StagingShadowRunRequest,
    bundle: V3SyntheticFixtureBundle,
    settings: Settings,
    workspace_root: Path,
    allow_provider_calls: bool,
    run_timeout_seconds: int,
    runner: V3ShadowRunnerPort | None = None,
    now: Callable[[], datetime] | None = None,
) -> tuple[V3StagingShadowRunManifest, Path]:
    clock = now or (lambda: datetime.now(UTC))
    output_directory = resolve_output_directory(workspace_root, run_id=request.run_id)
    if output_directory.exists():
        raise _StagingCliError(V3StagingShadowFailureCode.RUN_ALREADY_EXISTS)
    gate_failure = staging_gate_failure(settings, allow_provider_calls=allow_provider_calls)
    if gate_failure is not None:
        manifest = _failure_manifest(request, failure_code=gate_failure, finished_at=clock())
        return manifest, _write_manifest(output_directory, manifest)
    if not _request_matches_execution_context(request, bundle=bundle, settings=settings):
        manifest = _failure_manifest(
            request,
            failure_code=V3StagingShadowFailureCode.RESULT_CONTRACT_MISMATCH,
            finished_at=clock(),
        )
        return manifest, _write_manifest(output_directory, manifest)
    if run_timeout_seconds <= 0 or run_timeout_seconds > MAX_RUN_TIMEOUT_SECONDS:
        manifest = _failure_manifest(
            request,
            failure_code=V3StagingShadowFailureCode.RUN_TIMEOUT,
            finished_at=clock(),
        )
        return manifest, _write_manifest(output_directory, manifest)

    active_runner: V3ShadowRunnerPort
    if runner is None:
        try:
            versions = V3ShadowRuntimeVersions()
            active_runner = _RuntimeRunner(
                runtime=build_v3_shadow_runtime(
                    settings, allow_provider_calls=True, versions=versions
                ),
                versions=versions,
                model_version=settings.llm_agents_model_code,
            )
        except Exception:
            manifest = _failure_manifest(
                request,
                failure_code=V3StagingShadowFailureCode.PROVIDER_FAILURE,
                finished_at=clock(),
                actual_provider_call_count=0,
            )
            return manifest, _write_manifest(output_directory, manifest)
    else:
        active_runner = runner
    observed = _ObservedRunner(active_runner)
    try:
        results = await asyncio.wait_for(
            collect_results(
                bundle,
                repeat_count=request.repeat_count,
                runner=observed,
                allow_provider_calls=True,
            ),
            timeout=run_timeout_seconds,
        )
    except TimeoutError:
        manifest = _failure_manifest(
            request,
            failure_code=V3StagingShadowFailureCode.RUN_TIMEOUT,
            finished_at=clock(),
            actual_result_count=observed.result_count,
            actual_provider_call_count=None,
        )
        return manifest, _write_manifest(output_directory, manifest)
    except Exception:
        manifest = _failure_manifest(
            request,
            failure_code=V3StagingShadowFailureCode.PROVIDER_FAILURE,
            finished_at=clock(),
            actual_result_count=observed.result_count,
            actual_provider_call_count=None,
        )
        return manifest, _write_manifest(output_directory, manifest)

    if len(results) != request.expected_case_count:
        manifest = _failure_manifest(
            request,
            failure_code=V3StagingShadowFailureCode.PARTIAL_RESULTS,
            finished_at=clock(),
            actual_result_count=len(results),
            actual_provider_call_count=observed.provider_call_count,
        )
        return manifest, _write_manifest(output_directory, manifest)
    if not _results_match_request(results, request=request, bundle=bundle):
        manifest = _failure_manifest(
            request,
            failure_code=V3StagingShadowFailureCode.RESULT_CONTRACT_MISMATCH,
            finished_at=clock(),
            actual_result_count=len(results),
            actual_provider_call_count=observed.provider_call_count,
        )
        return manifest, _write_manifest(output_directory, manifest)
    if observed.provider_call_count > request.provider_call_budget.maximum_provider_call_budget:
        manifest = _failure_manifest(
            request,
            failure_code=V3StagingShadowFailureCode.PROVIDER_CALL_BUDGET_EXCEEDED,
            finished_at=clock(),
            actual_result_count=len(results),
            actual_provider_call_count=None,
        )
        return manifest, _write_manifest(output_directory, manifest)

    try:
        report_paths = write_reports(
            output_directory,
            bundle=bundle,
            results=results,
            repeat_count=request.repeat_count,
            provider_calls_allowed=True,
        )
        files = _evidence_files(report_paths, result_count=len(results))
        manifest = V3StagingShadowRunManifest.create(
            request,
            actual_result_count=len(results),
            actual_provider_call_count=observed.provider_call_count,
            finished_at=clock(),
            status_code=V3StagingShadowRunStatusCode.SUCCEEDED,
            failure_code=None,
            files=files,
        )
        return manifest, _write_manifest(output_directory, manifest)
    except Exception:
        manifest = _failure_manifest(
            request,
            failure_code=V3StagingShadowFailureCode.REPORT_WRITE_FAILED,
            finished_at=clock(),
            actual_result_count=len(results),
            actual_provider_call_count=observed.provider_call_count,
        )
        return manifest, _write_manifest(output_directory, manifest)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repeat-count", required=True, type=int)
    parser.add_argument("--maximum-provider-calls", required=True, type=int)
    parser.add_argument("--run-timeout-seconds", type=int, default=DEFAULT_RUN_TIMEOUT_SECONDS)
    parser.add_argument("--allow-provider-calls", action="store_true")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    runner: V3ShadowRunnerPort | None = None,
    workspace_root: Path | None = None,
    now: Callable[[], datetime] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    clock = now or (lambda: datetime.now(UTC))
    try:
        current_settings = settings or Settings(_env_file=None)  # type: ignore[call-arg]
    except Exception:
        print(V3StagingShadowFailureCode.INTERNAL_FAILURE.value, file=sys.stderr)
        return 2
    bundle = build_synthetic_fixture_bundle()
    if not 0 < args.repeat_count <= STAGING_MAX_REPEAT_COUNT:
        print(V3StagingShadowFailureCode.OUTPUT_PATH_INVALID.value, file=sys.stderr)
        return 2
    expected_provider_calls = (
        len(bundle.fixtures)
        * args.repeat_count
        * STAGING_INVOCATION_SLOTS_PER_CASE
        * current_settings.llm_agents_max_attempts
    )
    if not (expected_provider_calls <= args.maximum_provider_calls <= STAGING_MAX_PROVIDER_CALLS):
        print(
            V3StagingShadowFailureCode.PROVIDER_CALL_BUDGET_EXCEEDED.value,
            file=sys.stderr,
        )
        return 2
    request: V3StagingShadowRunRequest | None = None
    try:
        request = build_staging_request(
            bundle=bundle,
            settings=current_settings,
            run_id=args.run_id,
            repeat_count=args.repeat_count,
            maximum_provider_calls=args.maximum_provider_calls,
            started_at=clock(),
        )
        manifest, manifest_path = asyncio.run(
            run_staging_shadow(
                request=request,
                bundle=bundle,
                settings=current_settings,
                workspace_root=workspace_root or Path.cwd(),
                allow_provider_calls=args.allow_provider_calls,
                run_timeout_seconds=args.run_timeout_seconds,
                runner=runner,
                now=clock,
            )
        )
    except _StagingCliError as exc:
        print(exc.code.value, file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print(V3StagingShadowFailureCode.OUTPUT_PATH_INVALID.value, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        if request is not None:
            try:
                output_directory = resolve_output_directory(
                    workspace_root or Path.cwd(), run_id=request.run_id
                )
                manifest = _failure_manifest(
                    request,
                    failure_code=V3StagingShadowFailureCode.INTERRUPTED,
                    finished_at=clock(),
                    actual_provider_call_count=None,
                )
                _write_manifest(output_directory, manifest)
            except (OSError, ValueError):
                pass
        print(V3StagingShadowFailureCode.INTERRUPTED.value, file=sys.stderr)
        return 130
    print(manifest_path)
    if manifest.status_code is V3StagingShadowRunStatusCode.SUCCEEDED:
        return 0
    print(
        manifest.failure_code.value if manifest.failure_code else "INTERNAL_FAILURE",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())


__all__ = [
    "DEFAULT_RUN_TIMEOUT_SECONDS",
    "MAX_RUN_TIMEOUT_SECONDS",
    "STAGING_MANIFEST_FILE_NAME",
    "build_staging_request",
    "main",
    "resolve_output_directory",
    "run_staging_shadow",
    "staging_gate_failure",
]
