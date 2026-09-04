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
from backend.app.modules.catalog.approvals import get_derived_data_approval
from backend.app.modules.catalog.service import (
    ApprovedCatalogRecord,
    ExerciseDetailRecord,
    ExerciseListRecord,
    ExerciseVariantRecord,
    ExerciseVariantSetUnavailableError,
    ExerciseVariantsRecord,
    HouseholdEquipmentGuideRecord,
)
from backend.app.modules.identity.codes import UserStatusCode
from backend.app.modules.identity.service import CurrentUser


class FakeSession:
    pass


class FakeMediaUrlProvider:
    def __init__(self, url: str | None = None) -> None:
        self.url = url
        self.keys: list[str] = []

    def create_url(self, source_object_key: str) -> str | None:
        self.keys.append(source_object_key)
        return self.url


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


def _client(
    repository: FakeExerciseRepository,
    *,
    authenticated: bool = True,
    media_url_provider: FakeMediaUrlProvider | None = None,
) -> TestClient:
    app = create_app(
        settings=Settings(
            app_env="test", database_url="postgresql+psycopg://test:test@localhost/test"
        ),
        readiness_probe=lambda: None,
        exercise_media_url_provider=media_url_provider,
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
    assert response.json()["media_asset_key"] is None
    assert response.json()["media_url"] is None


def test_exercise_detail_returns_persisted_household_equipment_guide() -> None:
    repository = FakeExerciseRepository(())
    exercise_id = uuid4()
    repository.details[exercise_id] = ExerciseDetailRecord(
        exercise_id=exercise_id,
        exercise_name="guide exercise",
        training_type_code="STRENGTH",
        primary_body_area_codes=("CHEST",),
        instruction_summary="instruction",
        form_cues=("cue",),
        instruction_content_version="instruction-v1",
        household_equipment_guides=(
            HouseholdEquipmentGuideRecord(
                equipment_code="DUMBBELL",
                proposal_ko="Use a filled bottle.",
                examples_ko=("water bottle",),
                cautions_ko=("Keep a secure grip.",),
            ),
        ),
    )

    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{exercise_id}")

    assert response.status_code == 200
    assert response.json()["household_equipment_guides"] == [
        {
            "equipment_code": "DUMBBELL",
            "proposal_ko": "Use a filled bottle.",
            "examples_ko": ["water bottle"],
            "cautions_ko": ["Keep a secure grip."],
        }
    ]


def test_exercise_detail_reads_guide_from_validated_bundle() -> None:
    repository = FakeExerciseRepository(())
    exercise_id = uuid4()
    repository.details[exercise_id] = ExerciseDetailRecord(
        exercise_id=exercise_id,
        exercise_name="bundle guide exercise",
        training_type_code="STRENGTH",
        primary_body_area_codes=("ELBOW",),
        instruction_summary="instruction",
        form_cues=("cue",),
        instruction_content_version="instruction-v1",
        exercise_stable_code="dumbbell_alternate_biceps_curl",
    )

    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{exercise_id}")

    assert response.status_code == 200
    guides = response.json()["household_equipment_guides"]
    assert guides is not None
    assert guides[0]["equipment_code"] == "DUMBBELL"
    assert guides[0]["examples_ko"]
    assert guides[0]["cautions_ko"]


def test_exercise_detail_returns_url_only_for_exact_registry_approved_media() -> None:
    approval = get_derived_data_approval(
        "MEDIA_ASSETS",
        "media-set-v2.0.2",
        "0ede3cef89a5dd722e9acae42cb2d6244e0f055f98ff75e5edc4fbe6d81e04d7",
        68,
    )
    assert approval is not None
    repository = FakeExerciseRepository(())
    exercise_id = uuid4()
    source_key = "videos/0073-i6LWJok.gif"
    repository.details[exercise_id] = ExerciseDetailRecord(
        exercise_id=exercise_id,
        exercise_name="바벨 풀오버",
        training_type_code="STRENGTH",
        primary_body_area_codes=("CHEST",),
        instruction_summary="천천히 수행합니다.",
        form_cues=("반동을 사용하지 않습니다.",),
        instruction_content_version="instruction-v1",
        media_asset_key="catalog-media/gymvisual/barbell_pullover/demo.gif",
        source_identity="0073",
        media_source_object_key=source_key,
        media_status="AVAILABLE",
        media_rights_review_status="APPROVED",
        media_set_version_code="media-set-v2.0.2",
        media_source_manifest_hash=(
            "0ede3cef89a5dd722e9acae42cb2d6244e0f055f98ff75e5edc4fbe6d81e04d7"
        ),
        media_approval_metadata=approval.metadata(),
    )
    provider = FakeMediaUrlProvider("https://signed.example/object")

    with _client(repository, media_url_provider=provider) as client:
        response = client.get(f"/api/v1/exercises/{exercise_id}")
    failing_provider = FakeMediaUrlProvider(None)
    with _client(repository, media_url_provider=failing_provider) as client:
        failed_response = client.get(f"/api/v1/exercises/{exercise_id}")

    assert response.status_code == 200
    assert response.json()["media_asset_key"] == (
        "catalog-media/gymvisual/barbell_pullover/demo.gif"
    )
    assert response.json()["media_url"] == "https://signed.example/object"
    assert provider.keys == [source_key]
    assert failed_response.status_code == 200
    assert failed_response.json()["media_url"] is None


@pytest.mark.parametrize(
    "overrides",
    (
        {"media_status": "UNAVAILABLE"},
        {"media_rights_review_status": "PENDING"},
        {"media_source_object_key": None},
        {"source_identity": "0082"},
        {"media_approval_metadata": None},
        {"media_source_manifest_hash": "f" * 64},
    ),
)
def test_exercise_detail_returns_null_for_ineligible_media(overrides: dict[str, object]) -> None:
    approval = get_derived_data_approval(
        "MEDIA_ASSETS",
        "media-set-v2.0.2",
        "0ede3cef89a5dd722e9acae42cb2d6244e0f055f98ff75e5edc4fbe6d81e04d7",
        68,
    )
    assert approval is not None
    repository = FakeExerciseRepository(())
    exercise_id = uuid4()
    values = {
        "media_asset_key": "catalog-media/gymvisual/test/demo.gif",
        "source_identity": "0073",
        "media_source_object_key": "videos/0073-i6LWJok.gif",
        "media_status": "AVAILABLE",
        "media_rights_review_status": "APPROVED",
        "media_set_version_code": "media-set-v2.0.2",
        "media_source_manifest_hash": (
            "0ede3cef89a5dd722e9acae42cb2d6244e0f055f98ff75e5edc4fbe6d81e04d7"
        ),
        "media_approval_metadata": approval.metadata(),
    }
    values.update(overrides)
    repository.details[exercise_id] = ExerciseDetailRecord(
        exercise_id=exercise_id,
        exercise_name="운동",
        training_type_code="STRENGTH",
        primary_body_area_codes=("CHEST",),
        instruction_summary="설명",
        form_cues=("자세",),
        instruction_content_version="instruction-v1",
        **values,
    )
    provider = FakeMediaUrlProvider("https://signed.example/object")

    with _client(repository, media_url_provider=provider) as client:
        response = client.get(f"/api/v1/exercises/{exercise_id}")

    assert response.status_code == 200
    assert response.json()["media_url"] is None
    assert provider.keys == []


def test_exercise_detail_keeps_authentication_and_not_found_contracts() -> None:
    repository = FakeExerciseRepository(())
    exercise_id = uuid4()
    with _client(repository, authenticated=False) as client:
        unauthenticated = client.get(f"/api/v1/exercises/{exercise_id}")
    with _client(repository) as client:
        missing = client.get(f"/api/v1/exercises/{exercise_id}")

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


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
                "missing_equipment_code": None,
                "selection_rationale_ko": None,
                "household_guide": None,
            },
            {
                "exercise_id": str(second_id),
                "exercise_name": "맨몸 변형 2",
                "required_equipment_codes": ["BODYWEIGHT"],
                "instruction_summary": "바닥에서 수행합니다.",
                "form_cues": ["반동을 사용하지 않습니다."],
                "media_asset_key": "catalog-media/exercises/variant.webp",
                "goal_preservation_code": "GENERAL_FITNESS",
                "missing_equipment_code": None,
                "selection_rationale_ko": None,
                "household_guide": None,
            },
        ],
        "catalog_version": "catalog-production-v1",
        "alternative_set_version": "alternative-set-v2.0.1",
    }


def test_equipment_variant_returns_missing_equipment_rationale_and_guide() -> None:
    repository = FakeExerciseRepository(())
    source_id = uuid4()
    variant_id = uuid4()
    repository.variants[source_id] = ExerciseVariantsRecord(
        source_exercise_id=source_id,
        catalog_version="catalog-production-v1",
        source_required_equipment_codes=("DUMBBELL",),
        alternative_set_version="home-equipment-variants-v1-final-2026-09-04",
        items=(
            ExerciseVariantRecord(
                exercise_id=variant_id,
                exercise_name="bodyweight alternative",
                required_equipment_codes=("BODYWEIGHT",),
                instruction_summary="instruction",
                form_cues=("cue",),
                goal_preservation_code="EQUIPMENT_VARIANT",
                missing_equipment_code="DUMBBELL",
                selection_rationale_ko="Missing dumbbell variant.",
                household_guide=HouseholdEquipmentGuideRecord(
                    equipment_code="DUMBBELL",
                    proposal_ko="Use a filled bottle.",
                    examples_ko=("water bottle",),
                    cautions_ko=("Keep a secure grip.",),
                ),
            ),
        ),
    )

    with _client(repository) as client:
        response = client.get(f"/api/v1/exercises/{source_id}/variants")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["missing_equipment_code"] == "DUMBBELL"
    assert item["selection_rationale_ko"] == "Missing dumbbell variant."
    assert item["household_guide"] == {
        "equipment_code": "DUMBBELL",
        "proposal_ko": "Use a filled bottle.",
        "examples_ko": ["water bottle"],
        "cautions_ko": ["Keep a secure grip."],
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
