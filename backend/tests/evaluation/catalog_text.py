"""Korean names and instruction summaries for the evaluation catalog.

`catalog.py` carries the structured record every plan is built from.  Retrieval
needs something else: the reviewed *text* an embedding actually reads
(`canonical_embedding_document` in `qdrant/index_builder.py` puts `name_ko`,
`name_en` and `instruction_summary_ko` into the embedded document).

Splitting the text out keeps the planning fixtures unchanged while giving PHASE 3
real language to score against.  A hash-based fake embedding cannot tell
"덤벨 로우" from "종아리 스트레칭", so without this the retrieval numbers would
measure the harness rather than the retriever.

The summaries below are ordinary movement descriptions written for this fixture.
They are not reviewed catalog content and carry no medical claim.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID, uuid5

from backend.app.db.repositories.vector_index import IndexableExerciseRecord
from backend.tests.evaluation import catalog

CATALOG_VERSION_ID: Final = uuid5(UUID("6f1d5f2e-0f4c-4a2b-9c3d-8e7a1b2c3d4e"), "eval-catalog-v1")
CATALOG_MANIFEST_HASH: Final = "e" * 64
INSTRUCTION_CONTENT_VERSION: Final = "eval-instruction-v1"


class ExerciseText:
    """Reviewed-style text for one evaluation exercise."""

    __slots__ = ("name_ko", "name_en", "instruction_summary_ko")

    def __init__(self, name_ko: str, name_en: str, instruction_summary_ko: str) -> None:
        self.name_ko = name_ko
        self.name_en = name_en
        self.instruction_summary_ko = instruction_summary_ko


TEXT: Final[dict[str, ExerciseText]] = {
    # --- WARMUP ---------------------------------------------------------
    "WARMUP_ARM_CIRCLE": ExerciseText(
        "팔 돌리기",
        "Arm Circle",
        "선 자세에서 양팔을 크게 돌려 어깨 관절의 가동 범위를 넓히는 상체 준비 운동이다.",
    ),
    "WARMUP_HIP_OPENER": ExerciseText(
        "고관절 열기",
        "Hip Opener",
        "무릎을 들어 바깥으로 원을 그리며 고관절 주변을 풀어주는 하체 준비 운동이다.",
    ),
    "WARMUP_MARCH_IN_PLACE": ExerciseText(
        "제자리 걷기",
        "March In Place",
        "제자리에서 무릎을 번갈아 들어올려 심박수를 서서히 올리는 전신 준비 운동이다.",
    ),
    "WARMUP_SHOULDER_ROLL": ExerciseText(
        "어깨 돌리기",
        "Shoulder Roll",
        "어깨를 앞뒤로 크게 돌려 승모근과 어깨 주변 긴장을 푸는 상체 준비 운동이다.",
    ),
    # --- MAIN -----------------------------------------------------------
    "SQUAT_BODYWEIGHT": ExerciseText(
        "맨몸 스쿼트",
        "Bodyweight Squat",
        (
            "발을 어깨너비로 벌리고 앉았다 일어서며 허벅지와 엉덩이를 단련하는 "
            "하체 운동이다. 무릎에 부하가 실린다."
        ),
    ),
    "LUNGE_FORWARD": ExerciseText(
        "전방 런지",
        "Forward Lunge",
        (
            "한 발을 앞으로 내딛어 무릎을 굽혔다 돌아오며 하체를 단련하는 "
            "운동이다. 무릎에 부하가 실린다."
        ),
    ),
    "WALL_SIT": ExerciseText(
        "벽 스쿼트 버티기",
        "Wall Sit",
        (
            "벽에 등을 대고 앉은 자세를 유지하며 허벅지를 버티게 하는 하체 등척성 "
            "운동이다. 무릎에 부하가 실린다."
        ),
    ),
    "PUSHUP_KNEE": ExerciseText(
        "무릎 푸시업",
        "Knee Push-up",
        ("무릎을 바닥에 대고 팔을 굽혀 내려갔다 밀어 올리며 가슴과 삼두를 단련하는 상체 운동이다."),
    ),
    "GLUTE_BRIDGE": ExerciseText(
        "글루트 브릿지",
        "Glute Bridge",
        "누워서 엉덩이를 들어 올려 둔근과 햄스트링을 단련하는 하체 운동이다. 무릎 부하가 적다.",
    ),
    "PLANK_FOREARM": ExerciseText(
        "팔꿈치 플랭크",
        "Forearm Plank",
        "팔꿈치로 몸을 지탱하며 자세를 유지해 복부와 코어를 단련하는 운동이다.",
    ),
    "DEAD_BUG": ExerciseText(
        "데드버그",
        "Dead Bug",
        "누워서 팔다리를 번갈아 뻗으며 허리를 안정시키고 코어를 단련하는 운동이다.",
    ),
    "ROW_DUMBBELL": ExerciseText(
        "덤벨 로우",
        "Dumbbell Row",
        "덤벨을 잡고 상체를 숙여 당겨 올리며 등 근육을 단련하는 상체 운동이다. 덤벨이 필요하다.",
    ),
    "OVERHEAD_PRESS_DUMBBELL": ExerciseText(
        "덤벨 오버헤드 프레스",
        "Dumbbell Overhead Press",
        (
            "덤벨을 어깨 높이에서 머리 위로 밀어 올리며 어깨를 단련하는 상체 "
            "운동이다. 덤벨이 필요하다."
        ),
    ),
    "LEG_PRESS_MACHINE": ExerciseText(
        "레그 프레스 머신",
        "Leg Press Machine",
        "헬스장 머신에 앉아 발판을 밀어내며 하체를 단련하는 운동이다. 머신이 필요하다.",
    ),
    # --- COOLDOWN -------------------------------------------------------
    "COOLDOWN_HAMSTRING_STRETCH": ExerciseText(
        "햄스트링 스트레칭",
        "Hamstring Stretch",
        "다리를 뻗고 상체를 숙여 허벅지 뒤쪽을 늘여주는 마무리 스트레칭이다.",
    ),
    "COOLDOWN_CHEST_STRETCH": ExerciseText(
        "가슴 스트레칭",
        "Chest Stretch",
        "양팔을 뒤로 열어 가슴 앞쪽을 늘여주는 상체 마무리 스트레칭이다.",
    ),
    "COOLDOWN_CHILD_POSE": ExerciseText(
        "아기 자세",
        "Child Pose",
        "무릎을 꿇고 상체를 앞으로 숙여 허리와 등을 이완하는 마무리 스트레칭이다.",
    ),
    "COOLDOWN_CALF_STRETCH": ExerciseText(
        "종아리 스트레칭",
        "Calf Stretch",
        "벽을 짚고 뒤꿈치를 눌러 종아리를 늘여주는 마무리 스트레칭이다.",
    ),
}


def indexable_record(stable_code: str) -> IndexableExerciseRecord:
    """Project one evaluation exercise into the record the index builder embeds."""

    record = catalog.CATALOG[stable_code]
    text = TEXT[stable_code]
    return IndexableExerciseRecord(
        exercise_id=record.exercise_id,
        catalog_version_id=CATALOG_VERSION_ID,
        catalog_version_code=record.catalog_version,
        catalog_manifest_hash=CATALOG_MANIFEST_HASH,
        name_ko=text.name_ko,
        name_en=text.name_en,
        instruction_summary_ko=text.instruction_summary_ko,
        instruction_content_version=INSTRUCTION_CONTENT_VERSION,
        training_type_code=record.training_type_code,
        body_focus_code=record.body_focus_code,
        primary_movement_pattern_code=record.movement_pattern_codes[0],
        difficulty_code=record.difficulty_code,
        recovery_eligible=record.recovery_eligible,
        review_status_code="DOMAIN_APPROVED",
        review_method_code="EVAL_FIXTURE",
        status_interpretation_code="ACTIVE",
        production_eligible=True,
        goal_codes=record.goal_codes,
        equipment_codes=record.equipment_codes,
        location_codes=record.location_codes,
        phase_codes=record.phase_codes,
        prescription_experience_level_codes=("BEGINNER",),
        stable_code=record.stable_code,
        family_code=record.family_code,
        timing_mode_code=record.timing_mode_code,
        default_seconds_per_rep=record.default_seconds_per_rep,
        default_work_seconds=record.default_work_seconds,
        default_rest_seconds=record.default_rest_seconds,
        default_transition_seconds=record.default_transition_seconds,
        role_eligibility_code=record.role_eligibility_code,
    )


def all_indexable_records() -> tuple[IndexableExerciseRecord, ...]:
    """Every evaluation exercise, in canonical UUID order."""

    return tuple(
        sorted(
            (indexable_record(code) for code in catalog.CATALOG),
            key=lambda item: str(item.exercise_id),
        )
    )


__all__ = [
    "CATALOG_MANIFEST_HASH",
    "CATALOG_VERSION_ID",
    "TEXT",
    "ExerciseText",
    "all_indexable_records",
    "indexable_record",
]
