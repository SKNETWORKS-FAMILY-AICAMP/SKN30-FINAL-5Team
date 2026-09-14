from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "sync_v2_0_6_gymvisual_muscles.py"
spec = importlib.util.spec_from_file_location("sync_v2_0_6_gymvisual_muscles", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def catalog_row(
    identity: str, primary: str = "OLD", secondary: str = "OLD_SECONDARY"
) -> dict[str, str]:
    return {
        "source_identity": identity,
        "stable_code": f"exercise_{identity}",
        "primary_body_area_codes": primary,
        "secondary_body_area_codes": secondary,
    }


def raw_row(identity: str, primary: str, secondary: list[str]) -> dict[str, object]:
    return {"id": identity, "muscle_group": primary, "secondary_muscles": secondary}


def test_overwrites_existing_values_and_excludes_primary_from_secondary() -> None:
    rows, report = module.apply_sync(
        [catalog_row("0001")],
        {"0001": raw_row("0001", "hamstrings", ["hamstrings", "lower back", "calves"])},
    )

    assert rows[0]["primary_body_area_codes"] == "hamstrings"
    assert rows[0]["secondary_body_area_codes"] == "lower back|calves"
    assert report["updated_record_count"] == 1


def test_normalizes_lats_and_traps_synonyms_before_filtering_secondary() -> None:
    rows, _ = module.apply_sync(
        [catalog_row("0002")],
        {"0002": raw_row("0002", "latissimus dorsi", ["lats", "trapezius", "traps"])},
    )

    assert rows[0]["primary_body_area_codes"] == "lats"
    assert rows[0]["secondary_body_area_codes"] == "traps"
