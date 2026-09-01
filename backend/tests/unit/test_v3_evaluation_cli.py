import ast
import asyncio
import json
from pathlib import Path

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
from backend.scripts.run_v3_shadow_evaluation import collect_results, main


class CountingRunner:
    def __init__(self, fixtures: tuple[V3SyntheticShadowFixture, ...]) -> None:
        self.results = {item.case.scenario_code: item.stored_result for item in fixtures}
        self.calls = 0

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


def test_stored_result_mode_never_calls_the_runner() -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)

    results = asyncio.run(
        collect_results(
            bundle,
            repeat_count=2,
            runner=runner,
            allow_provider_calls=False,
        )
    )

    assert len(results) == 40
    assert runner.calls == 0


def test_explicit_provider_flag_uses_the_injected_runner() -> None:
    bundle = build_synthetic_fixture_bundle()
    runner = CountingRunner(bundle.fixtures)

    results = asyncio.run(
        collect_results(
            bundle,
            repeat_count=1,
            runner=runner,
            allow_provider_calls=True,
        )
    )

    assert len(results) == 20
    assert runner.calls == 20


def test_cli_dry_run_writes_all_reports_deterministically(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert main(["--output-directory", str(first), "--repeat-count", "2"]) == 0
    assert main(["--output-directory", str(second), "--repeat-count", "2"]) == 0

    expected = {
        "results.jsonl",
        "summary.json",
        "summary.md",
        "expert_review_template.jsonl",
        "manifest.json",
    }
    assert {item.name for item in first.iterdir()} == expected
    assert (first / "results.jsonl").read_text(encoding="utf-8").count("\n") == 40
    assert (first / "expert_review_template.jsonl").read_text(encoding="utf-8").count("\n") == 40
    summary = json.loads((first / "summary.json").read_text(encoding="utf-8"))
    assert summary["total_case_count"] == 40
    assert summary["expert_review_status_code"] == "NOT_REVIEWED"
    assert summary["average_cost_per_decision"] is None
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()


def test_cli_rejects_live_flag_without_an_injected_runner(tmp_path: Path) -> None:
    assert (
        main(
            [
                "--output-directory",
                str(tmp_path),
                "--allow-provider-calls",
            ]
        )
        == 2
    )
    assert not (tmp_path / "results.jsonl").exists()


def test_cli_has_no_live_provider_factory_or_network_client() -> None:
    script = Path("backend/scripts/run_v3_shadow_evaluation.py")
    tree = ast.parse(script.read_text(encoding="utf-8"))
    forbidden_roots = {"httpx", "openai", "requests", "urllib"}
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert imported_roots.isdisjoint(forbidden_roots)
