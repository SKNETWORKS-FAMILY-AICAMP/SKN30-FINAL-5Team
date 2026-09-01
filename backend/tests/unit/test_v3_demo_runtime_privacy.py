from __future__ import annotations

import asyncio
import inspect

from backend.app.integrations.langgraph import demo_runtime
from backend.app.integrations.langgraph.demo_runtime import build_v3_demo_runtime
from backend.app.integrations.langgraph.state import V3GraphInput
from backend.tests.unit.test_v3_demo_runtime import _settings, _successful_model
from backend.tests.unit.test_v3_persistence_service import make_bundle


def test_demo_bundle_exposes_no_identifier_health_prompt_or_provider_error_fields() -> None:
    root_snapshot = make_bundle().root_snapshot
    runtime = build_v3_demo_runtime(
        _settings(),
        execution_profile="DEMO",
        chat_model=_successful_model(root_snapshot),
    )
    assert runtime is not None

    bundle = asyncio.run(runtime.create(root_snapshot=root_snapshot))
    serialized = bundle.model_dump_json().lower()

    for forbidden in (
        "user_id",
        "email",
        "pain_intensity_score",
        "raw_health",
        "raw_wearable",
        "prompt_text",
        "provider_exception",
        "chain_of_thought",
    ):
        assert forbidden not in serialized


def test_demo_runtime_has_no_web_db_or_promotion_evaluator_dependency() -> None:
    source = inspect.getsource(demo_runtime).lower()

    assert "from fastapi" not in source
    assert "import fastapi" not in source
    assert "sqlalchemy" not in source
    assert "v3_promotion" not in source
    assert "repository" not in V3GraphInput.__annotations__
    assert "qdrant" not in V3GraphInput.__annotations__
