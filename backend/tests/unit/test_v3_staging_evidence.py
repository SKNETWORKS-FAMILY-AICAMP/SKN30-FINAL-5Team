from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.integrations.langgraph.shadow_runtime import V3ShadowRuntimeVersions
from backend.app.modules.decisions.v3_evaluation_fixtures import (
    build_synthetic_fixture_bundle,
)
from backend.app.modules.decisions.v3_staging_evidence import (
    V3ProviderCallBudget,
    V3StagingEvidenceFile,
    V3StagingEvidencePrivacyError,
    V3StagingShadowFailureCode,
    V3StagingShadowRunManifest,
    V3StagingShadowRunStatusCode,
    validate_staging_evidence_privacy,
)
from backend.scripts.run_v3_shadow_evaluation import HARNESS_VERSION
from backend.scripts.run_v3_staging_shadow import build_staging_request

FIXED_TIME = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
CURRENT_CATALOG_VERSION = "exercise-catalog-v2.0.1-final"
STALE_CATALOG_VERSION = "exercise-catalog-v2.0.0-final"
APPROVED_VECTOR_INDEX_VERSION = "v201-openai-text-embedding-3-large-d3072-inputv1-cosine-r1"


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="staging",
        llm_agents_model_code="approved-model-v1",
        llm_agents_max_attempts=2,
    )


def _request():
    return build_staging_request(
        bundle=build_synthetic_fixture_bundle(),
        settings=_settings(),
        run_id="staging-run-001",
        repeat_count=1,
        maximum_provider_calls=320,
        started_at=FIXED_TIME,
    )


def _files() -> tuple[V3StagingEvidenceFile, ...]:
    return tuple(
        V3StagingEvidenceFile(file_name=name, sha256="a" * 64, record_count=20)
        for name in sorted(
            (
                "results.jsonl",
                "summary.json",
                "summary.md",
                "expert_review_template.jsonl",
                "manifest.json",
            )
        )
    )


def test_request_and_budget_have_canonical_hashes_and_versions() -> None:
    request = _request()

    assert request.expected_case_count == 20
    assert request.provider_call_budget.expected_provider_call_upper_bound == 320
    assert request.harness_version == HARNESS_VERSION
    assert request.graph_version == V3ShadowRuntimeVersions().graph_version
    assert request.catalog_version == CURRENT_CATALOG_VERSION
    assert {
        fixture.constraint_envelope.catalog_version
        for fixture in build_synthetic_fixture_bundle().fixtures
    } == {CURRENT_CATALOG_VERSION}
    assert len(request.request_hash) == 64
    assert len(request.provider_call_budget.budget_hash) == 64

    with pytest.raises(ValidationError):
        request.model_copy(update={"request_hash": "0" * 64}).model_validate(
            request.model_dump() | {"request_hash": "0" * 64}
        )


def test_budget_below_worst_case_upper_bound_is_rejected_before_execution() -> None:
    with pytest.raises(ValidationError, match="below the precomputed upper bound"):
        V3ProviderCallBudget.create(
            expected_case_count=20,
            maximum_attempts_per_invocation=2,
            maximum_provider_call_budget=319,
        )


def test_success_manifest_requires_complete_results_and_all_report_files() -> None:
    request = _request()
    manifest = V3StagingShadowRunManifest.create(
        request,
        actual_result_count=20,
        actual_provider_call_count=80,
        finished_at=FIXED_TIME + timedelta(minutes=1),
        status_code=V3StagingShadowRunStatusCode.SUCCEEDED,
        failure_code=None,
        files=_files(),
    )

    assert len(manifest.manifest_hash) == 64
    assert manifest.failure_code is None

    with pytest.raises(ValidationError, match="partial staging results"):
        V3StagingShadowRunManifest.create(
            request,
            actual_result_count=19,
            actual_provider_call_count=76,
            finished_at=FIXED_TIME + timedelta(minutes=1),
            status_code=V3StagingShadowRunStatusCode.SUCCEEDED,
            failure_code=None,
            files=_files(),
        )

    with pytest.raises(ValidationError, match="zero provider calls"):
        V3StagingShadowRunManifest.create(
            request,
            actual_result_count=20,
            actual_provider_call_count=0,
            finished_at=FIXED_TIME + timedelta(minutes=1),
            status_code=V3StagingShadowRunStatusCode.SUCCEEDED,
            failure_code=None,
            files=_files(),
        )


def test_failed_manifest_uses_machine_code_and_never_requires_raw_error() -> None:
    request = _request()
    manifest = V3StagingShadowRunManifest.create(
        request,
        actual_result_count=3,
        actual_provider_call_count=None,
        finished_at=FIXED_TIME + timedelta(seconds=10),
        status_code=V3StagingShadowRunStatusCode.FAILED,
        failure_code=V3StagingShadowFailureCode.PROVIDER_FAILURE,
        files=(),
    )

    assert manifest.failure_code is V3StagingShadowFailureCode.PROVIDER_FAILURE
    assert "error" not in manifest.model_dump()
    assert "exception" not in manifest.model_dump()


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "api_key",
        "prompt",
        "messages",
        "provider_response",
        "provider_error",
        "chain_of_thought",
        "user_id",
        "email",
        "name",
        "raw_health",
        "raw_wearable",
        "vector",
        "embedding",
    ),
)
def test_staging_privacy_allowlist_rejects_forbidden_keys(forbidden_key: str) -> None:
    with pytest.raises(V3StagingEvidencePrivacyError):
        validate_staging_evidence_privacy({forbidden_key: "sentinel"})


def test_staging_timestamps_must_be_timezone_aware() -> None:
    bundle = build_synthetic_fixture_bundle()
    with pytest.raises(ValidationError, match="timezone"):
        build_staging_request(
            bundle=bundle,
            settings=_settings(),
            run_id="staging-run-naive",
            repeat_count=1,
            maximum_provider_calls=320,
            started_at=datetime(2026, 8, 25, 12, 0),
        )


def test_staging_runbook_builds_only_the_current_catalog_contract() -> None:
    runbook = Path("docs/runbooks/v3-staging-demo.md").read_text(encoding="utf-8")

    assert f"--catalog-version {CURRENT_CATALOG_VERSION}" in runbook
    assert f"--catalog-version {STALE_CATALOG_VERSION}" not in runbook
    assert f"--vector-index-version {APPROVED_VECTOR_INDEX_VERSION}" in runbook
    assert "EMBEDDING_MODEL_VERSION=text-embedding-3-large" in runbook
    assert "EMBEDDING_VECTOR_DIMENSION=3072" in runbook
    assert "EMBEDDING_INPUT_SCHEMA_VERSION=exercise-embedding-input-v1" in runbook
    assert "EMBEDDING_DISTANCE_METRIC_CODE=COSINE" in runbook


def test_task_keeps_v200_evidence_historical_and_v201_unexecuted() -> None:
    task = Path("docs/tasks/TASK-AGENT-150.md").read_text(encoding="utf-8")

    assert "Historical evidence — 2026-08-26 v2.0.0 local integration" in task
    assert "v2.0.1 staging preflight" in task
    assert "완료 evidence로 해석하지 않는다" in task
