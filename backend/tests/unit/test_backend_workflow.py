from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/backend.yml")


def test_backend_workflow_keeps_v1_and_adds_bounded_v2_release_flow() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert "postgresql-release-flow" in jobs
    assert "postgresql-v2-release-flow" in jobs

    v1_steps = {step.get("name") for step in jobs["postgresql-release-flow"]["steps"]}
    assert "V1 PostgreSQL release flow" in v1_steps

    v2 = jobs["postgresql-v2-release-flow"]
    assert v2["timeout-minutes"] == 15
    assert v2["services"]["postgres"]["image"] == "postgres:16"
    assert v2["services"]["postgres"]["env"]["POSTGRES_DB"].endswith("_test")
    assert v2["env"]["DATABASE_URL"].endswith("_test")
    assert v2["env"]["TEST_DATABASE_URL"].endswith("_test")

    step_names = {step.get("name") for step in v2["steps"]}
    assert {
        "V2 migration round trip",
        "V2 bundle static fail-closed checks",
        "V2 PostgreSQL release flow",
    } <= step_names


def test_v2_release_job_uses_no_secret_or_external_service_configuration() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    v2 = workflow["jobs"]["postgresql-v2-release-flow"]
    serialized = yaml.safe_dump(v2)

    assert "secrets." not in serialized
    assert set(v2["services"]) == {"postgres"}
    assert "qdrant" not in serialized.lower()
    assert "openai" not in serialized.lower()
    assert "aws" not in serialized.lower()
