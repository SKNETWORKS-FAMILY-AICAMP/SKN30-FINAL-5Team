from enum import StrEnum

CATALOG_CODE_SET_VERSION = "mvp-v1"
CATALOG_V2_CODE_SET_VERSION = "catalog-v2"
CATALOG_MANIFEST_SCHEMA_VERSION = "1.0"
APPROVED_TAXONOMY_REGISTRY_SHA256 = (
    "89e61bba1baf1ccedca94adcb88127f32f529a1b46162ee8392f2cd2ef1372c7"
)


class CatalogVersionStatusCode(StrEnum):
    DRAFT = "DRAFT"


class CatalogReviewStatusCode(StrEnum):
    DOMAIN_APPROVED = "DOMAIN_APPROVED"


class ReviewMethodCode(StrEnum):
    AGENT_ONLY = "AGENT_ONLY"
    DOMAIN_REVIEWER = "DOMAIN_REVIEWER"


class ReviewStatusInterpretationCode(StrEnum):
    PIPELINE_COMPATIBILITY_ONLY = "PIPELINE_COMPATIBILITY_ONLY"


class SourceTrackCode(StrEnum):
    WGER = "wger"
    KSPO = "kspo"
    GYMVISUAL = "gymvisual"
    MERGED = "merged"
    # v2.0.2 derives 75 independent exercises from the reviewed pain-alternative
    # policy. They keep their own track so the provenance stays readable.
    PAIN_ALTERNATIVE_POLICY = "pain_alternative_policy"


class TrainingTypeCode(StrEnum):
    STRENGTH = "STRENGTH"
    CARDIO = "CARDIO"
    MOBILITY = "MOBILITY"


class BodyFocusCode(StrEnum):
    UPPER_BODY = "UPPER_BODY"
    LOWER_BODY = "LOWER_BODY"
    CHEST = "CHEST"
    BACK = "BACK"
    SHOULDERS = "SHOULDERS"
    BICEPS = "BICEPS"
    TRICEPS = "TRICEPS"
    FOREARMS = "FOREARMS"
    GLUTES = "GLUTES"
    QUADRICEPS = "QUADRICEPS"
    HAMSTRINGS = "HAMSTRINGS"
    CALVES = "CALVES"
    CORE = "CORE"
    FULL_BODY = "FULL_BODY"
    CARDIO = "CARDIO"
    MOBILITY = "MOBILITY"


V2_BODY_FOCUS_CODES = frozenset(
    {
        BodyFocusCode.CHEST,
        BodyFocusCode.BACK,
        BodyFocusCode.SHOULDERS,
        BodyFocusCode.BICEPS,
        BodyFocusCode.TRICEPS,
        BodyFocusCode.FOREARMS,
        BodyFocusCode.GLUTES,
        BodyFocusCode.QUADRICEPS,
        BodyFocusCode.HAMSTRINGS,
        BodyFocusCode.CALVES,
        BodyFocusCode.CORE,
        BodyFocusCode.FULL_BODY,
        BodyFocusCode.CARDIO,
        BodyFocusCode.MOBILITY,
    }
)


class MovementPatternCode(StrEnum):
    BALANCE = "BALANCE"
    CYCLING = "CYCLING"
    ELLIPTICAL = "ELLIPTICAL"
    VERTICAL_PULL = "VERTICAL_PULL"
    HORIZONTAL_PULL = "HORIZONTAL_PULL"
    HORIZONTAL_PUSH = "HORIZONTAL_PUSH"
    VERTICAL_PUSH = "VERTICAL_PUSH"
    KNEE_DOMINANT = "KNEE_DOMINANT"
    HIP_DOMINANT = "HIP_DOMINANT"
    KNEE_FLEXION = "KNEE_FLEXION"
    ISOLATION = "ISOLATION"
    GAIT = "GAIT"
    CORE_BRACE = "CORE_BRACE"
    MOBILITY_STRETCH = "MOBILITY_STRETCH"
    JUMP_PLYOMETRIC = "JUMP_PLYOMETRIC"


class EquipmentCode(StrEnum):
    BODYWEIGHT = "BODYWEIGHT"
    DUMBBELL = "DUMBBELL"
    BARBELL = "BARBELL"
    EZ_BAR = "EZ_BAR"
    KETTLEBELL = "KETTLEBELL"
    CABLE_MACHINE = "CABLE_MACHINE"
    MACHINE = "MACHINE"
    HOUSEHOLD_WEIGHT = "HOUSEHOLD_WEIGHT"
    BENCH = "BENCH"
    PULL_UP_BAR = "PULL_UP_BAR"
    RESISTANCE_BAND = "RESISTANCE_BAND"
    STRETCH_STRAP = "STRETCH_STRAP"
    MAT = "MAT"
    STABILITY_BALL = "STABILITY_BALL"
    ELLIPTICAL_MACHINE = "ELLIPTICAL_MACHINE"
    JUMP_ROPE = "JUMP_ROPE"
    FOAM_ROLLER = "FOAM_ROLLER"
    STATIONARY_BIKE = "STATIONARY_BIKE"
    STEP_BOX = "STEP_BOX"
    CHAIR = "CHAIR"


# BENCH and CHAIR remain enum members so historical DB rows and API responses
# can still be decoded. They are deliberately absent from the V2 import set.
V2_EQUIPMENT_CODES = frozenset(
    {
        EquipmentCode.BODYWEIGHT,
        EquipmentCode.DUMBBELL,
        EquipmentCode.BARBELL,
        EquipmentCode.EZ_BAR,
        EquipmentCode.KETTLEBELL,
        EquipmentCode.CABLE_MACHINE,
        EquipmentCode.MACHINE,
        EquipmentCode.HOUSEHOLD_WEIGHT,
        EquipmentCode.PULL_UP_BAR,
        EquipmentCode.RESISTANCE_BAND,
        EquipmentCode.STRETCH_STRAP,
        EquipmentCode.MAT,
        EquipmentCode.STABILITY_BALL,
        EquipmentCode.ELLIPTICAL_MACHINE,
        EquipmentCode.JUMP_ROPE,
        EquipmentCode.FOAM_ROLLER,
        EquipmentCode.STATIONARY_BIKE,
        EquipmentCode.STEP_BOX,
    }
)

V2_EQUIPMENT_CODE_ALIASES: dict[str, EquipmentCode] = {
    "CABLE": EquipmentCode.CABLE_MACHINE,
    "CABLE|MACHINE": EquipmentCode.CABLE_MACHINE,
    "BAND": EquipmentCode.RESISTANCE_BAND,
    "ROPE": EquipmentCode.STRETCH_STRAP,
    "ROLLER": EquipmentCode.FOAM_ROLLER,
    "WEIGHTED": EquipmentCode.HOUSEHOLD_WEIGHT,
}


def normalize_v2_equipment_code(value: str | EquipmentCode) -> EquipmentCode:
    """Return one approved V2 equipment code or fail closed."""

    raw = value.value if isinstance(value, EquipmentCode) else value
    normalized = V2_EQUIPMENT_CODE_ALIASES.get(raw, raw)
    try:
        code = EquipmentCode(normalized)
    except ValueError as exc:
        raise ValueError(f"unsupported V2 equipment code: {raw}") from exc
    if code not in V2_EQUIPMENT_CODES:
        raise ValueError(f"equipment code is not allowed in V2 artifacts: {raw}")
    return code


class LocationCode(StrEnum):
    HOME = "HOME"
    GYM = "GYM"
    OUTDOOR = "OUTDOOR"


class BodyAreaCode(StrEnum):
    NECK = "NECK"
    SHOULDER = "SHOULDER"
    ELBOW = "ELBOW"
    WRIST_HAND = "WRIST_HAND"
    UPPER_BACK = "UPPER_BACK"
    LOWER_BACK = "LOWER_BACK"
    HIP = "HIP"
    KNEE = "KNEE"
    ANKLE_FOOT = "ANKLE_FOOT"
    CHEST = "CHEST"
    ABDOMEN = "ABDOMEN"


class DifficultyCode(StrEnum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"


class GoalCode(StrEnum):
    """Onboarding goals a catalog may carry approved prescriptions for.

    Onboarding has offered all three since the frontend exposed them; the
    catalog only carried GENERAL_FITNESS until v2.0.3, so picking either other
    goal left the approved pool empty and routine creation failed.
    """

    GENERAL_FITNESS = "GENERAL_FITNESS"
    FAT_LOSS = "FAT_LOSS"
    MUSCLE_GAIN = "MUSCLE_GAIN"


class TimingModeCode(StrEnum):
    REPS = "REPS"
    DURATION = "DURATION"


class BodyAreaRoleCode(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class EquipmentRequirementCode(StrEnum):
    REQUIRED = "REQUIRED"


# Only labels approved in data/normalized/exercise_taxonomy_codes.json are frozen here.
# Body-area user labels remain nullable until PM approval; machine codes never double as labels.
APPROVED_DISPLAY_NAMES_KO: dict[type[StrEnum], dict[StrEnum, str]] = {
    TrainingTypeCode: {
        TrainingTypeCode.STRENGTH: "근력",
        TrainingTypeCode.CARDIO: "유산소",
        TrainingTypeCode.MOBILITY: "가동성",
    },
    BodyFocusCode: {
        BodyFocusCode.UPPER_BODY: "상체",
        BodyFocusCode.LOWER_BODY: "하체",
        BodyFocusCode.CHEST: "가슴",
        BodyFocusCode.BACK: "등",
        BodyFocusCode.SHOULDERS: "어깨",
        BodyFocusCode.BICEPS: "이두근",
        BodyFocusCode.TRICEPS: "삼두근",
        BodyFocusCode.FOREARMS: "전완",
        BodyFocusCode.GLUTES: "둔근",
        BodyFocusCode.QUADRICEPS: "대퇴사두근",
        BodyFocusCode.HAMSTRINGS: "햄스트링",
        BodyFocusCode.CALVES: "종아리",
        BodyFocusCode.CORE: "코어",
        BodyFocusCode.FULL_BODY: "전신",
        BodyFocusCode.CARDIO: "유산소",
        BodyFocusCode.MOBILITY: "가동성",
    },
    MovementPatternCode: {
        MovementPatternCode.VERTICAL_PULL: "수직 당기기",
        MovementPatternCode.HORIZONTAL_PULL: "수평 당기기",
        MovementPatternCode.HORIZONTAL_PUSH: "수평 밀기",
        MovementPatternCode.VERTICAL_PUSH: "수직 밀기",
        MovementPatternCode.KNEE_DOMINANT: "무릎 중심 하체",
        MovementPatternCode.HIP_DOMINANT: "엉덩관절 중심 하체",
        MovementPatternCode.KNEE_FLEXION: "무릎 굽힘",
        MovementPatternCode.ISOLATION: "단순 보조",
        MovementPatternCode.GAIT: "걷기·가벼운 러닝",
        MovementPatternCode.CORE_BRACE: "코어",
        MovementPatternCode.MOBILITY_STRETCH: "스트레칭·가동성",
    },
    EquipmentCode: {
        EquipmentCode.BODYWEIGHT: "맨몸",
        EquipmentCode.DUMBBELL: "덤벨",
        EquipmentCode.BARBELL: "바벨",
        EquipmentCode.KETTLEBELL: "케틀벨",
        EquipmentCode.CABLE_MACHINE: "케이블 머신",
        EquipmentCode.MACHINE: "웨이트 머신",
        EquipmentCode.HOUSEHOLD_WEIGHT: "생활 소도구",
        EquipmentCode.BENCH: "벤치",
        EquipmentCode.PULL_UP_BAR: "풀업바",
        EquipmentCode.RESISTANCE_BAND: "밴드",
        EquipmentCode.MAT: "매트",
        EquipmentCode.STABILITY_BALL: "짐볼",
        EquipmentCode.CHAIR: "의자",
    },
    LocationCode: {
        LocationCode.HOME: "홈",
        LocationCode.GYM: "헬스장",
        LocationCode.OUTDOOR: "실외",
    },
}


def approved_display_name(code: StrEnum) -> str | None:
    return APPROVED_DISPLAY_NAMES_KO.get(type(code), {}).get(code)
