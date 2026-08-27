from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import (
    get_catalog_repository,
    get_current_user,
    get_db_session,
)
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.catalog.service import (
    ApprovedCatalogRecord,
    ExerciseDetailRecord,
    ExerciseListRecord,
    ExerciseVariantRecord,
    ExerciseVariantSetUnavailableError,
    ExerciseVariantsRecord,
)
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser


class FakeSession:
    pass


class FakeExerciseRepository:
    def __init__(self, records: tuple[ExerciseListRecord, ...]) -> None:
        self.catalog: ApprovedCatalogRecord | None = ApprovedCatalogRecord(
            catalog_version_id=UUID(int=1000),
            version_code="catalog-production-v1",
        )
        self.records = records
        self.details: dict[UUID, ExerciseDetailRecord] = {}
        self.variants: dict[UUID, ExerciseVariantsRecord] = {}
        self.variant_error: Exception | None = None
        self.requested_limits: list[int] = []

    def get_approved_catalog(self, session: object) -> ApprovedCatalogRecord | None:
        return self.catalog

    def list_approved_exercises(
        self,
        session: object,
        catalog_version_id: UUID,
        *,
        body_area_code: str | None,
        equipment_code: str | None,
        training_type_code: str | None,
        difficulty_code: str | None,
        after_exercise_id: UUID | None,
        limit: int,
    ) -> tuple[ExerciseListRecord, ...]:
        self.requested_limits.append(limit)
        assert self.catalog is not None
        assert catalog_version_id == self.catalog.catalog_version_id
        rows = [
            row
            for row in self.records
            if (body_area_code is None or body_area_code in row.primary_body_area_codes)
            and (equipment_code is None or equipment_code in row.required_equipment_codes)
            and (training_type_code is None or training_type_code == row.training_type_code)
            and (difficulty_code is None or difficulty_code == row.difficulty_code)
            and (after_exercise_id is None or row.exercise_id > after_exercise_id)
        ]
        return tuple(sorted(rows, key=lambda row: row.exercise_id)[:limit])

    def get_exercise_detail(
        self, session: object, exercise_id: UUID
    ) -> ExerciseDetailRecord | None:
        return self.details.get(exercise_id)

    def get_equipment_variants(
        self,
        session: object,
        exercise_id: UUID,
    ) -> ExerciseVariantsRecord | None:
        if self.variant_error is not None:
            raise self.variant_error
        return self.variants.get(exercise_id)


def _record(index: int) -> ExerciseListRecord:
    return ExerciseListRecord(
        exercise_id=UUID(int=index + 1),
        exercise_name=f"운동 {index + 1}",
        training_type_code="STRENGTH" if index % 2 == 0 else "MOBILITY",
        difficulty_code="BEGINNER" if index % 2 == 0 else "INTERMEDIATE",
        primary_body_area_codes=("HIP", "KNEE") if index % 2 == 0 else ("SHOULDER",),
        required_equipment_codes=("BODYWEIGHT", "DUMBBELL") if index % 3 == 0 else ("BODYWEIGHT",),
    )


def _client(repository: FakeExerciseRepository, *, authenticated: bool = True) -> TestClient:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
    )
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id=uuid4(), status_code=UserStatusCode.ACTIVE
        )

    def session_override():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_catalog_repository] = lambda: repository
    return TestClient(app)


def test_exercise_list_requires_authentication() -> None:
    repository = FakeExerciseRepository(())
    with _client(repository, authenticated=False) as client:
        response = client.get("/api/v1/exercises")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_exercise_list_returns_contract_and_uses_default_limit() -> None:
    repository = FakeExerciseRepository(tuple(_record(index) for index in range(25)))
    with _client(repository) as client:
        response = client.get("/api/v1/exercises")

    body = response.json()
    assert response.status_code == 200
    assert len(body["items"]) == 20
    assert body["next_cursor"] is not None
    assert body["catalog_version"] == "catalog-production-v1"
    assert repository.requested_limits == [21]
    assert body["items"][0] == {
        "id": str(UUID(int=1)),
        "name": "운동 1",
        "training_type_code": "STRENGTH",
        "difficulty_code": "BEGINNER",
        "primary_body_area_codes": ["HIP", "KNEE"],
        "required_equipment_codes": ["BODYWEIGHT", "DUMBBELL"],
        "media_asset_key": None,
    }


def test_exercise_list_combines_filters_with_and_and_returns_empty_page() -> None:
    repository = FakeExerciseRepository(tuple(_record(index) for index in range(12)))
    with _client(repository) as client:
        filtered = client.get(
            "/api/v1/exercises",
            params={
                "body_area_code": "KNEE",
                "equipment_code": "DUMBBELL",
                "training_type_code": "STRENGTH",
                "difficulty_code": "BEGINNER",
            },
        )
        empty = client.get("/api/v1/exercises", params={"training_type_code": "CARDIO"})

    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [
        str(UUID(int=1)),
        str(UUID(int=7)),
    ]
    assert empty.status_code == 200
    assert empty.json() == {
        "items": [],
        "next_cursor": None,
        "catalog_version": "catalog-production-v1",
    }


@pytest.mark.parametrize(
    ("filter_name", "filter_value", "expected_ids"),
    (
        ("body_area_code", "KNEE", (1, 3, 5)),
        ("equipment_code", "DUMBBELL", (1, 4)),
        ("training_type_code", "MOBILITY", (2, 4, 6)),
        ("difficulty_code", "INTERMEDIATE", (2, 4, 6)),
    ),
)
def test_exercise_list_applies_each_filter(
    filter_name: str,
    filter_value: str,
    expected_ids: tuple[int, ...],
) -> None:
    repository = FakeExerciseRepository(tuple(_record(index) for index in range(6)))
    with _client(repository) as client:
        response = client.get("/api/v1/exercises", params={filter_name: filter_value})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        str(UUID(int=value)) for value in expected_ids
    ]


def test_exercise_list_cursor_has_no_duplicates_and_rejects_invalid_or_stale_values() -> None:
    repository = FakeExerciseRepository(tuple(_record(index) for index in range(7)))
    with _client(repository) as client:
        first = client.get("/api/v1/exercises", params={"limit": 3})
        second = client.get(
            "/api/v1/exercises",
            params={"limit": 3, "cursor": first.json()["next_cursor"]},
        )
        malformed = client.get("/api/v1/exercises", params={"cursor": "not-a-cursor"})
        repository.catalog = ApprovedCatalogRecord(
            catalog_version_id=UUID(int=2000), version_code="catalog-production-v2"
        )
        stale = client.get("/api/v1/exercises", params={"cursor": first.json()["next_cursor"]})

    first_ids = {item["id"] for item in first.json()["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert first.status_code == second.status_code == 200
    assert first_ids.isdisjoint(second_ids)
    assert malformed.status_code == stale.status_code == 400
    assert malformed.json()["error"]["code"] == "INVALID_REQUEST"
    assert stale.json()["error"]["code"] == "INVALID_REQUEST"


def test_exercise_list_validates_filter_codes_and_limit_bounds() -> None:
    repository = FakeExerciseRepository(())
    with _client(repository) as client:
        invalid_code = client.get("/api/v1/exercises", params={"body_area_code": "NOT_A_BODY_AREA"})
        below_minimum = client.get("/api/v1/exercises", params={"limit": 0})
        maximum = client.get("/api/v1/exercises", params={"limit": 100})
        above_maximum = client.get("/api/v1/exercises", params={"limit": 101})

    assert invalid_code.status_code == below_minimum.status_code == above_maximum.status_code == 400
    assert invalid_code.json()["error"]["code"] == "INVALID_REQUEST"
    assert maximum.status_code == 200
    assert repository.requested_limits == [101]


def test_exercise_list_fails_closed_without_an_approved_catalog() -> None:
    repository = FakeExerciseRepository(())
    repository.catalog = None
    with _client(repository) as client:
        response = client.get("/api/v1/exercises")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "APPROVED_CATALOG_UNAVAILABLE"


def test_exercise_detail_route_remains_available() -> None:
    repository = FakeExerciseRepository(())
    exercise_id = uuid4()
    repository.details[exercise_id] = ExerciseDetailRecord(
        exercise_id=exercise_id,
        exercise_name="기존 상세 운동",
        training_type_code="STRENGTH",
        primary_body_area_codes=("CHEST",),
        instruction_summary="기존 상세 설명",
        form_cues=("천천히 수행합니다.",),
        instruction_content_version="instruction-v1",
    )
    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{exercise_id}")

    assert response.status_code == 200
    assert response.json()["exercise_id"] == str(exercise_id)
    assert response.json()["exercise_name"] == "기존 상세 운동"


def test_equipment_variants_require_authentication() -> None:
    repository = FakeExerciseRepository(())
    with _client(repository, authenticated=False) as client:
        response = client.get(f"/api/v1/exercises/{uuid4()}/variants")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_equipment_variants_return_reviewed_display_contract_in_stable_order() -> None:
    repository = FakeExerciseRepository(())
    source_id = uuid4()
    first_id = UUID(int=10)
    second_id = UUID(int=20)
    repository.variants[source_id] = ExerciseVariantsRecord(
        source_exercise_id=source_id,
        catalog_version="catalog-production-v1",
        source_required_equipment_codes=("DUMBBELL", "MAT"),
        alternative_set_version="alternative-set-v2.0.1",
        items=(
            ExerciseVariantRecord(
                exercise_id=first_id,
                exercise_name="맨몸 변형 1",
                required_equipment_codes=("BODYWEIGHT",),
                instruction_summary="장비 없이 천천히 수행합니다.",
                form_cues=("허리를 중립으로 유지합니다.",),
                goal_preservation_code="GENERAL_FITNESS",
            ),
            ExerciseVariantRecord(
                exercise_id=second_id,
                exercise_name="맨몸 변형 2",
                required_equipment_codes=("BODYWEIGHT",),
                instruction_summary="바닥에서 수행합니다.",
                form_cues=("반동을 사용하지 않습니다.",),
                goal_preservation_code="GENERAL_FITNESS",
                media_asset_key="catalog-media/exercises/variant.webp",
            ),
        ),
    )

    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{source_id}/variants")

    assert response.status_code == 200
    assert response.json() == {
        "source_exercise_id": str(source_id),
        "source_required_equipment_codes": ["DUMBBELL", "MAT"],
        "items": [
            {
                "exercise_id": str(first_id),
                "exercise_name": "맨몸 변형 1",
                "required_equipment_codes": ["BODYWEIGHT"],
                "instruction_summary": "장비 없이 천천히 수행합니다.",
                "form_cues": ["허리를 중립으로 유지합니다."],
                "media_asset_key": None,
                "goal_preservation_code": "GENERAL_FITNESS",
            },
            {
                "exercise_id": str(second_id),
                "exercise_name": "맨몸 변형 2",
                "required_equipment_codes": ["BODYWEIGHT"],
                "instruction_summary": "바닥에서 수행합니다.",
                "form_cues": ["반동을 사용하지 않습니다."],
                "media_asset_key": "catalog-media/exercises/variant.webp",
                "goal_preservation_code": "GENERAL_FITNESS",
            },
        ],
        "catalog_version": "catalog-production-v1",
        "alternative_set_version": "alternative-set-v2.0.1",
    }


def test_equipment_variants_return_empty_items_when_no_variant_exists() -> None:
    repository = FakeExerciseRepository(())
    source_id = uuid4()
    repository.variants[source_id] = ExerciseVariantsRecord(
        source_exercise_id=source_id,
        catalog_version="catalog-production-v1",
        source_required_equipment_codes=("BODYWEIGHT",),
        alternative_set_version=None,
        items=(),
    )

    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{source_id}/variants")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["alternative_set_version"] is None


def test_equipment_variants_reject_unknown_source_exercise() -> None:
    repository = FakeExerciseRepository(())
    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{uuid4()}/variants")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_equipment_variants_do_not_depend_on_the_current_active_catalog() -> None:
    repository = FakeExerciseRepository(())
    repository.catalog = None
    source_id = uuid4()
    repository.variants[source_id] = ExerciseVariantsRecord(
        source_exercise_id=source_id,
        catalog_version="catalog-deprecated-v1",
        source_required_equipment_codes=("BODYWEIGHT",),
        alternative_set_version=None,
        items=(),
    )
    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{source_id}/variants")

    assert response.status_code == 200
    assert response.json()["catalog_version"] == "catalog-deprecated-v1"


def test_equipment_variants_map_database_failure_to_common_error() -> None:
    repository = FakeExerciseRepository(())
    repository.variant_error = SQLAlchemyError("synthetic database failure")
    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{uuid4()}/variants")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_equipment_variants_fail_closed_for_multiple_approved_sets() -> None:
    repository = FakeExerciseRepository(())
    repository.variant_error = ExerciseVariantSetUnavailableError()
    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{uuid4()}/variants")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "APPROVED_CATALOG_UNAVAILABLE"
