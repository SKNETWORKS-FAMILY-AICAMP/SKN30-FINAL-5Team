from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


def load_module(name: str, filename: str):
    script = Path(__file__).resolve().parents[1] / filename
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = load_module(
    "bootstrap_v2_0_6_normalized_catalog", "bootstrap_v2_0_6_normalized_catalog.py"
)
builder = load_module(
    "build_v2_0_6_catalog_from_normalized", "build_v2_0_6_catalog_from_normalized.py"
)


def sample_row(identity: str = "0001") -> dict[str, object]:
    row = {field: None for field in builder.REQUIRED_FIELDS}
    row.update(
        {
            "stable_code": f"exercise_{identity}",
            "name_ko": "검수 운동",
            "name_en": "Reviewed exercise",
            "form_cues_ko": ["첫 단계"],
            "equipment_codes": ["BODYWEIGHT"],
            "location_codes": [],
            "primary_body_area_codes": [],
            "secondary_body_area_codes": [],
            "safety_relevant_body_area_codes": [],
            "source_identity": identity,
            "source_track": "gymvisual",
            "met_review_status_code": "REVIEW_REQUIRED",
            "met_policy_version": "test-policy",
        }
    )
    return row


def write_input(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: bootstrap._csv_value(row.get(field)) for field in fields})


def test_bootstrap_and_builder_round_trip_one_canonical_csv(tmp_path: Path) -> None:
    source_json = tmp_path / "draft.json"
    source_rows = [sample_row()]
    source_json.write_text(json.dumps(source_rows, ensure_ascii=False), encoding="utf-8")
    normalized = tmp_path / "normalized.csv"
    bootstrap.write_catalog(normalized, source_rows)

    records, fields = builder.read_catalog(normalized)
    assert records[0]["stable_code"] == "exercise_0001"
    assert records[0]["form_cues_ko"] == ["첫 단계"]
    assert set(builder.REQUIRED_FIELDS).issubset(fields)


def test_final_builder_reads_only_normalized_catalog_and_is_reproducible(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "normalized.csv"
    write_input(input_path, [sample_row(), sample_row("0002")])
    output_dir = tmp_path / "generated"

    first = builder.build(input_path, output_dir)
    first_bytes = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    second = builder.build(input_path, output_dir)
    second_bytes = {path.name: path.read_bytes() for path in output_dir.iterdir()}

    assert first["status"] == "DRAFT"
    assert second_bytes == first_bytes
    assert second["policy"]["raw_json_read"] is False
    assert second["policy"]["review_csv_read"] is False
    output = json.loads((output_dir / "exercise_catalog_merged_draft.json").read_text())
    assert output[0]["stable_code"] == "exercise_0001"
    assert (
        json.loads((output_dir / "exercise_catalog_merge_report.json").read_text())[
            "production_eligible"
        ]
        is False
    )


def test_final_builder_fails_when_required_column_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    row = sample_row()
    row.pop("safety_relevant_body_area_codes")
    write_input(path, [row])
    try:
        builder.read_catalog(path)
    except builder.NormalizedCatalogError as exc:
        assert "safety_relevant_body_area_codes" in str(exc)
    else:
        raise AssertionError("missing required column must fail closed")


def test_domain_approved_met_rows_require_matching_manifest(tmp_path: Path) -> None:
    input_path = tmp_path / "normalized.csv"
    write_input(
        input_path,
        [sample_row() | {"met_review_status_code": "DOMAIN_APPROVED"}],
    )
    manifest = tmp_path / "met_approval.json"
    manifest.write_text(
        json.dumps(
            {
                "review_status_code": "DOMAIN_APPROVED",
                "approved_record_count": 1,
                "source_catalog_sha256": builder._sha256(input_path),
            }
        ),
        encoding="utf-8",
    )
    records, _ = builder.read_catalog(input_path, manifest)
    assert records[0]["met_review_status_code"] == "DOMAIN_APPROVED"
