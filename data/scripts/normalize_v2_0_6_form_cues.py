#!/usr/bin/env python3
"""Make v2.0.6 form cues clear, safety-oriented, and punctuation-free.

GIF-reviewed cues keep their exercise-specific meaning.  Other rows receive
two concise posture cues selected from the movement shown by the normalized
exercise name, instruction, equipment, and training category.  The rules use
only general movement guidance; they do not add medical contraindications.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import string
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/form_cues_apply_report.json"
REQUIRED_FIELDS = {
    "source_identity",
    "stable_code",
    "name_ko",
    "name_en",
    "instruction_summary_ko",
    "equipment_codes",
    "training_type_code",
    "form_cues_ko",
    "form_cues_review_status",
    "form_cues_source",
    "instruction_content_version",
}
GIF_REVIEWED_CONTENT_VERSION = "gif-reviewed-natural-language-ko-v2.0.6"
EDITORIAL_SOURCE = "data/scripts/normalize_v2_0_6_form_cues.py"
FORM_CUES_REVIEW_STATUS = "APPROVED"
PUNCTUATION_TRANSLATION = str.maketrans(
    "", "", string.punctuation + "…·，。！？：；（）「」『』〈〉《》"
)


class FormCueNormalizationError(ValueError):
    """Raised when the canonical form-cue data is incomplete or malformed."""


def read_catalog(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [
                {key: (value or "").strip() for key, value in row.items() if key is not None}
                for row in reader
            ]
    except OSError as exc:
        raise FormCueNormalizationError(f"cannot read catalog: {path}") from exc
    missing = sorted(REQUIRED_FIELDS - set(fields))
    if missing:
        raise FormCueNormalizationError(f"catalog is missing columns: {', '.join(missing)}")
    identities = [row["source_identity"] for row in rows]
    if not rows or not all(identities) or len(identities) != len(set(identities)):
        raise FormCueNormalizationError("source_identity values must be unique and non-empty")
    return rows, fields


def _clean(value: str) -> str:
    value = value.replace("·", " ").replace("/", " ")
    value = value.translate(PUNCTUATION_TRANSLATION)
    return re.sub(r"\s+", " ", value).strip()


def _searchable(row: dict[str, str]) -> str:
    return " ".join(
        (
            row["name_ko"],
            row["name_en"],
            row["stable_code"],
            row["instruction_summary_ko"],
            row["equipment_codes"],
            row["training_type_code"],
        )
    ).lower()


def _category(row: dict[str, str]) -> str:
    searchable = _searchable(row)
    if "foam_roller" in searchable or "폼롤러" in searchable:
        return "foam_roller"
    if "stretch" in searchable or "스트레칭" in searchable or row["training_type_code"] == "MOBILITY":
        return "stretch"
    if any(token in searchable for token in ("squat", "스쿼트", "런지", "lunge", "stepup", "스텝업", "leg press", "레그 프레스")):
        return "lower_body"
    if any(token in searchable for token in ("deadlift", "데드리프트", "good morning", "굿모닝", "hip extension", "힙 익스텐션", "bridge", "브리지")):
        return "hip_hinge"
    if "calf" in searchable or "카프" in searchable or "종아리" in searchable:
        return "calf"
    if any(token in searchable for token in ("crunch", "싯업", "situp", "컬업", "플랭크", "plank", "mountain climber", "마운틴 클라이머")):
        return "core"
    if "pushup" in searchable or "푸시업" in searchable:
        return "floor_push"
    if any(token in searchable for token in ("raise", "레이즈", "shoulder", "숄더", "overhead", "오버헤드", "슈러그", "push press", "푸시 프레스")):
        return "shoulder"
    if any(token in searchable for token in ("push", "푸시", "press", "프레스", "dip", "딥스")):
        return "push"
    if any(token in searchable for token in ("pull", "풀", "row", "로우", "curl", "컬")):
        return "pull"
    if row["training_type_code"] == "CARDIO" or any(
        token in searchable for token in ("run", "달리", "jump", "점프", "treadmill", "트레드밀", "cycle", "사이클", "elliptical", "일립티컬")
    ):
        return "cardio"
    if any(token in searchable for token in ("machine", "머신", "cable", "케이블", "barbell", "바벨", "dumbbell", "덤벨")):
        return "equipment"
    return "general"


def _generated_cues(row: dict[str, str]) -> list[str]:
    category = _category(row)
    cues_by_category = {
        "lower_body": [
            "무릎이 발끝과 같은 방향을 향하게 하고 안쪽으로 무너지지 않게 합니다",
            "발바닥 전체로 바닥을 밀어 몸을 일으킵니다",
        ],
        "hip_hinge": [
            "허리를 둥글게 말지 말고 배 주변에 가볍게 힘을 줍니다",
            "발바닥 전체로 바닥을 누르며 엉덩이 움직임을 만듭니다",
        ],
        "calf": [
            "발끝과 무릎이 같은 방향을 향하게 합니다",
            "내려올 때 발바닥 전체를 바닥에 안정적으로 둡니다",
        ],
        "core": [
            "목을 손으로 당기지 말고 시선은 편안히 위쪽에 둡니다",
            "허리가 과하게 뜨거나 처지지 않게 배 주변에 힘을 줍니다",
        ],
        "floor_push": [
            "손목을 과하게 꺾지 말고 손바닥 전체로 바닥을 지지합니다",
            "허리가 처지거나 과하게 젖혀지지 않게 몸통을 유지합니다",
        ],
        "push": [
            "팔꿈치와 손목을 과하게 꺾지 않게 합니다",
            "몸통을 흔들어 반동을 만들지 말고 천천히 밀고 돌아옵니다",
        ],
        "pull": [
            "어깨가 귀 쪽으로 올라가지 않게 합니다",
            "몸을 흔들어 반동을 만들지 말고 천천히 당깁니다",
        ],
        "shoulder": [
            "허리를 과하게 젖히지 말고 배 주변에 가볍게 힘을 줍니다",
            "팔을 던지듯 움직이지 말고 천천히 올리고 내립니다",
        ],
        "cardio": [
            "발바닥 전체로 지면이나 발판을 부드럽게 디딥니다",
            "무릎이 안쪽으로 무너지지 않게 발끝과 같은 방향으로 움직입니다",
        ],
        "equipment": [
            "운동 전에 시트나 패드 위치와 무게를 몸에 맞게 조절합니다",
            "반동을 쓰지 말고 무게를 천천히 움직입니다",
        ],
        "stretch": [
            "당김이 느껴지는 편안한 범위까지만 움직입니다",
            "반동으로 늘리지 말고 숨을 편안히 쉬며 자세를 유지합니다",
        ],
        "foam_roller": [
            "관절 위를 직접 누르지 말고 근육이 닿는 부위만 천천히 굴립니다",
            "압박이 불편하면 체중을 줄이고 손과 발로 몸을 지지합니다",
        ],
        "general": [
            "목과 허리를 과하게 꺾지 말고 편안한 자세를 유지합니다",
            "반동을 쓰지 말고 천천히 움직입니다",
        ],
    }
    return cues_by_category[category]


def _clean_existing_cues(value: str) -> list[str]:
    return list(dict.fromkeys(_clean(cue) for cue in value.split("|") if _clean(cue)))


def apply_normalization(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    changed: list[str] = []
    categories: Counter[str] = Counter()
    for row in rows:
        gif_reviewed = row["instruction_content_version"] == GIF_REVIEWED_CONTENT_VERSION
        cues = _clean_existing_cues(row["form_cues_ko"]) if gif_reviewed else _generated_cues(row)
        if len(cues) != 2 or any(not cue for cue in cues):
            raise FormCueNormalizationError(f"expected two form cues: {row['source_identity']}")
        normalized = "|".join(cues)
        if row["form_cues_ko"] != normalized:
            row["form_cues_ko"] = normalized
            changed.append(row["source_identity"])
        if not gif_reviewed:
            row["form_cues_source"] = EDITORIAL_SOURCE
            categories[_category(row)] += 1
        row["form_cues_review_status"] = FORM_CUES_REVIEW_STATUS
    return rows, {
        "status": "DRAFT",
        "production_eligible": False,
        "input_record_count": len(rows),
        "updated_record_count": len(changed),
        "gif_reviewed_record_count": sum(
            row["instruction_content_version"] == GIF_REVIEWED_CONTENT_VERSION for row in rows
        ),
        "editorial_safety_record_count": sum(
            row["instruction_content_version"] != GIF_REVIEWED_CONTENT_VERSION for row in rows
        ),
        "editorial_safety_category_counts": dict(sorted(categories.items())),
        "form_cue_format": "TWO_PUNCTUATION_FREE_POLITE_KO_CUES",
        "form_cues_review_status": FORM_CUES_REVIEW_STATUS,
    }


def write_catalog(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows, fields = read_catalog(args.catalog)
    rows, report = apply_normalization(rows)
    if not args.dry_run:
        write_catalog(args.catalog, rows, fields)
        write_report(args.report, report)
    print(json.dumps({"updated_records": report["updated_record_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
