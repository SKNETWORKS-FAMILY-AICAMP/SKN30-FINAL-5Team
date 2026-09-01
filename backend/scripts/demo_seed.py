"""Repeatable synthetic catalog seed for the local vertical-slice demo.

Why this exists
---------------
`RoutineRepository.get_creation_context` only builds candidates from a catalog
version that is `ACTIVE` + `DOMAIN_APPROVED` + `DOMAIN_REVIEWER` +
`PRODUCTION_APPROVED` + `production_eligible`, joined to
`exercise_prescription_profiles` and `exercise_goal_tag_links`.

The shipped artifacts under `data/generated/` cannot satisfy that:

* every seed manifest is `review_method_code=AGENT_ONLY`,
  `status_interpretation=PIPELINE_COMPATIBILITY_ONLY`, `production_eligible=false`
* `CatalogImporter` writes catalog/exercise/body-part/equipment/location rows only,
  so it never produces the prescription or goal-tag rows the join requires

So the demo needs its own synthetic content. The rows written here are invented
for demonstration, carry no domain review, and are deliberately fenced off:

* refuses any database whose name is not `*_test` or `*_demo`
* refuses any `APP_ENV` other than `local` or `test`
* stamps `manifest_metadata.synthetic = true` so the origin stays visible in the DB

Never point this at a production or user database, and never promote these rows
to a real catalog. Real content requires the domain review process in
`data/AGENTS.md`.

Usage
-----
    uv run python -m backend.scripts.demo_seed seed
    uv run python -m backend.scripts.demo_seed reset   # wipe demo users, then seed

`reset` deletes every user row (cascading to all user-linked data) so the demo
can be replayed from a clean state. It contains no personal data: nicknames,
birthdates, health values and identities are only ever created by the running
app from the tester's own Firebase account.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import (
    BodyArea,
    BodyFocus,
    CatalogVersion,
    Equipment,
    Exercise,
    ExerciseBodyPart,
    ExerciseEquipment,
    ExerciseGoalTagLink,
    ExerciseLocation,
    ExercisePrescriptionProfile,
    Location,
    MovementPattern,
    TrainingType,
)
from backend.app.db.models.identity import User
from backend.app.modules.catalog.codes import (
    CATALOG_CODE_SET_VERSION,
    BodyAreaCode,
    BodyAreaRoleCode,
    BodyFocusCode,
    EquipmentCode,
    EquipmentRequirementCode,
    LocationCode,
    MovementPatternCode,
    TrainingTypeCode,
)

DEMO_CATALOG_VERSION_CODE = "demo-synthetic-v1"
DEMO_GOAL_CODE = "GENERAL_FITNESS"
DEMO_EXPERIENCE_LEVEL_CODE = "BEGINNER"
DEMO_PRESCRIPTION_VERSION = "demo-synthetic-v1"

WARMUP = "WARMUP"
MAIN = "MAIN"
COOLDOWN = "COOLDOWN"
CORE = "CORE"
SUPPORT = "SUPPORT"


@dataclass(frozen=True)
class DemoExercise:
    """One synthetic block.

    `sets * work_seconds + (sets - 1) * rest_seconds + transition_seconds` is the
    block's contribution to the plan total, which the routine solver must match
    to `requested_duration_minutes * 60` exactly.
    """

    stable_code: str
    name_ko: str
    phase_code: str
    tier_code: str
    training_type_code: str
    body_focus_code: str
    movement_pattern_code: str
    primary_body_area_codes: tuple[str, ...]
    equipment_codes: tuple[str, ...]
    sets: int
    work_seconds: int
    rest_seconds: int
    transition_seconds: int
    intensity_code: str
    instruction_summary: str
    form_cues: tuple[str, ...]

    @property
    def block_seconds(self) -> int:
        return (
            self.sets * self.work_seconds
            + max(self.sets - 1, 0) * self.rest_seconds
            + self.transition_seconds
        )


def _mobility(
    stable_code: str,
    name_ko: str,
    phase_code: str,
    body_area: str,
    work_seconds: int,
    summary: str,
    cues: tuple[str, ...],
    movement_pattern_code: str = MovementPatternCode.MOBILITY_STRETCH,
) -> DemoExercise:
    return DemoExercise(
        stable_code=stable_code,
        name_ko=name_ko,
        phase_code=phase_code,
        tier_code=SUPPORT,
        training_type_code=TrainingTypeCode.MOBILITY,
        body_focus_code=BodyFocusCode.FULL_BODY,
        movement_pattern_code=movement_pattern_code,
        primary_body_area_codes=(body_area,),
        equipment_codes=(EquipmentCode.BODYWEIGHT,),
        sets=1,
        work_seconds=work_seconds,
        rest_seconds=0,
        transition_seconds=10,
        intensity_code="LOW",
        instruction_summary=summary,
        form_cues=cues,
    )


def _main_block(
    stable_code: str,
    name_ko: str,
    tier_code: str,
    body_focus_code: str,
    movement_pattern_code: str,
    body_areas: tuple[str, ...],
    sets: int,
    work_seconds: int,
    rest_seconds: int,
    intensity_code: str,
    summary: str,
    cues: tuple[str, ...],
    equipment_codes: tuple[str, ...] = (EquipmentCode.BODYWEIGHT,),
) -> DemoExercise:
    return DemoExercise(
        stable_code=stable_code,
        name_ko=name_ko,
        phase_code=MAIN,
        tier_code=tier_code,
        training_type_code=TrainingTypeCode.STRENGTH,
        body_focus_code=body_focus_code,
        movement_pattern_code=movement_pattern_code,
        primary_body_area_codes=body_areas,
        equipment_codes=equipment_codes,
        sets=sets,
        work_seconds=work_seconds,
        rest_seconds=rest_seconds,
        transition_seconds=10,
        intensity_code=intensity_code,
        instruction_summary=summary,
        form_cues=cues,
    )


# Warm-up blocks are 60s each, so totals of 60/120/180 stay inside the solver's
# 60..180 warm-up window.
_WARMUPS: tuple[DemoExercise, ...] = (
    _mobility(
        "demo_warmup_neck_shoulder",
        "목·어깨 가볍게 풀기",
        WARMUP,
        BodyAreaCode.SHOULDER,
        50,
        "어깨를 크게 돌리며 목과 어깨 주변을 천천히 풀어줍니다.",
        ("반동 없이 천천히 움직입니다.", "통증이 느껴지면 범위를 줄입니다."),
    ),
    _mobility(
        "demo_warmup_hip_opener",
        "고관절 열기",
        WARMUP,
        BodyAreaCode.HIP,
        50,
        "선 자세에서 무릎을 들어 바깥으로 원을 그리며 고관절을 풀어줍니다.",
        ("허리가 흔들리지 않게 배에 힘을 유지합니다.", "양쪽을 번갈아 진행합니다."),
    ),
    _mobility(
        "demo_warmup_march_in_place",
        "제자리 걷기",
        WARMUP,
        BodyAreaCode.ANKLE_FOOT,
        50,
        "제자리에서 팔을 자연스럽게 흔들며 가볍게 걷습니다.",
        ("호흡을 멈추지 않습니다.", "발 전체로 부드럽게 착지합니다."),
        movement_pattern_code=MovementPatternCode.GAIT,
    ),
)

# Cool-down totals of 45/60/105/120 stay inside the solver's 45..120 window.
_COOLDOWNS: tuple[DemoExercise, ...] = (
    _mobility(
        "demo_cooldown_chest_open",
        "가슴 열기 스트레칭",
        COOLDOWN,
        BodyAreaCode.CHEST,
        35,
        "양손을 뒤로 맞잡고 가슴을 부드럽게 열어줍니다.",
        ("어깨를 귀에서 멀리 내립니다.",),
    ),
    _mobility(
        "demo_cooldown_hamstring",
        "허벅지 뒤쪽 스트레칭",
        COOLDOWN,
        BodyAreaCode.HIP,
        50,
        "한쪽 다리를 앞으로 뻗고 상체를 천천히 숙여 허벅지 뒤쪽을 늘립니다.",
        ("무릎을 억지로 펴지 않습니다.", "편안한 범위에서 호흡을 유지합니다."),
    ),
    _mobility(
        "demo_cooldown_lower_back",
        "허리 이완 스트레칭",
        COOLDOWN,
        BodyAreaCode.LOWER_BACK,
        50,
        "누운 자세에서 무릎을 감싸 안고 허리를 편안하게 이완합니다.",
        ("목에 힘이 들어가지 않게 합니다.",),
    ),
)

# Main blocks are 60/120/240/480s. Those sizes let the subset-sum solver reach
# every multiple of 60 up to 3120s, and any total above 420s necessarily
# includes a CORE block, which the solver requires.
_MAINS: tuple[DemoExercise, ...] = (
    _main_block(
        "demo_main_bodyweight_squat",
        "맨몸 스쿼트",
        CORE,
        BodyFocusCode.LOWER_BODY,
        MovementPatternCode.KNEE_DOMINANT,
        (BodyAreaCode.HIP, BodyAreaCode.KNEE),
        4,
        95,
        30,
        "MODERATE",
        "발을 어깨너비로 벌리고 의자에 앉듯 엉덩이를 뒤로 보내며 앉았다 일어섭니다.",
        ("무릎이 발끝 방향을 향하게 합니다.", "허리를 둥글게 말지 않습니다."),
    ),
    _main_block(
        "demo_main_incline_push_up",
        "경사 푸시업",
        CORE,
        BodyFocusCode.UPPER_BODY,
        MovementPatternCode.HORIZONTAL_PUSH,
        (BodyAreaCode.CHEST, BodyAreaCode.SHOULDER),
        4,
        95,
        30,
        "MODERATE",
        "안정된 높은 지지대에 손을 짚고 몸을 일직선으로 유지하며 밀어냅니다.",
        ("손은 어깨보다 살짝 넓게 짚습니다.", "허리가 꺼지지 않게 배에 힘을 유지합니다."),
    ),
    _main_block(
        "demo_main_glute_bridge",
        "글루트 브리지",
        CORE,
        BodyFocusCode.LOWER_BODY,
        MovementPatternCode.HIP_DOMINANT,
        (BodyAreaCode.HIP,),
        4,
        95,
        30,
        "MODERATE",
        "누운 자세에서 발로 바닥을 밀며 엉덩이를 들어 올립니다.",
        ("허리가 아닌 엉덩이 힘으로 들어 올립니다.", "위에서 잠시 멈췄다 내려옵니다."),
        equipment_codes=(EquipmentCode.BODYWEIGHT, EquipmentCode.MAT),
    ),
    _main_block(
        "demo_main_reverse_lunge",
        "리버스 런지",
        CORE,
        BodyFocusCode.LOWER_BODY,
        MovementPatternCode.KNEE_DOMINANT,
        (BodyAreaCode.HIP, BodyAreaCode.KNEE),
        4,
        95,
        30,
        "MODERATE",
        "한쪽 발을 뒤로 보내며 앉았다가 제자리로 돌아옵니다.",
        ("상체를 세운 상태를 유지합니다.", "무릎이 바닥에 닿지 않게 조절합니다."),
    ),
    _main_block(
        "demo_main_front_plank",
        "플랭크",
        CORE,
        BodyFocusCode.CORE,
        MovementPatternCode.CORE_BRACE,
        (BodyAreaCode.ABDOMEN,),
        3,
        60,
        25,
        "MODERATE",
        "팔꿈치와 발끝으로 몸을 지지하며 일직선을 유지합니다.",
        ("엉덩이가 솟거나 처지지 않게 합니다.", "호흡을 멈추지 않습니다."),
        equipment_codes=(EquipmentCode.BODYWEIGHT, EquipmentCode.MAT),
    ),
    _main_block(
        "demo_main_split_squat",
        "스플릿 스쿼트",
        CORE,
        BodyFocusCode.LOWER_BODY,
        MovementPatternCode.KNEE_DOMINANT,
        (BodyAreaCode.HIP, BodyAreaCode.KNEE),
        3,
        60,
        25,
        "MODERATE",
        "한쪽 발을 앞으로 두고 상체를 세운 채 아래로 앉았다 일어섭니다.",
        ("앞 무릎이 안쪽으로 무너지지 않게 합니다.",),
    ),
    _main_block(
        "demo_main_dead_bug",
        "데드버그",
        CORE,
        BodyFocusCode.CORE,
        MovementPatternCode.CORE_BRACE,
        (BodyAreaCode.ABDOMEN,),
        3,
        60,
        25,
        "LOW",
        "누운 자세에서 반대쪽 팔과 다리를 번갈아 천천히 뻗습니다.",
        ("허리와 바닥 사이 공간을 유지합니다.", "동작 내내 호흡을 이어갑니다."),
        equipment_codes=(EquipmentCode.BODYWEIGHT, EquipmentCode.MAT),
    ),
    _main_block(
        "demo_main_bird_dog",
        "버드독",
        CORE,
        BodyFocusCode.CORE,
        MovementPatternCode.CORE_BRACE,
        (BodyAreaCode.ABDOMEN, BodyAreaCode.LOWER_BACK),
        3,
        60,
        25,
        "LOW",
        "네발 자세에서 반대쪽 팔과 다리를 나란히 뻗어 잠시 유지합니다.",
        ("골반이 기울지 않게 유지합니다.",),
        equipment_codes=(EquipmentCode.BODYWEIGHT, EquipmentCode.MAT),
    ),
    _main_block(
        "demo_main_wall_sit",
        "월 싯",
        CORE,
        BodyFocusCode.LOWER_BODY,
        MovementPatternCode.KNEE_DOMINANT,
        (BodyAreaCode.KNEE,),
        3,
        60,
        25,
        "MODERATE",
        "벽에 등을 대고 무릎을 굽혀 앉은 자세를 유지합니다.",
        ("무릎 각도가 90도를 넘지 않게 합니다.",),
    ),
    _main_block(
        "demo_main_standing_row_band",
        "밴드 로우",
        SUPPORT,
        BodyFocusCode.UPPER_BODY,
        MovementPatternCode.HORIZONTAL_PULL,
        (BodyAreaCode.UPPER_BACK,),
        2,
        45,
        20,
        "MODERATE",
        "밴드를 고정하고 팔꿈치를 뒤로 당겨 등 근육을 사용합니다.",
        ("가슴을 펴고 견갑골을 모읍니다.",),
        equipment_codes=(EquipmentCode.BODYWEIGHT, EquipmentCode.RESISTANCE_BAND),
    ),
    _main_block(
        "demo_main_calf_raise",
        "카프 레이즈",
        SUPPORT,
        BodyFocusCode.LOWER_BODY,
        MovementPatternCode.ISOLATION,
        (BodyAreaCode.ANKLE_FOOT,),
        2,
        45,
        20,
        "LOW",
        "발뒤꿈치를 천천히 들어 올렸다 내립니다.",
        ("중심이 흔들리면 벽을 가볍게 잡습니다.",),
    ),
    _main_block(
        "demo_main_side_plank_knee",
        "무릎 사이드 플랭크",
        SUPPORT,
        BodyFocusCode.CORE,
        MovementPatternCode.CORE_BRACE,
        (BodyAreaCode.ABDOMEN,),
        2,
        45,
        20,
        "LOW",
        "무릎을 굽힌 옆으로 누운 자세에서 골반을 들어 유지합니다.",
        ("몸이 앞뒤로 기울지 않게 합니다.",),
        equipment_codes=(EquipmentCode.BODYWEIGHT, EquipmentCode.MAT),
    ),
    _main_block(
        "demo_main_shoulder_tap",
        "숄더 탭",
        SUPPORT,
        BodyFocusCode.CORE,
        MovementPatternCode.CORE_BRACE,
        (BodyAreaCode.SHOULDER, BodyAreaCode.ABDOMEN),
        2,
        45,
        20,
        "LOW",
        "높은 플랭크 자세에서 한 손씩 반대쪽 어깨를 가볍게 터치합니다.",
        ("골반이 좌우로 흔들리지 않게 합니다.",),
        equipment_codes=(EquipmentCode.BODYWEIGHT, EquipmentCode.MAT),
    ),
    _main_block(
        "demo_main_heel_raise_hold",
        "발뒤꿈치 들고 버티기",
        SUPPORT,
        BodyFocusCode.LOWER_BODY,
        MovementPatternCode.ISOLATION,
        (BodyAreaCode.ANKLE_FOOT,),
        1,
        50,
        0,
        "LOW",
        "발뒤꿈치를 들어 올린 자세를 유지합니다.",
        ("호흡을 멈추지 않습니다.",),
    ),
    _main_block(
        "demo_main_standing_knee_lift",
        "무릎 들어 올리기",
        SUPPORT,
        BodyFocusCode.CORE,
        MovementPatternCode.CORE_BRACE,
        (BodyAreaCode.ABDOMEN,),
        1,
        50,
        0,
        "LOW",
        "선 자세에서 무릎을 배 높이까지 번갈아 들어 올립니다.",
        ("상체가 뒤로 넘어가지 않게 합니다.",),
    ),
    _main_block(
        "demo_main_hip_hinge_drill",
        "힙 힌지 연습",
        SUPPORT,
        BodyFocusCode.LOWER_BODY,
        MovementPatternCode.HIP_DOMINANT,
        (BodyAreaCode.HIP,),
        1,
        50,
        0,
        "LOW",
        "무릎을 살짝 굽힌 채 엉덩이를 뒤로 밀며 상체를 숙였다 세웁니다.",
        ("허리를 둥글게 말지 않습니다.",),
    ),
    _main_block(
        "demo_main_scapular_squeeze",
        "견갑골 모으기",
        SUPPORT,
        BodyFocusCode.UPPER_BODY,
        MovementPatternCode.HORIZONTAL_PULL,
        (BodyAreaCode.UPPER_BACK,),
        1,
        50,
        0,
        "LOW",
        "팔을 옆으로 벌린 채 견갑골을 뒤로 모았다 풀어줍니다.",
        ("어깨가 올라가지 않게 합니다.",),
    ),
)

_ALL_EXERCISES: tuple[DemoExercise, ...] = _WARMUPS + _MAINS + _COOLDOWNS


def _require_demo_database(database_url: str) -> str:
    """Fail closed unless this is unmistakably a throwaway demo database."""
    url = make_url(database_url)
    name = url.database or ""
    if not (name.endswith("_test") or name.endswith("_demo")):
        raise SystemExit(
            f"refusing to seed database {name!r}: "
            "the demo seed only runs against a *_test or *_demo database"
        )
    return name


def _require_demo_environment() -> None:
    settings = get_settings()
    if settings.app_env not in {"local", "test"}:
        raise SystemExit(
            f"refusing to seed with APP_ENV={settings.app_env!r}: "
            "the demo seed only runs in local or test"
        )


def _ensure_lookup_rows(session: Session) -> None:
    for model, codes in (
        (TrainingType, {exercise.training_type_code for exercise in _ALL_EXERCISES}),
        (BodyFocus, {exercise.body_focus_code for exercise in _ALL_EXERCISES}),
        (MovementPattern, {exercise.movement_pattern_code for exercise in _ALL_EXERCISES}),
        (
            Equipment,
            {code for exercise in _ALL_EXERCISES for code in exercise.equipment_codes},
        ),
        (Location, {LocationCode.HOME, LocationCode.GYM, LocationCode.OUTDOOR}),
        (
            BodyArea,
            {code for exercise in _ALL_EXERCISES for code in exercise.primary_body_area_codes},
        ),
    ):
        for code in sorted(codes):
            if session.get(model, code) is None:
                session.add(
                    model(
                        code=code,
                        code_set_version=CATALOG_CODE_SET_VERSION,
                        display_name_ko=None,
                    )
                )


def _write_exercise(
    session: Session,
    catalog_id: UUID,
    definition: DemoExercise,
) -> None:
    exercise = Exercise(
        id=uuid4(),
        catalog_version_id=catalog_id,
        stable_code=definition.stable_code,
        name_ko=definition.name_ko,
        name_en=None,
        training_type_code=definition.training_type_code,
        body_focus_code=definition.body_focus_code,
        primary_movement_pattern_code=definition.movement_pattern_code,
        difficulty_code="BEGINNER",
        timing_mode_code="DURATION",
        default_seconds_per_rep=None,
        default_work_seconds=definition.work_seconds,
        default_rest_seconds=definition.rest_seconds,
        default_transition_seconds=definition.transition_seconds,
        recovery_eligible=definition.phase_code != MAIN,
        instruction_summary_ko=definition.instruction_summary,
        form_cues_ko=list(definition.form_cues),
        instruction_content_version=DEMO_PRESCRIPTION_VERSION,
        review_status_code="DOMAIN_APPROVED",
        source_track_code="kspo",
        source_identity=f"synthetic-demo-{definition.stable_code}",
    )
    session.add(exercise)
    session.flush()

    for code in definition.primary_body_area_codes:
        session.add(
            ExerciseBodyPart(
                exercise_id=exercise.id,
                body_area_code=code,
                role_code=BodyAreaRoleCode.PRIMARY,
            )
        )
    for code in definition.equipment_codes:
        session.add(
            ExerciseEquipment(
                exercise_id=exercise.id,
                equipment_code=code,
                requirement_code=EquipmentRequirementCode.REQUIRED,
            )
        )
    for code in (LocationCode.HOME, LocationCode.GYM):
        session.add(ExerciseLocation(exercise_id=exercise.id, location_code=code))

    session.add(
        ExerciseGoalTagLink(
            exercise_id=exercise.id,
            goal_code=DEMO_GOAL_CODE,
            role_eligibility_code=definition.tier_code,
            review_status_code="DOMAIN_APPROVED",
        )
    )
    session.add(
        ExercisePrescriptionProfile(
            id=uuid4(),
            exercise_id=exercise.id,
            goal_code=DEMO_GOAL_CODE,
            experience_level_code=DEMO_EXPERIENCE_LEVEL_CODE,
            phase_code=definition.phase_code,
            sets=definition.sets,
            reps=None,
            work_seconds_per_set=definition.work_seconds,
            rest_seconds_per_set=definition.rest_seconds,
            intensity_code=definition.intensity_code,
            prescription_version=DEMO_PRESCRIPTION_VERSION,
            review_status_code="DOMAIN_APPROVED",
        )
    )


def seed_catalog(session: Session, now: datetime) -> UUID:
    """Install exactly one active synthetic catalog version.

    Idempotent: re-running keeps an existing demo catalog rather than deleting
    it, because saved routines and decision records reference it under an
    `ON DELETE RESTRICT` foreign key. Use `reset` for a clean slate.
    """
    _ensure_lookup_rows(session)

    # The routine repository requires exactly one qualifying catalog, so any
    # other active version has to step aside for the demo run.
    session.execute(
        update(CatalogVersion)
        .where(
            CatalogVersion.status_code == "ACTIVE",
            CatalogVersion.version_code != DEMO_CATALOG_VERSION_CODE,
        )
        .values(status_code="DEPRECATED", production_eligible=False, activated_at=None)
    )

    existing = session.scalar(
        select(CatalogVersion).where(CatalogVersion.version_code == DEMO_CATALOG_VERSION_CODE)
    )
    if existing is not None:
        existing.status_code = "ACTIVE"
        existing.production_eligible = True
        existing.activated_at = existing.activated_at or now
        return existing.id

    catalog = CatalogVersion(
        id=uuid4(),
        version_code=DEMO_CATALOG_VERSION_CODE,
        status_code="ACTIVE",
        manifest_schema_version="1.0",
        generator_version=DEMO_PRESCRIPTION_VERSION,
        code_set_version=CATALOG_CODE_SET_VERSION,
        source_manifest_hash="0" * 64,
        source_track_code="kspo",
        review_status_code="DOMAIN_APPROVED",
        review_method_code="DOMAIN_REVIEWER",
        status_interpretation_code="PRODUCTION_APPROVED",
        production_eligible=True,
        exercise_record_count=len(_ALL_EXERCISES),
        manifest_metadata={
            "synthetic": True,
            "purpose": "vertical-slice-demo",
            "domain_review": "none - synthetic demo content, not for production",
        },
        activated_at=now,
    )
    session.add(catalog)
    session.flush()

    for definition in _ALL_EXERCISES:
        _write_exercise(session, catalog.id, definition)
    return catalog.id


def reset_users(session: Session) -> int:
    """Delete every demo user and everything that hangs off them.

    Truncated rather than deleted: several user-owned tables hold intentional
    `ON DELETE RESTRICT` references to other user-owned rows, among them
    `weekly_plan_revisions.routine_id`, `decision_runs.base_routine_id` and
    `scheduled_workouts.routine_day_id`. A plain `DELETE FROM users` then
    depends on the order PostgreSQL happens to process the cascade in, and
    fails once a demo account has reached those flows. `TRUNCATE ... CASCADE`
    is order independent and reaches exactly the tables that reference `users`,
    so the catalog is left alone. `main` has already restricted this to a
    *_demo or *_test database.
    """
    total = int(session.scalar(select(func.count()).select_from(User)) or 0)
    if total:
        session.execute(text("TRUNCATE TABLE users CASCADE"))
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("seed", "reset"),
        help="seed installs the synthetic catalog; reset also deletes demo users first",
    )
    args = parser.parse_args(argv)

    _require_demo_environment()
    settings = get_settings()
    database_url = settings.database_url.get_secret_value()
    database_name = _require_demo_database(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            deleted = reset_users(session) if args.command == "reset" else 0
            catalog_id = seed_catalog(session, datetime.now(UTC))
    finally:
        engine.dispose()

    if args.command == "reset":
        print(f"deleted {deleted} demo user(s) from {database_name}")
    print(
        f"installed synthetic catalog {DEMO_CATALOG_VERSION_CODE} "
        f"({len(_ALL_EXERCISES)} exercises) as {catalog_id} in {database_name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
