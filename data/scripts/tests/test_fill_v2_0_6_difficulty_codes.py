from __future__ import annotations

import csv

from data.scripts.fill_v2_0_6_difficulty_codes import apply_review


def write_catalog(path, rows):
    fields = ["source_identity", "difficulty_code", "name_en"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_catalog(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_review_fills_all_blank_ids_and_preserves_existing_values(tmp_path) -> None:
    path = tmp_path / "catalog.csv"
    write_catalog(
        path,
        [
            {"source_identity": "0017", "difficulty_code": "", "name_en": "assisted pull-up"},
            {"source_identity": "0140", "difficulty_code": "INTERMEDIATE", "name_en": "pull-up"},
            {"source_identity": "0158", "difficulty_code": "", "name_en": "cable fly"},
            {
                "source_identity": "0872",
                "difficulty_code": "INTERMEDIATE",
                "name_en": "reverse crunch",
            },
        ],
    )

    # The real review must cover the complete 166-row blank scope, so this
    # focused fixture is expanded with the remaining reviewed IDs.
    from data.scripts.fill_v2_0_6_difficulty_codes import DIFFICULTY_BY_SOURCE_ID

    rows = read_catalog(path)
    rows.extend(
        {
            "source_identity": source_id,
            "difficulty_code": "",
            "name_en": source_id,
        }
        for source_id in DIFFICULTY_BY_SOURCE_ID
        if source_id not in {row["source_identity"] for row in rows}
    )
    write_catalog(path, rows)

    updated, preserved = apply_review(path)
    result = {row["source_identity"]: row["difficulty_code"] for row in read_catalog(path)}

    assert updated == len(DIFFICULTY_BY_SOURCE_ID) + 1
    assert preserved == 1
    assert result["0017"] == "BEGINNER"
    assert result["0140"] == "INTERMEDIATE"
    assert result["0158"] == "INTERMEDIATE"
    assert result["0872"] == "BEGINNER"
    assert all(result.values())
