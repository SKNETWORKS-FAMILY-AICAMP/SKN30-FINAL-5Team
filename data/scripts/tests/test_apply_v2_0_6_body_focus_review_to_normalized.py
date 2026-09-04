from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def load_module(name: str, filename: str):
    script = Path(__file__).resolve().parents[1] / filename
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply_module = load_module(
    "apply_body_focus_normalized",
    "apply_v2_0_6_body_focus_review_to_normalized.py",
)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_applies_only_body_focus_and_preserves_other_blanks(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    write_csv(
        catalog,
        [
            {
                "source_identity": "0001",
                "stable_code": "one",
                "body_focus_code": "",
                "training_type_code": "",
            },
            {
                "source_identity": "0002",
                "stable_code": "two",
                "body_focus_code": "BACK",
                "training_type_code": "",
            },
        ],
    )
    review = tmp_path / "review.csv"
    write_csv(
        review,
        [
            {"source_identity": "0001", "body_focus_code": "CORE"},
            {"source_identity": "0002", "body_focus_code": "BACK"},
        ],
    )
    report = apply_module.apply_review(catalog, review, tmp_path / "report.json")
    with catalog.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["body_focus_code"] == "CORE"
    assert rows[0]["training_type_code"] == ""
    assert report["counts"] == {
        "catalog_records": 2,
        "filled": 1,
        "unchanged": 1,
        "conflicts": 0,
        "unresolved_taxonomy_conflict": 0,
    }


def test_conflicting_existing_body_focus_fails_closed(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    write_csv(
        catalog,
        [{"source_identity": "0001", "stable_code": "one", "body_focus_code": "CHEST"}],
    )
    review = tmp_path / "review.csv"
    write_csv(review, [{"source_identity": "0001", "body_focus_code": "BACK"}])
    try:
        apply_module.apply_review(catalog, review, tmp_path / "report.json")
    except apply_module.BodyFocusApplyError as exc:
        assert "conflict" in str(exc)
    else:
        raise AssertionError("conflicting review value must fail closed")
