#!/usr/bin/env python3
"""Normalize v2.0.6 Korean exercise instructions into numbered polite steps."""

from __future__ import annotations

import argparse
import csv
import json
import re
import string
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
DEFAULT_REPORT = (
    PROJECT_ROOT / "data/reports/v2_0_6_catalog_merge/instruction_style_apply_report.json"
)
FIELD = "instruction_summary_ko"

# These rows were rechecked from the local GIF during this review because the
# previous prose contradicted the displayed start position or movement.
GIF_OVERRIDES = {
    "1368": (
        "1. 서서 한쪽 다리를 바닥에서 가볍게 듭니다 "
        "2. 든 발의 발목을 원을 그리며 돌립니다 "
        "3. 반대쪽도 같은 순서로 수행합니다"
    ),
    "0274": (
        "1. 등을 바닥에 대고 누워 무릎을 굽혀 발을 바닥에 둡니다 "
        "2. 배 주변에 힘을 주고 어깨를 들어 무릎 쪽으로 상체를 굽힙니다 "
        "3. 천천히 시작 자세로 돌아옵니다"
    ),
    "3672": (
        "1. 발을 어깨너비로 벌리고 섭니다 "
        "2. 오른쪽 발을 앞으로 내디뎠다가 제자리로 돌아옵니다 "
        "3. 왼쪽 발도 같은 순서로 앞뒤로 움직입니다"
    ),
    "3666": (
        "1. 인클라인 트레드밀의 경사와 속도를 설정하고 손잡이를 가볍게 잡습니다 "
        "2. 벨트가 움직이면 발을 번갈아 내디뎌 일정한 리듬으로 달립니다 "
        "3. 속도를 낮춘 뒤 발판으로 이동합니다"
    ),
}

MANUAL_OVERRIDES = {
    "0514": (
        "1. 발을 어깨너비로 벌리고 발끝을 약간 바깥쪽으로 향하게 섭니다 "
        "2. 가슴을 펴고 엉덩이를 뒤로 보내며 무릎을 굽혀 편안한 깊이까지 내려갑니다 "
        "3. 발바닥 전체로 바닥을 밀어 시작 자세로 돌아옵니다"
    ),
    "0854": (
        "1. 발을 어깨 너비만큼 벌리고 무게가 있는 물건을 양손에 하나씩 들고 서 있습니다 "
        "2. 팔을 앞으로 곧게 뻗고 손가락이 마주보도록 합니다 "
        "3. 악력을 사용해 물건을 손으로 단단히 쥐었다가 천천히 힘을 풉니다"
    ),
}

PHRASE_REPLACEMENTS = (
    ("느껴보세요", "느낍니다"),
    ("내려놓으세요", "내려놓습니다"),
    ("디디세요", "디딥니다"),
    ("펴세요", "폅니다"),
    ("붙이세요", "붙입니다"),
    ("붙이십시오", "붙입니다"),
    ("붙이습니다", "붙입니다"),
    ("서십시오", "섭니다"),
    ("누으십시오", "눕습니다"),
    ("누우십시오", "눕습니다"),
    ("서세요", "섭니다"),
    ("대십시오", "댑니다"),
    ("느끼십시오", "느낍니다"),
    ("하십시오", "합니다"),
    ("십시오", "습니다"),
    ("하세요", "합니다"),
    ("하시오", "합니다"),
    ("댄다", "댑니다"),
    ("펼친다", "폅니다"),
    ("올린다", "올립니다"),
    ("전완을", "팔뚝을"),
    ("전완에", "팔뚝에"),
    ("대퇴사두근에서 스트레칭을 느낍니다", "허벅지 앞쪽이 늘어나는 느낌이 들도록 합니다"),
    ("햄스트링의 스트레칭을 느낍니다", "허벅지 뒤쪽이 늘어나는 느낌이 들도록 합니다"),
    ("햄스트링 스트레칭을 느낍니다", "허벅지 뒤쪽이 늘어나는 느낌이 들도록 합니다"),
    ("햄스트링에 스트레칭 감각이 들 때까지", "허벅지 뒤쪽이 당기는 느낌이 들 때까지"),
    ("삼두근 스트레칭을 느낍니다", "팔 뒤쪽이 늘어나는 느낌이 들도록 합니다"),
    ("오른쪽 어깨에 스트레칭을 느낍니다", "오른쪽 어깨 뒤쪽이 늘어나는 느낌이 들도록 합니다"),
    ("종아리 근육에서의 스트레칭을 느낍니다", "종아리가 늘어나는 느낌이 들도록 합니다"),
    ("등근육에서 스트레칭을 느낄 때까지", "등이 당기는 느낌이 들 때까지"),
    ("가슴과 어깨 앞부분에서 스트레칭을 느낍니다", "가슴과 어깨 앞쪽이 늘어나는 느낌이 들도록 합니다"),
    ("스트레칭을 유지한 후", "자세를 잠시 유지한 뒤"),
)
STEP_SPLIT_RE = re.compile(r",\s*(?:이어서|그리고|그다음|그 다음|이후|그 후)\s*")
NUMBER_PREFIX_RE = re.compile(r"(?:^|\s)\d+\.\s*")
NUMBERED_STEP_RE = re.compile(r"(?:^|\s)\d+\.\s*(.*?)(?=\s+\d+\.\s*|$)")
ONE_SIDED_RE = re.compile(r"(?:한쪽|오른쪽|왼쪽)")
TWO_SIDED_RE = re.compile(r"(?:반대쪽|양쪽|좌우|교대로)")
PUNCTUATION_TRANSLATION = str.maketrans(
    "", "", string.punctuation + "…·，。！？：；（）「」『』〈〉《》"
)


class InstructionStyleError(ValueError):
    """Raised when the canonical instruction source is malformed."""


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
        raise InstructionStyleError(f"cannot read catalog: {path}") from exc
    required = {"source_identity", "stable_code", FIELD}
    if not required.issubset(fields):
        raise InstructionStyleError("catalog is missing instruction columns")
    if not rows:
        raise InstructionStyleError("catalog is empty")
    identities = [row["source_identity"] for row in rows]
    if not all(identities) or len(identities) != len(set(identities)):
        raise InstructionStyleError("source_identity values must be unique and non-empty")
    return rows, fields


def _polish_sentence(value: str) -> str:
    sentence = value.strip()
    for old, new in PHRASE_REPLACEMENTS:
        sentence = sentence.replace(old, new)
    sentence = sentence.translate(PUNCTUATION_TRANSLATION)
    sentence = re.sub(r"\s+", " ", sentence).strip(" ,")
    return sentence


def _steps(value: str) -> list[str]:
    numbered = [match.group(1) for match in NUMBERED_STEP_RE.finditer(value)]
    if numbered:
        return [_polish_sentence(step) for step in numbered if step.strip(" .,!?")]
    plain = NUMBER_PREFIX_RE.sub(" ", value).strip()
    plain = STEP_SPLIT_RE.sub(". ", plain)
    raw_steps = re.split(r"(?<=[.!?])\s+", plain)
    return [_polish_sentence(step) for step in raw_steps if step.strip(" .,")]


def normalize_instruction(identity: str, value: str) -> str:
    if identity in GIF_OVERRIDES:
        return GIF_OVERRIDES[identity]
    if identity in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[identity]
    steps = _steps(value)
    if not steps:
        raise InstructionStyleError(f"instruction is blank: {identity}")
    combined = " ".join(steps)
    if ONE_SIDED_RE.search(combined) and not TWO_SIDED_RE.search(combined):
        steps.append("반대쪽도 같은 순서로 수행합니다")
    return " ".join(f"{index}. {step}" for index, step in enumerate(steps, 1))


def apply_style(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    changed: list[str] = []
    invalid: list[dict[str, str]] = []
    for row in rows:
        normalized = normalize_instruction(row["source_identity"], row[FIELD])
        if row[FIELD] != normalized:
            row[FIELD] = normalized
            changed.append(row["source_identity"])
        numbered_steps = re.findall(r"(?:^|\s)\d+\.\s*(.*?)(?=\s+\d+\.\s*|$)", normalized)
        if not normalized.startswith("1. ") or not numbered_steps or any(
            not sentence.endswith("니다") for sentence in numbered_steps
        ):
            invalid.append(
                {
                    "source_identity": row["source_identity"],
                    "stable_code": row["stable_code"],
                    "instruction_summary_ko": normalized,
                }
            )
    if invalid:
        raise InstructionStyleError(
            "instruction style is not uniformly polite: "
            + ", ".join(item["source_identity"] for item in invalid[:8])
        )
    return rows, {
        "status": "DRAFT",
        "production_eligible": False,
        "input_record_count": len(rows),
        "updated_record_count": len(changed),
        "instruction_format": "NUMBERED_POLITE_KO_STEPS",
        "gif_overrides": sorted(GIF_OVERRIDES),
        "one_sided_completion_count": sum(
            "반대쪽도 같은 순서로 수행합니다." in row[FIELD] for row in rows
        ),
        "invalid_records": invalid,
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
    rows, report = apply_style(rows)
    if not args.dry_run:
        write_catalog(args.catalog, rows, fields)
        write_report(args.report, report)
    print(json.dumps({"updated_records": report["updated_record_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
