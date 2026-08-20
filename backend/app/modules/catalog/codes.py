from enum import StrEnum

CATALOG_CODE_SET_VERSION = "mvp-v1"
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


class ReviewStatusInterpretationCode(StrEnum):
    PIPELINE_COMPATIBILITY_ONLY = "PIPELINE_COMPATIBILITY_ONLY"


class SourceTrackCode(StrEnum):
    WGER = "wger"
    KSPO = "kspo"
    MERGED = "merged"


class TrainingTypeCode(StrEnum):
    STRENGTH = "STRENGTH"
    CARDIO = "CARDIO"
    MOBILITY = "MOBILITY"


class BodyFocusCode(StrEnum):
    UPPER_BODY = "UPPER_BODY"
    LOWER_BODY = "LOWER_BODY"
    CORE = "CORE"
    FULL_BODY = "FULL_BODY"


class MovementPatternCode(StrEnum):
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


class EquipmentCode(StrEnum):
    BODYWEIGHT = "BODYWEIGHT"
    DUMBBELL = "DUMBBELL"
    BARBELL = "BARBELL"
    KETTLEBELL = "KETTLEBELL"
    CABLE_MACHINE = "CABLE_MACHINE"
    MACHINE = "MACHINE"
    HOUSEHOLD_WEIGHT = "HOUSEHOLD_WEIGHT"
    BENCH = "BENCH"
    PULL_UP_BAR = "PULL_UP_BAR"
    RESISTANCE_BAND = "RESISTANCE_BAND"
    MAT = "MAT"
    STABILITY_BALL = "STABILITY_BALL"
    CHAIR = "CHAIR"


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
        BodyFocusCode.CORE: "코어",
        BodyFocusCode.FULL_BODY: "전신",
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
