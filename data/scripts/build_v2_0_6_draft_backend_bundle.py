"""Build the v2.0.6 DRAFT bundle from the immutable v2.0.5 bundle.

This is a conservative media-gated projection.  Only exercises with an exact
representative-ID-to-stable-code media binding are carried into the catalog;
all derived rows are filtered to that catalog.  Alternatives are deliberately
emitted as an empty JSONL artifact, so no DISCOMFORT relationship is created or
consumed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_VERSION = "exercise-catalog-v2.0.5-final"
TARGET_VERSION = "exercise-catalog-v2.0.6-draft"
TARGET_SUFFIX = "v2.0.6-draft"
GENERATOR_VERSION = "v2-0-6-draft-media-gated-packager-1.0.0"
BUNDLE_VERSION = "v2-0-6-draft-backend-bundle-2026-09-03"

DEFAULT_SOURCE = PROJECT_ROOT / f"data/generated/{SOURCE_VERSION}/backend_bundle"
DEFAULT_TARGET = PROJECT_ROOT / f"data/generated/{TARGET_VERSION}/backend_bundle"

SUB_MANIFESTS = (
    "catalog/seed_manifest.json",
    "alternatives/alternatives_manifest.json",
    "media/media_manifest.json",
    "safety/rules_manifest.json",
    "prescriptions/prescription_manifest.json",
)
ALTERNATIVE_CONFLICT_REPORT = "alternatives/input/alternative_projection_conflicts.json"

SOURCE_IDENTITY_RE = re.compile(r"^videos/(?P<identity>[0-9]{4})-[A-Za-z0-9]+\.gif$")
USER_EXPOSED_FIELDS = ("instruction_summary_ko", "form_cues_ko", "name_ko")
UPPER_SNAKE_CASE_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
LOWER_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
STABLE_CODE_RE = re.compile(r"\bstable_code\b", re.IGNORECASE)
BODY_AREA_CODES = {
    "ABDOMEN",
    "ANKLE_FOOT",
    "CHEST",
    "ELBOW",
    "HIP",
    "KNEE",
    "LOWER_BACK",
    "NECK",
    "SHOULDER",
    "UPPER_BACK",
    "WRIST_HAND",
}
BODY_AREA_CODE_RE = re.compile(
    r"\b(?:" + "|".join(sorted(BODY_AREA_CODES, key=len, reverse=True)) + r")\b"
)
VAGUE_CUE_RE = re.compile(
    r"(?:안내된 부위|목표 관절|시작 자세와 기구를 안정적으로 준비한다|"
    r"편안한 시작 자세를 잡고 주변 공간을 확인한다|원본의 .*지시는 사용하지 않고)"
)
CODE_KOREAN_ADJACENCY_RE = re.compile(r"(?:[A-Z][A-Z0-9_]*[가-힣]|[가-힣][A-Z][A-Z0-9_]*)")

RAW_GYMVISUAL_EXERCISES = PROJECT_ROOT / "data/raw/gym_visual/exercises.json"
NORMALIZED_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
EXCLUDED_AUXILIARY_ARTIFACTS = (
    "data/normalized/home_equipment_substitution_guides_v1.jsonl",
    "data/normalized/dumbbell_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/foam_roller_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/resistance_band_bodyweight_variant_candidates_v1.jsonl",
    "data/normalized/stretch_strap_home_suitability_review_v1.jsonl",
    "data/reports/resistance_band_bodyweight_variant_gap_report_v1.json",
    "data/reports/home_equipment_substitution_guides_v1_validation.json",
)
INSTRUCTION_CONTENT_VERSION = "user-natural-language-ko-v2.0.6"
APPROVED_FORM_CUES_REVIEW_STATUS = "APPROVED"
BACKEND_APPROVED_FORM_CUES_REVIEW_STATUS = "DOMAIN_APPROVED"
CONTENT_AUDIT_PATH = "audit/content_naturalization_audit.jsonl"
NORMALIZED_USER_CONTENT_FIELDS = (
    "name_ko",
    "instruction_summary_ko",
    "form_cues_ko",
    "equipment_codes",
    "instruction_content_version",
    "form_cues_review_status",
    "form_cues_source",
)
NORMALIZED_ALWAYS_OVERLAY_FIELDS = (
    "name_en",
    "equipment_codes",
    "location_codes",
    "body_focus_code",
    "primary_movement_pattern_code",
    "timing_mode_code",
    "default_seconds_per_rep",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "form_cues_ko",
    "form_cues_review_status",
    "form_cues_source",
)

# These are the internal posture/support examples documented by the service
# policy.  They are only a migration aid; unknown development tokens fail
# closed instead of being silently exposed or guessed.
DEV_TOKEN_TRANSLATIONS = {
    "REVIEWED_NO_LOAD_POSTURE": "검수된 무부하 자세",
    "REVIEWED_NO_LOAD_SUPPORT": "안정적인 지지",
    "SUPPORTED_SUPINE_NO_TRUNK_BRACING": "누워서 몸통에 힘을 과하게 주지 않는 자세",
    "FULL_BACK_AND_PELVIS_MAT_SUPPORT": "등과 골반을 매트에 편안히 지지하는 것",
    "SUPPORTED_SUPINE_ARMS_RELAXED": "누워서 팔에 힘을 빼는 자세",
    "MAT_AND_LIMB_BLOCK_SUPPORT": "매트와 팔다리로 안정적으로 지지하는 것",
    "SUPPORTED_SUPINE_ARMS_RELAXED_NO_HAND_SUPPORT": "누워서 팔과 손에 힘을 빼는 자세",
    "MAT_AND_LOWER_LIMB_BLOCK_SUPPORT": "매트와 다리로 안정적으로 지지하는 것",
    "SUPPORTED_SUPINE_NEUTRAL_SPINE": "누워서 척추를 편안한 중립 자세로 유지하는 것",
    "SUPPORTED_SUPINE_UPPER_BACK_NEUTRAL": "누워서 등 위쪽을 편안하게 유지하는 자세",
    "MAT_AND_FULL_UPPER_BACK_SUPPORT": "등 위쪽 전체를 매트에 편안히 지지하는 것",
    "SUPPORTED_SUPINE_HEAD_NECK_NEUTRAL": "누워서 머리와 목을 편안하게 유지하는 자세",
    "MAT_AND_HEAD_CUSHION_SUPPORT": "매트와 쿠션으로 머리를 안정적으로 지지하는 것",
    "SUPPORTED_SEATED_HANDS_OPEN_RELAXED": "앉아서 손을 편안하게 펴는 자세",
    "BACKREST_AND_OPEN_PALM_CUSHION_SUPPORT": "등받이와 편안히 편 손으로 안정적으로 지지하는 것",
    "SUPPORTED_SUPINE_PELVIS_NEUTRAL": "누워서 골반을 편안한 중립 자세로 유지하는 것",
    "FULL_BODY_MAT_AND_KNEE_BOLSTER_SUPPORT": (
        "몸 전체를 매트와 무릎 받침으로 안정적으로 지지하는 것"
    ),
    "SUPPORTED_SEATED_KNEES_NEUTRAL_UNWEIGHTED": "앉아서 무릎을 편안하게 두고 힘을 빼는 자세",
    "BACKREST_AND_LOWER_LEG_SUPPORT": "등받이와 종아리로 안정적으로 지지하는 것",
    "SUPPORTED_SEATED_FEET_UNWEIGHTED": "앉아서 발에 힘을 싣지 않고 편안히 두는 자세",
    "LOWER_BACK": "허리",
    "UPPER_BACK": "등 위쪽",
    "WRIST_HAND": "손목과 손",
    "ANKLE_FOOT": "발목과 발",
}

BODY_AREA_LABELS = {
    "ABDOMEN": "배",
    "ANKLE_FOOT": "발목과 발",
    "CHEST": "가슴",
    "ELBOW": "팔꿈치",
    "HIP": "엉덩이 관절",
    "KNEE": "무릎",
    "LOWER_BACK": "허리",
    "NECK": "목",
    "SHOULDER": "어깨",
    "UPPER_BACK": "등 위쪽",
    "WRIST_HAND": "손목과 손",
}

SOURCE_LANGUAGE_REPLACEMENTS = (
    ("고관절 굴곡근", "엉덩이 앞쪽"),
    ("이두근", "팔 앞쪽 근육"),
    ("삼두근", "팔 뒤쪽 근육"),
    ("대퇴사두근", "허벅지 앞쪽"),
    ("햄스트링", "허벅지 뒤쪽"),
    ("둔근", "엉덩이 근육"),
    ("견갑골", "어깨뼈"),
    ("전완근", "팔뚝"),
    ("전완", "팔뚝"),
    ("상완", "위팔"),
    ("코어 근육", "배 주변"),
    ("코어", "배 주변"),
    ("플랫폼", "발판"),
    ("스트레치", "당김"),
    ("스트레칭을 느끼", "당김이 느껴지"),
    ("손아등그립", "손바닥이 아래를 향하도록 잡는 방식"),
    ("오버핸드 그립", "손바닥이 아래를 향하도록 잡는 방식"),
    ("언더핸드 그립", "손바닥이 위를 향하도록 잡는 방식"),
    ("컬링하며", "굽혀 들어 올리며"),
    ("컬링합니다", "굽혀 들어 올립니다"),
    ("컬링", "굽혀 들어 올리는 동작"),
    ("커핑합니다", "굽혀 들어 올립니다"),
    ("스쿠즈합니다", "모아 힘을 줍니다"),
    ("스쿠즈", "모아 힘을 주는 동작"),
    ("발의 공 부분", "발 앞부분"),
    ("발의 공", "발 앞부분"),
    ("발목을 펼쳐 확장합니다", "발목을 펴 뒤꿈치를 들어 올립니다"),
    ("발목을 펼쳐", "발목을 펴"),
    ("복부에 힘을 주어", "배 주변에 가볍게 힘을 주어"),
    ("복부에 힘을 주고", "배 주변에 가볍게 힘을 주고"),
    ("복부에 힘을 줍니다", "배 주변에 가볍게 힘을 줍니다"),
    ("복부를 조여줍니다", "배 주변에 가볍게 힘을 줍니다"),
    ("복부를 바닥에", "배를 바닥에"),
    ("배 주변에 가볍게 힘을 주고", "배 주변에 가볍게 힘을 주고"),
    ("엎질러 잡고", "손바닥이 아래를 향하도록 잡고"),
    ("엎질러 잡습니다", "손바닥이 아래를 향하도록 잡습니다"),
    ("정상에서", "가장 높은 위치에서"),
    ("수축시키고", "힘을 주고"),
    ("수축시키면서", "힘을 주면서"),
    ("완전히 수축되고", "충분히 힘이 들어가고"),
    ("수축된 위치", "힘을 준 위치"),
    ("수축된 상태", "힘이 들어간 상태"),
    ("수축시키며", "힘을 주며"),
    ("수축을 1초간 유지", "힘을 1초간 유지"),
    ("수축시킵니다", "힘을 줍니다"),
    ("어깨 어깨뼈", "어깨뼈"),
    ("척추를 곧게", "등을 곧게"),
    ("척추에 당김", "등에 당김"),
    ("척추를 길게", "등을 길게"),
    ("당김를", "당김을"),
)

# The source contains the same return cue twice for the two-part lateral/front
# raise.  Distinguish the second, front-raise return while preserving the
# source movement order.
SOURCE_STEP_OVERRIDES = {
    "0335": {5: "앞쪽에서 잠시 멈춘 뒤 팔을 천천히 시작 위치로 내립니다."},
}


class BundleBuildError(RuntimeError):
    """Raised when the conservative v2.0.6 bundle cannot be proven valid."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    return len(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _normalized_content_by_stable_code(path: Path) -> dict[str, dict[str, Any]]:
    """Read only canonical user-facing catalog values for this projection.

    The normalized v2.0.6 CSV is the editable source.  Its set of stable codes
    is also authoritative for removals from the older v2.0.5-derived bundle.
    """

    rows = _read_csv(path)
    required = {
        "stable_code",
        "source_identity",
        *NORMALIZED_USER_CONTENT_FIELDS,
        *NORMALIZED_ALWAYS_OVERLAY_FIELDS,
    }
    if not rows or any(not required.issubset(row) for row in rows):
        raise BundleBuildError("normalized v2.0.6 catalog lacks required content fields")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        stable_code = row["stable_code"]
        if not stable_code or stable_code in result:
            raise BundleBuildError("normalized v2.0.6 stable codes must be unique and non-empty")
        result[stable_code] = {
            **{
                field: row[field]
                for field in NORMALIZED_USER_CONTENT_FIELDS
                if field not in {"form_cues_ko", "equipment_codes"}
            },
            "name_en": row["name_en"],
            "body_focus_code": row["body_focus_code"],
            "primary_movement_pattern_code": row["primary_movement_pattern_code"],
            "timing_mode_code": row["timing_mode_code"],
            "default_seconds_per_rep": (
                int(row["default_seconds_per_rep"]) if row["default_seconds_per_rep"] else None
            ),
            "default_work_seconds": (
                int(row["default_work_seconds"]) if row["default_work_seconds"] else None
            ),
            "default_rest_seconds": int(row["default_rest_seconds"]),
            "default_transition_seconds": int(row["default_transition_seconds"]),
            "form_cues_ko": [item for item in row["form_cues_ko"].split("|") if item],
            "equipment_codes": [item for item in row["equipment_codes"].split("|") if item],
            "location_codes": [item for item in row["location_codes"].split("|") if item],
            "source_identity": row["source_identity"],
        }
    return result


def _overlay_normalized_content(
    catalog: list[dict[str, Any]], normalized_by_code: dict[str, dict[str, Any]]
) -> None:
    for record in catalog:
        normalized = normalized_by_code.get(record["stable_code"])
        if normalized is None:
            raise BundleBuildError(
                f"bundle record is missing from normalized v2.0.6 catalog: {record['stable_code']}"
            )
        if normalized["source_identity"] != record["source_identity"]:
            raise BundleBuildError(
                f"normalized source identity does not match bundle: {record['stable_code']}"
            )
        if not normalized["instruction_summary_ko"]:
            raise BundleBuildError(
                f"normalized instruction summary is missing: {record['stable_code']}"
            )
        record["instruction_summary_ko"] = normalized["instruction_summary_ko"]
        for field in NORMALIZED_ALWAYS_OVERLAY_FIELDS:
            value = normalized[field]
            # The normalized CSV records the owner's literal APPROVED decision.
            # The legacy backend bundle has a narrower compatibility enum, so
            # project that value only at the bundle boundary.
            if field == "form_cues_review_status" and value == APPROVED_FORM_CUES_REVIEW_STATUS:
                value = BACKEND_APPROVED_FORM_CUES_REVIEW_STATUS
            record[field] = value
        if normalized["instruction_content_version"] != (
            "gif-reviewed-natural-language-ko-v2.0.6"
        ):
            continue
        if not normalized["form_cues_ko"]:
            raise BundleBuildError(
                f"GIF-reviewed normalized form cues are missing: {record['stable_code']}"
            )
        for field in NORMALIZED_USER_CONTENT_FIELDS:
            value = normalized[field]
            if field == "form_cues_review_status" and value == APPROVED_FORM_CUES_REVIEW_STATUS:
                value = BACKEND_APPROVED_FORM_CUES_REVIEW_STATUS
            record[field] = value


def _write_registry(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("representative_exercise_id", "stable_code"),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _retarget(value: Any) -> Any:
    if isinstance(value, str):
        replacements = (
            (SOURCE_VERSION, TARGET_VERSION),
            ("alternative-set-v2.0.5", f"alternative-set-{TARGET_SUFFIX}"),
            ("safety-rule-set-v2.0.5", f"safety-rule-set-{TARGET_SUFFIX}"),
            ("prescription-set-v2.0.5", f"prescription-set-{TARGET_SUFFIX}"),
            ("media-set-v2.0.5", f"media-set-{TARGET_SUFFIX}"),
            ("alternative-rule-v2.0.5", f"alternative-rule-{TARGET_SUFFIX}"),
            ("v2.0.5", TARGET_SUFFIX),
        )
        for old, new in replacements:
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [_retarget(item) for item in value]
    if isinstance(value, dict):
        return {key: _retarget(item) for key, item in value.items()}
    return value


def _naturalize_form_cue(value: str) -> str:
    """Rewrite a legacy cue without guessing an unknown machine token's meaning."""
    if "KNEE 부위는 체중지지·그립·브레이싱에 사용하지 않는다." in value:
        return "무릎에 체중이 실리지 않도록 편안한 자세를 유지합니다."

    body_area_match = re.fullmatch(
        r"(?P<area>[A-Z_]+) 부위는 체중지지·그립·브레이싱에 사용하지 않는다\.",
        value,
    )
    if body_area_match and body_area_match.group("area") in BODY_AREA_LABELS:
        area = BODY_AREA_LABELS[body_area_match.group("area")]
        return f"{area}에 체중이 실리지 않도록 편안한 자세를 유지합니다."

    # These phrases are source-specific semantic rewrites, not word-for-word
    # substitutions.  They retain the support and posture represented by the
    # approved variant cue while making the action directly usable by a person.
    semantic_rewrites = (
        (
            {"SUPPORTED_SEATED_KNEES_NEUTRAL_UNWEIGHTED", "BACKREST_AND_LOWER_LEG_SUPPORT"},
            "등받이가 있는 안정적인 의자에 앉아 두 발을 바닥에 편하게 둡니다. "
            "운동이 끝날 때까지 등을 등받이에 기대어 몸을 안정적으로 유지합니다.",
        ),
        (
            {"SUPPORTED_SEATED_FEET_UNWEIGHTED", "BACKREST_AND_LOWER_LEG_SUPPORT"},
            "등받이가 있는 안정적인 의자에 앉아 다리와 발을 편안하게 둡니다. "
            "운동이 끝날 때까지 등을 등받이에 기대어 몸을 안정적으로 유지합니다.",
        ),
        (
            {"SUPPORTED_SEATED_HANDS_OPEN_RELAXED", "BACKREST_AND_OPEN_PALM_CUSHION_SUPPORT"},
            "등받이가 있는 안정적인 의자에 앉아 손에 힘을 빼고 편안하게 둡니다. "
            "운동이 끝날 때까지 등을 등받이에 기대어 몸을 안정적으로 유지합니다.",
        ),
        (
            {"SUPPORTED_SUPINE_NEUTRAL_SPINE", "FULL_BACK_AND_PELVIS_MAT_SUPPORT"},
            "바닥에 누워 등과 골반을 매트에 편안히 붙이고 허리를 자연스럽게 둡니다. "
            "운동이 끝날 때까지 몸을 안정적으로 유지합니다.",
        ),
        (
            {"SUPPORTED_SUPINE_PELVIS_NEUTRAL", "FULL_BODY_MAT_AND_KNEE_BOLSTER_SUPPORT"},
            "바닥에 누워 골반과 등을 매트에 편안히 붙이고 무릎 받침으로 다리를 안정시킵니다. "
            "운동이 끝날 때까지 몸을 안정적으로 유지합니다.",
        ),
        (
            {"SUPPORTED_SUPINE_UPPER_BACK_NEUTRAL", "MAT_AND_FULL_UPPER_BACK_SUPPORT"},
            "바닥에 누워 등 위쪽을 매트에 편안히 붙이고 몸을 안정적으로 둡니다. "
            "운동이 끝날 때까지 등을 매트에 편안히 지지합니다.",
        ),
        (
            {"SUPPORTED_SUPINE_HEAD_NECK_NEUTRAL", "MAT_AND_HEAD_CUSHION_SUPPORT"},
            "바닥에 누워 머리를 쿠션에 편안히 올리고 목을 자연스럽게 둡니다. "
            "운동이 끝날 때까지 머리와 몸을 안정적으로 유지합니다.",
        ),
        (
            {"SUPPORTED_SUPINE_ARMS_RELAXED", "MAT_AND_LIMB_BLOCK_SUPPORT"},
            "바닥에 누워 팔에 힘을 빼고 매트에 편안히 둡니다. "
            "운동이 끝날 때까지 몸을 안정적으로 유지합니다.",
        ),
        (
            {"SUPPORTED_SUPINE_ARMS_RELAXED_NO_HAND_SUPPORT", "MAT_AND_LOWER_LIMB_BLOCK_SUPPORT"},
            "바닥에 누워 팔과 손에 힘을 빼고 다리로 몸을 편안히 지지합니다. "
            "운동이 끝날 때까지 몸을 안정적으로 유지합니다.",
        ),
        (
            {"SUPPORTED_SUPINE_NO_TRUNK_BRACING", "FULL_BACK_AND_PELVIS_MAT_SUPPORT"},
            "바닥에 누워 몸통에 힘을 과하게 주지 않고 등과 골반을 매트에 편안히 붙입니다. "
            "운동이 끝날 때까지 몸을 안정적으로 유지합니다.",
        ),
        (
            {"REVIEWED_NO_LOAD_POSTURE", "REVIEWED_NO_LOAD_SUPPORT"},
            "안정적인 자세를 잡고 몸을 편안히 지지합니다. 운동이 끝날 때까지 자세를 유지합니다.",
        ),
    )
    tokens = set(UPPER_SNAKE_CASE_RE.findall(value))
    for required_tokens, replacement in semantic_rewrites:
        if tokens == required_tokens:
            return replacement

    for token in tokens:
        translation = DEV_TOKEN_TRANSLATIONS.get(token)
        if translation is None:
            raise BundleBuildError(f"unknown development token in form cue: {token}")
        value = value.replace(token, translation)
    if UPPER_SNAKE_CASE_RE.search(value) or LOWER_SNAKE_CASE_RE.search(value):
        raise BundleBuildError("form cue still contains a development snake_case token")
    return _polish_source_sentence(value)


def _polish_source_sentence(value: str) -> str:
    for old, new in SOURCE_LANGUAGE_REPLACEMENTS:
        value = value.replace(old, new)
    value = value.replace("선다합니다", "섭니다")
    value = value.replace("서십시오", "섭니다")
    value = value.replace("서세요", "섭니다")
    value = value.replace("대십시오", "댑니다")
    value = value.replace("느끼십시오", "느껴지는 범위까지 움직입니다")
    value = value.replace("하십시오", "합니다")
    value = value.replace("스트레칭이 느껴집니다", "당김이 느껴집니다")
    value = value.replace("스트레칭이 느껴지는", "당김이 느껴지는")
    value = value.replace("스트레칭을 느낍니다", "당김을 느낍니다")
    value = value.replace("스트레칭을 유지합니다", "당김이 느껴지는 자세를 유지합니다")
    value = value.replace("스트레칭을", "당김을")
    value = re.sub(r"\s+", " ", value).strip()
    if not value.endswith((".", "요", "다", "니다")):
        value += "."
    return value


def _read_source_instruction_steps(path: Path) -> dict[str, list[str]]:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BundleBuildError(
            "Gymvisual source exercise instructions are missing or invalid"
        ) from error
    indexed: dict[str, list[str]] = {}
    for row in rows:
        source_identity = str(row.get("id", ""))
        steps = row.get("instruction_steps", {}).get("ko")
        if (
            source_identity
            and isinstance(steps, list)
            and all(isinstance(step, str) for step in steps)
        ):
            indexed[source_identity] = [step.strip() for step in steps if step.strip()]
    return indexed


def _naturalize_catalog(
    records: list[dict[str, Any]],
    source_steps_by_identity: dict[str, list[str]],
) -> list[dict[str, Any]]:
    audit_rows: list[dict[str, Any]] = []
    for record in records:
        source_identity = str(record.get("source_identity", ""))
        source_steps = source_steps_by_identity.get(source_identity)
        if not source_steps:
            raise BundleBuildError(
                f"Korean source instruction steps are missing: {record.get('stable_code')}"
            )
        original_cues = list(record.get("form_cues_ko", []))
        existing_content_version = record.get("instruction_content_version")
        changed_cues = [
            SOURCE_STEP_OVERRIDES.get(source_identity, {}).get(index)
            or _polish_source_sentence(step)
            for index, step in enumerate(source_steps)
        ]
        if any(UPPER_SNAKE_CASE_RE.search(cue) for cue in changed_cues):
            raise BundleBuildError(
                "source instruction contains an unresolved development token: "
                f"{record.get('stable_code')}"
            )
        changed = original_cues != changed_cues
        if changed:
            record["instruction_content_version"] = INSTRUCTION_CONTENT_VERSION
            # Content was rewritten, so it remains pending external/domain review.
            record["form_cues_review_status"] = "REVIEW_REQUIRED"
        for index, changed_sentence in enumerate(changed_cues):
            original_sentence = original_cues[index] if index < len(original_cues) else ""
            audit_rows.append(
                {
                    "stable_code": record["stable_code"],
                    "source_track": record["source_track"],
                    "source_identity": record["source_identity"],
                    "existing_instruction_content_version": existing_content_version,
                    "new_instruction_content_version": record.get("instruction_content_version"),
                    "existing_form_cues_source": record["form_cues_source"],
                    "original_sentence": original_sentence,
                    "changed_sentence": changed_sentence,
                    "reason_code": (
                        "SOURCE_INSTRUCTION_STEPS_NATURAL_LANGUAGE_REWRITE"
                        if changed
                        else "NO_CONTENT_CHANGE"
                    ),
                    "review_required": bool(
                        changed or record.get("form_cues_review_status") == "REVIEW_REQUIRED"
                    ),
                }
            )
        record["form_cues_ko"] = changed_cues
    _validate_user_exposed_fields(records)
    return audit_rows


def _validate_user_exposed_fields(records: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    for record in records:
        stable_code = str(record.get("stable_code", ""))
        summary = record.get("instruction_summary_ko")
        name = record.get("name_ko")
        cues = record.get("form_cues_ko")
        if not isinstance(summary, str) or not summary.strip():
            errors.append(f"{stable_code}: empty instruction_summary_ko")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{stable_code}: empty name_ko")
        if not isinstance(cues, list) or not cues:
            errors.append(f"{stable_code}: empty form_cues_ko")
            continue
        if any(not isinstance(cue, str) or not cue.strip() for cue in cues):
            errors.append(f"{stable_code}: empty cue sentence")
        if len(cues) != len(set(cues)):
            errors.append(f"{stable_code}: duplicate cue sentence")
        if (
            record.get("instruction_content_version") == INSTRUCTION_CONTENT_VERSION
            and record.get("form_cues_review_status")
            not in {
                "REVIEW_REQUIRED",
                APPROVED_FORM_CUES_REVIEW_STATUS,
                BACKEND_APPROVED_FORM_CUES_REVIEW_STATUS,
            }
        ):
            errors.append(f"{stable_code}: rewritten cues must have a valid review status")
        for field in USER_EXPOSED_FIELDS:
            values = record.get(field, []) if field == "form_cues_ko" else [record.get(field, "")]
            for value in values:
                if not isinstance(value, str):
                    continue
                if UPPER_SNAKE_CASE_RE.search(value):
                    errors.append(f"{stable_code}: uppercase snake_case in {field}")
                if LOWER_SNAKE_CASE_RE.search(value):
                    errors.append(f"{stable_code}: lowercase snake_case in {field}")
                if STABLE_CODE_RE.search(value):
                    errors.append(f"{stable_code}: stable_code exposed in {field}")
                if BODY_AREA_CODE_RE.search(value):
                    errors.append(f"{stable_code}: body-area code exposed in {field}")
                if CODE_KOREAN_ADJACENCY_RE.search(value):
                    errors.append(f"{stable_code}: code/Korean adjacency in {field}")
                if VAGUE_CUE_RE.search(value):
                    errors.append(f"{stable_code}: vague user cue in {field}")
    if errors:
        raise BundleBuildError("user-facing catalog validation failed: " + "; ".join(errors[:8]))


def _unique(rows: list[dict[str, str]], key: str, label: str) -> dict[str, dict[str, str]]:
    values = [row.get(key, "") for row in rows]
    if any(not value for value in values) or len(values) != len(set(values)):
        raise BundleBuildError(f"{label} must have unique non-empty {key}")
    return {row[key]: row for row in rows}


def _media_bindings(
    catalog: list[dict[str, Any]],
    registry_rows: list[dict[str, str]],
    media_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    registry = _unique(registry_rows, "representative_exercise_id", "representative registry")
    if len({row["stable_code"] for row in registry_rows}) != len(registry_rows):
        raise BundleBuildError("representative registry must map stable codes one-to-one")
    catalog_by_code = {row["stable_code"]: row for row in catalog}
    media_by_code: dict[str, dict[str, Any]] = {}
    for media in media_rows:
        representative_id = str(media.get("representative_exercise_id", ""))
        registered = registry.get(representative_id)
        if registered is None:
            raise BundleBuildError(
                f"media has no exact representative registry row: {representative_id}"
            )
        stable_code = registered["stable_code"]
        if stable_code in media_by_code:
            raise BundleBuildError(f"stable code has more than one media asset: {stable_code}")
        exercise = catalog_by_code.get(stable_code)
        if exercise is None:
            raise BundleBuildError(f"media maps outside catalog: {stable_code}")
        if exercise.get("source_track") != "gymvisual":
            raise BundleBuildError(f"media binding is not Gymvisual: {stable_code}")
        if media.get("media_status") != "AVAILABLE" or media.get("rights_review_status") != (
            "APPROVED"
        ):
            raise BundleBuildError(f"media is not AVAILABLE + APPROVED: {stable_code}")
        source_key = str(media.get("source_metadata", {}).get("source_object_key", ""))
        match = SOURCE_IDENTITY_RE.fullmatch(source_key)
        if match is None or match.group("identity") != str(exercise.get("source_identity")):
            raise BundleBuildError(
                f"media source identity does not exactly match catalog: {stable_code}"
            )
        media_by_code[stable_code] = _retarget(media)
    return media_by_code


def _refresh_manifest(manifest: dict[str, Any], root: Path, counts: dict[str, int]) -> None:
    summary = manifest.get("summary", {})
    for key, value in counts.items():
        if key in summary:
            summary[key] = value
    for entry in manifest.get("files", []):
        path = root / entry["path"]
        entry["sha256"] = _sha256(path)
        entry["bytes"] = path.stat().st_size
        if path.suffix == ".jsonl":
            entry["records"] = len(_read_jsonl(path))
    for artifact in manifest.get("source", {}).get("input_artifacts", []):
        path = root / artifact["path"]
        if path.is_file():
            artifact["sha256"] = _sha256(path)
            artifact["bytes"] = path.stat().st_size


def _validate_references(
    catalog: list[dict[str, Any]],
    media: list[dict[str, Any]],
    safety: list[dict[str, Any]],
    links: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    alternatives: list[dict[str, Any]],
) -> None:
    codes = {row["stable_code"] for row in catalog}
    if len(codes) != len(catalog):
        raise BundleBuildError("v2.0.6 catalog contains duplicate stable codes")
    if len(media) != len(catalog):
        raise BundleBuildError("catalog and media must have the same record count")
    if any(
        row.get("media_status") != "AVAILABLE" or row.get("rights_review_status") != "APPROVED"
        for row in media
    ):
        raise BundleBuildError("catalog contains a non-approved media asset")
    references = (
        (
            "safety",
            (row["exercise_stable_code"] for row in safety if row.get("exercise_stable_code")),
        ),
        ("goal tag", (row["exercise_stable_code"] for row in links)),
        ("prescription", (row["exercise_stable_code"] for row in profiles)),
    )
    for label, values in references:
        dangling = {value for value in values if value not in codes}
        if dangling:
            raise BundleBuildError(
                f"{label} references excluded stable codes: {sorted(dangling)[:3]}"
            )
    if alternatives:
        raise BundleBuildError("v2.0.6 alternatives must contain zero records")
    _validate_user_exposed_fields(catalog)


def _allowed_media_codes_without_alternative_fallback(
    catalog: list[dict[str, Any]], media_by_code: dict[str, dict[str, Any]]
) -> tuple[set[str], set[str]]:
    """Return media-backed codes while refusing importer alternative fallbacks."""
    catalog_by_code = {row["stable_code"]: row for row in catalog}
    withheld = {
        code
        for code in media_by_code
        if "STRETCH_STRAP" in catalog_by_code[code].get("equipment_codes", [])
    }
    return set(media_by_code) - withheld, withheld


def build(*, source: Path = DEFAULT_SOURCE, target: Path = DEFAULT_TARGET) -> dict[str, Any]:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    catalog_path = target / "catalog/exercises.jsonl"
    registry_path = target / "catalog/input/representative_exercises.csv"
    source_catalog = _read_jsonl(catalog_path)
    source_registry = _read_csv(registry_path)
    source_media = _read_jsonl(target / "media/media_assets.jsonl")
    source_instruction_steps = _read_source_instruction_steps(RAW_GYMVISUAL_EXERCISES)
    normalized_by_code = _normalized_content_by_stable_code(NORMALIZED_CATALOG)
    source_catalog_fields = set(source_catalog[0])
    media_by_code = _media_bindings(source_catalog, source_registry, source_media)

    # Existing V2 importer requires a bodyweight fallback for STRETCH_STRAP
    # exercises.  With an intentionally empty alternatives artifact, those
    # exercises are withheld rather than weakening the importer safety gate.
    allowed_codes, excluded_no_alternative_fallback = (
        _allowed_media_codes_without_alternative_fallback(source_catalog, media_by_code)
    )
    allowed_codes &= set(normalized_by_code)
    if not allowed_codes:
        raise BundleBuildError("media-gated catalog is empty")

    catalog = [_retarget(row) for row in source_catalog if row["stable_code"] in allowed_codes]
    content_audit = _naturalize_catalog(catalog, source_instruction_steps)
    _overlay_normalized_content(catalog, normalized_by_code)
    if any(set(row) != source_catalog_fields for row in catalog):
        raise BundleBuildError("catalog columns must remain identical to v2.0.5")
    catalog.sort(key=lambda row: str(row["stable_code"]))
    _write_jsonl(catalog_path, catalog)

    audit_path = target / CONTENT_AUDIT_PATH
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(audit_path, content_audit)

    registry = [row for row in source_registry if row.get("stable_code") in allowed_codes]
    registry.sort(key=lambda row: (row["representative_exercise_id"], row["stable_code"]))
    _write_registry(registry_path, registry)

    media = [media_by_code[code] for code in sorted(allowed_codes)]
    _write_jsonl(target / "media/media_assets.jsonl", media)

    safety = [
        _retarget(row)
        for row in _read_jsonl(target / "safety/safety_rules.jsonl")
        if row.get("exercise_stable_code") is None
        or row.get("exercise_stable_code") in allowed_codes
    ]
    safety.sort(
        key=lambda row: (
            str(row.get("exercise_stable_code")),
            str(row.get("body_area_code")),
            str(row.get("effect_code")),
        )
    )
    _write_jsonl(target / "safety/safety_rules.jsonl", safety)

    prescription_root = target / "prescriptions"
    links = [
        _retarget(row)
        for row in _read_jsonl(prescription_root / "goal_tag_links.jsonl")
        if row.get("exercise_stable_code") in allowed_codes
    ]
    profiles = [
        _retarget(row)
        for row in _read_jsonl(prescription_root / "prescription_profiles.jsonl")
        if row.get("exercise_stable_code") in allowed_codes
    ]
    links.sort(key=lambda row: (row["exercise_stable_code"], row["goal_code"]))
    profiles.sort(
        key=lambda row: (
            row["exercise_stable_code"],
            row["goal_code"],
            row["experience_level_code"],
            row["phase_code"],
        )
    )
    _write_jsonl(prescription_root / "goal_tag_links.jsonl", links)
    _write_jsonl(prescription_root / "prescription_profiles.jsonl", profiles)

    alternatives_path = target / "alternatives/alternatives.jsonl"
    _write_jsonl(alternatives_path, [])
    alternatives = []
    conflict_report_path = target / ALTERNATIVE_CONFLICT_REPORT
    conflict_report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        conflict_report_path,
        {
            "conflict_count": 0,
            "conflicts": [],
            "importer_record_count": 0,
            "production_eligible": False,
            "projection_status": "DIRECT",
            "runtime_record_count": 0,
            "status": "DRAFT",
        },
    )

    _validate_references(catalog, media, safety, links, profiles, alternatives)

    counts = {
        "exercise_records": len(catalog),
        "rule_records": len(safety),
        "alternative_records": 0,
        "media_asset_records": len(media),
        "goal_tag_records": len(links),
        "prescription_records": len(profiles),
    }
    for relative in SUB_MANIFESTS:
        path = target / relative
        manifest = _retarget(json.loads(path.read_text(encoding="utf-8")))
        manifest["generator_version"] = GENERATOR_VERSION
        if relative == "alternatives/alternatives_manifest.json":
            manifest["source"] = {
                "catalog_version_code": TARGET_VERSION,
                "conflict_report_path": "input/alternative_projection_conflicts.json",
                "input_artifacts": [],
                "projection_conflict_count": 0,
                "projection_status": "DIRECT_EMPTY",
                "reason": "DISCOMFORT alternatives are not created or consumed in this draft",
                "runtime_record_count": 0,
            }
        elif relative == "media/media_manifest.json":
            manifest["source"]["catalog_version_code"] = TARGET_VERSION
            manifest["source"]["matching_rule"] = (
                "exact representative_exercise_id -> stable_code and source_identity"
            )
            manifest["source"]["withheld_reason"] = (
                "no exact approved media binding or no alternatives fallback permitted by importer"
            )
            manifest["source"]["withheld_no_alternative_fallback"] = len(
                excluded_no_alternative_fallback
            )
            manifest["source"]["withheld_records"] = len(source_catalog) - len(media)
        _refresh_manifest(manifest, path.parent, counts)
        _write_json(path, manifest)

    bundle_path = target / "bundle_manifest.json"
    bundle = _retarget(json.loads(bundle_path.read_text(encoding="utf-8")))
    bundle.update(
        {
            "bundle_version": BUNDLE_VERSION,
            "catalog_version_code": TARGET_VERSION,
            "status_code": "DRAFT",
            "production_eligible": False,
            "derived_set_versions": {
                "rule_set_version_code": f"safety-rule-set-{TARGET_SUFFIX}",
                "alternative_set_version_code": f"alternative-set-{TARGET_SUFFIX}",
                "prescription_set_version_code": f"prescription-set-{TARGET_SUFFIX}",
            },
            "summary": {
                "alternative_records": 0,
                "catalog_records": len(catalog),
                "goal_tag_records": len(links),
                "media_asset_records": len(media),
                "prescription_records": len(profiles),
                "safety_rule_records": len(safety),
            },
            "projection": {
                "status": "DIRECT_EMPTY",
                "media_coverage": "EXACT_ALL_CATALOG_RECORDS",
                "runtime_alternative_records": 0,
                "importer_alternative_records": 0,
                "alternative_conflict_count": 0,
                "conflict_report_path": ALTERNATIVE_CONFLICT_REPORT,
            },
            "input_policy": {
                "canonical_catalog_source": "data/normalized/v2_0_6_exercise_catalog.csv",
                "excluded_auxiliary_artifacts": list(EXCLUDED_AUXILIARY_ARTIFACTS),
                "excluded_reason": (
                    "household substitutions, cautions, and replacement exercises are "
                    "not stored in equipment descriptions or alternatives"
                ),
            },
            "content_audit_path": CONTENT_AUDIT_PATH,
            "derived_from": {
                "catalog_version_code": SOURCE_VERSION,
                "bundle_manifest_sha256": _sha256(source / "bundle_manifest.json"),
                "change_summary": (
                    "Media-gated v2.0.6 DRAFT projection from v2.0.5; catalog and all derived "
                    "rows are restricted to exact approved media bindings, alternatives are empty, "
                    "and user-facing Korean instructions are reconciled to source steps."
                ),
                "media_filter": {
                    "source_media_records": len(source_media),
                    "catalog_records_after": len(catalog),
                    "withheld_no_alternative_fallback": sorted(excluded_no_alternative_fallback),
                },
            },
        }
    )
    bundle["importer_paths"] = {
        "alternatives": "alternatives/alternatives_manifest.json",
        "catalog": "catalog/seed_manifest.json",
        "media": "media/media_manifest.json",
        "prescriptions": "prescriptions/prescription_manifest.json",
        "safety": "safety/rules_manifest.json",
    }
    bundle["files"] = []
    for path in sorted(target.rglob("*")):
        if not path.is_file() or path == bundle_path:
            continue
        entry: dict[str, Any] = {
            "path": path.relative_to(target).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        if path.suffix == ".jsonl":
            entry["records"] = len(_read_jsonl(path))
        bundle["files"].append(entry)
    _write_json(bundle_path, bundle)
    return {
        "catalog_version_code": TARGET_VERSION,
        "catalog_records": len(catalog),
        "media_asset_records": len(media),
        "withheld_no_alternative_fallback": len(excluded_no_alternative_fallback),
        "alternative_records": 0,
        "bundle_manifest_sha256": _sha256(bundle_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    print(json.dumps(build(source=args.source, target=args.target), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
