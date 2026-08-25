#!/usr/bin/env python3
"""Process MET review recommendations without auto-approving any row.

The recommendation workbook is treated as reviewer input, not as approval
evidence. Until a human decision is supplied, every recommendation remains
REVIEW_REQUIRED and production_eligible remains false.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from xml.etree import ElementTree as ET


DECISION_FIELDS = [
    "exercise_id",
    "exercise_name",
    "representative_id",
    "family",
    "movement_pattern",
    "equipment",
    "difficulty",
    "current_mapping_met",
    "recommended_met",
    "recommended_intensity",
    "alternative_met_options",
    "compendium_reference",
    "recommendation_basis",
    "recommendation_reason",
    "decision_required",
    "reviewer_decision",
    "reviewer_comment",
]
CHANGE_FIELDS = [
    "exercise_id",
    "existing_status",
    "recommended_met",
    "final_decision",
    "decision_basis",
    "compendium_source",
]
MAPPING_FIELDS = [
    "exercise_id",
    "exercise_name",
    "representative_id",
    "met_value",
    "intensity_level",
    "met_source",
    "source_activity_name",
    "mapping_basis",
    "review_status",
    "production_eligible",
]
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def xlsx_column_number(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha())
    number = 0
    for char in letters.upper():
        number = number * 26 + ord(char) - ord("A") + 1
    return number - 1


def read_xlsx_recommendations(path: Path) -> list[dict[str, str]]:
    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(text.text or "" for text in item.iter(f"{{{NS['a']}}}t"))
                for item in root.findall("a:si", NS)
            ]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relation_map = {item.attrib["Id"]: item.attrib["Target"].lstrip("/") for item in relationships}
        target = None
        for sheet in workbook.find("a:sheets", NS):
            if sheet.attrib["name"] == "MET_Review_Recommendations":
                target = relation_map[sheet.attrib[f"{{{REL_NS}}}id"]]
                break
        if target is None:
            raise ValueError("MET_Review_Recommendations sheet not found")
        root = ET.fromstring(archive.read(target))
        raw_rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", NS):
            cells: dict[int, str] = {}
            for cell in row.findall("a:c", NS):
                value = cell.find("a:v", NS)
                text = "" if value is None else value.text or ""
                if cell.attrib.get("t") == "s" and text:
                    text = shared_strings[int(text)]
                cells[xlsx_column_number(cell.attrib["r"])] = text
            if cells:
                raw_rows.append([cells.get(index, "") for index in range(max(cells) + 1)])
    headers = raw_rows[0]
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in raw_rows[1:]]


def read_recommendations(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".xlsx":
        return read_xlsx_recommendations(path)
    return read_csv(path)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def pending_decision(row: dict[str, str]) -> str:
    return (
        f"{row.get('recommendation_basis', 'NO_CONFIDENT_MAPPING')}: 권장값은 제안값일 뿐 승인 근거가 아님. "
        "공식 Compendium 활동·강도·속도·중량·반복수·휴식 조건을 확인한 뒤 승인하거나 REVIEW_REQUIRED 유지"
    )


def build_decision_required(
    recommendations: list[dict[str, str]], mapping_by_id: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    rows = []
    for recommendation in recommendations:
        if recommendation.get("recommended_intensity") != "REVIEW_REQUIRED":
            continue
        mapping = mapping_by_id[recommendation["exercise_id"]]
        rows.append(
            {
                "exercise_id": recommendation["exercise_id"],
                "exercise_name": recommendation["exercise_name"],
                "representative_id": recommendation["representative_id"],
                "family": recommendation["family"],
                "movement_pattern": recommendation["movement_pattern"],
                "equipment": recommendation["equipment"],
                "difficulty": recommendation["difficulty"],
                "current_mapping_met": mapping.get("met_value", ""),
                "recommended_met": recommendation.get("recommended_met", ""),
                "recommended_intensity": recommendation.get("recommended_intensity", ""),
                "alternative_met_options": recommendation.get("alternative_met_options", ""),
                "compendium_reference": recommendation.get("compendium_reference", mapping.get("met_source", "")),
                "recommendation_basis": recommendation.get("recommendation_basis", ""),
                "recommendation_reason": recommendation.get("recommendation_reason", ""),
                "decision_required": pending_decision(recommendation),
                "reviewer_decision": "",
                "reviewer_comment": "",
            }
        )
    return rows


def build_reviewed_mapping(mapping_rows: list[dict[str, str]], recommendation_ids: set[str]) -> list[dict[str, Any]]:
    reviewed = []
    for source in mapping_rows:
        row = dict(source)
        if row["exercise_id"] in recommendation_ids:
            # No human approval has been provided in this run.
            row["review_status"] = "REVIEW_REQUIRED"
            row["met_value"] = ""
            row["intensity_level"] = "REVIEW_REQUIRED"
        # The source catalog is DRAFT, so this remains fail-closed even for
        # the pre-existing exact-match row.
        row["production_eligible"] = "false"
        reviewed.append(row)
    return reviewed


def build_change_log(
    recommendations: list[dict[str, str]], mapping_by_id: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    rows = []
    for recommendation in recommendations:
        mapping = mapping_by_id[recommendation["exercise_id"]]
        rows.append(
            {
                "exercise_id": recommendation["exercise_id"],
                "existing_status": mapping.get("review_status", ""),
                "recommended_met": recommendation.get("recommended_met", ""),
                "final_decision": "REVIEW_REQUIRED",
                "decision_basis": (
                    "USER_APPROVAL_PENDING; "
                    + recommendation.get("recommendation_basis", "")
                    + "; "
                    + recommendation.get("recommendation_reason", "")
                ),
                "compendium_source": recommendation.get("compendium_reference", mapping.get("met_source", "")),
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recommendations", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    recommendations = read_recommendations(args.recommendations)
    mapping_rows = read_csv(args.mapping)
    mapping_by_id = {row["exercise_id"]: row for row in mapping_rows}
    recommendation_ids = {row["exercise_id"] for row in recommendations}
    review_ids = {row["exercise_id"] for row in mapping_rows if row["review_status"] == "REVIEW_REQUIRED"}
    if len(recommendations) != 207 or recommendation_ids != review_ids:
        raise ValueError("recommendations must contain exactly the 207 REVIEW_REQUIRED mapping IDs")
    decision_rows = build_decision_required(recommendations, mapping_by_id)
    reviewed_mapping = build_reviewed_mapping(mapping_rows, recommendation_ids)
    change_log = build_change_log(recommendations, mapping_by_id)
    write_csv(args.output_dir / "met_review_decision_required.csv", DECISION_FIELDS, decision_rows)
    write_csv(args.output_dir / "exercise_met_mapping_reviewed.csv", MAPPING_FIELDS, reviewed_mapping)
    write_csv(args.output_dir / "met_review_change_log.csv", CHANGE_FIELDS, change_log)


if __name__ == "__main__":
    main()
