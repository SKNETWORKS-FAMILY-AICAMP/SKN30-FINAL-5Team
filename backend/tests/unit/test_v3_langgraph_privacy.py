import dataclasses

from backend.app.integrations.langgraph.state import V3GraphInput, V3GraphResult


def test_graph_boundary_has_no_identifier_raw_health_prompt_or_secret_fields() -> None:
    forbidden = {
        "user_id",
        "email",
        "name",
        "date",
        "checkin",
        "wearable",
        "calendar",
        "database",
        "repository",
        "qdrant",
        "api_key",
        "prompt_text",
        "provider_response",
        "exception",
        "chain_of_thought",
    }

    for contract in (V3GraphInput, V3GraphResult):
        names = {field.name.lower() for field in dataclasses.fields(contract)}
        assert not names & forbidden
