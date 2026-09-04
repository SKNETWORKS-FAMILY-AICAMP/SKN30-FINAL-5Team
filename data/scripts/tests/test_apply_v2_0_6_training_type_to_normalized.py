from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / ("apply_v2_0_6_training_type_to_normalized.py")
    spec = importlib.util.spec_from_file_location("apply_training_type", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = load_module()


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_fills_from_body_focus_and_explicit_strength_exception(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    write_csv(
        catalog,
        [
            {
                "source_identity": "1",
                "stable_code": "mobility",
                "body_focus_code": "MOBILITY",
                "training_type_code": "",
            },
            {
                "source_identity": "2",
                "stable_code": "unresolved",
                "body_focus_code": "",
                "training_type_code": "",
            },
        ],
    )
    review = tmp_path / "review.csv"
    write_csv(
        review,
        [
            {
                "source_identity": "1",
                "body_focus_code": "MOBILITY",
                "training_type_code": "MOBILITY",
            },
            {
                "source_identity": "2",
                "body_focus_code": "ADDUCTORS",
                "training_type_code": "STRENGTH",
            },
        ],
    )
    report = module.apply_training_type(catalog, review, tmp_path / "report.json")
    with catalog.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["training_type_code"] for row in rows] == ["MOBILITY", "STRENGTH"]
    assert report["counts"]["blank_body_focus_filled_as_strength"] == 1


def test_blank_body_focus_without_explicit_strength_fails(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    write_csv(
        catalog,
        [
            {
                "source_identity": "1",
                "stable_code": "unknown",
                "body_focus_code": "",
                "training_type_code": "",
            }
        ],
    )
    review = tmp_path / "review.csv"
    write_csv(
        review,
        [
            {
                "source_identity": "1",
                "body_focus_code": "",
                "training_type_code": "",
            }
        ],
    )
    try:
        module.apply_training_type(catalog, review, tmp_path / "report.json")
    except module.TrainingTypeApplyError as exc:
        assert "no explicit STRENGTH" in str(exc)
    else:
        raise AssertionError("blank body focus without explicit strength must fail")
