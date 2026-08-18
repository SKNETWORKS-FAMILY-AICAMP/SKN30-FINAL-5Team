from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.modules.catalog.codes import (
    BodyAreaCode,
    BodyFocusCode,
    CatalogReviewStatusCode,
    CatalogVersionStatusCode,
    DifficultyCode,
    EquipmentCode,
    LocationCode,
    MovementPatternCode,
    ReviewMethodCode,
    ReviewStatusInterpretationCode,
    SourceTrackCode,
    TimingModeCode,
    TrainingTypeCode,
)

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
StableCode = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$", max_length=120)]


class CatalogInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManifestCatalogVersion(CatalogInputModel):
    version_code: Annotated[str, Field(min_length=1, max_length=120)]
    status_code: CatalogVersionStatusCode


class ManifestInputArtifact(CatalogInputModel):
    role: Annotated[str, Field(min_length=1, max_length=80)]
    path: Annotated[str, Field(min_length=1, max_length=500)]
    sha256: Sha256
    bytes: Annotated[int, Field(ge=0)]


class ManifestSource(CatalogInputModel):
    track: SourceTrackCode
    review_batch_directory: Annotated[str, Field(min_length=1, max_length=255)]
    taxonomy_registry_sha256: Sha256
    input_artifacts: list[ManifestInputArtifact]


class ManifestReview(CatalogInputModel):
    status: CatalogReviewStatusCode
    review_method_code: ReviewMethodCode
    status_interpretation: ReviewStatusInterpretationCode
    production_eligible: bool


class ManifestSummary(CatalogInputModel):
    exercise_records: Annotated[int, Field(ge=0)]


class ManifestFile(CatalogInputModel):
    path: Annotated[str, Field(min_length=1, max_length=500)]
    sha256: Sha256
    bytes: Annotated[int, Field(ge=0)]
    records: Annotated[int, Field(ge=0)]


class CatalogManifest(CatalogInputModel):
    schema_version: Literal["1.0"]
    generator_version: Annotated[str, Field(min_length=1, max_length=80)]
    catalog_version: ManifestCatalogVersion
    source: ManifestSource
    review: ManifestReview
    summary: ManifestSummary
    files: list[ManifestFile]

    @model_validator(mode="after")
    def validate_single_exercise_file(self) -> "CatalogManifest":
        if len(self.files) != 1:
            raise ValueError("manifest must describe exactly one exercise JSONL file")
        if self.summary.exercise_records != self.files[0].records:
            raise ValueError("manifest summary and file record counts must match")
        return self


class ExerciseRecord(CatalogInputModel):
    stable_code: StableCode
    name_ko: Annotated[str, Field(min_length=1, max_length=200)]
    name_en: Annotated[str, Field(max_length=200)]
    training_type_code: TrainingTypeCode
    body_focus_code: BodyFocusCode
    primary_movement_pattern_code: MovementPatternCode
    difficulty_code: DifficultyCode
    beginner_suitable: bool
    timing_mode_code: TimingModeCode
    default_seconds_per_rep: Annotated[int | None, Field(gt=0)] = None
    default_work_seconds: Annotated[int | None, Field(gt=0)] = None
    default_rest_seconds: Annotated[int, Field(ge=0)]
    default_transition_seconds: Annotated[int, Field(ge=10, le=20)]
    recovery_eligible: bool
    primary_body_area_codes: list[BodyAreaCode]
    secondary_body_area_codes: list[BodyAreaCode]
    equipment_codes: list[EquipmentCode]
    location_codes: list[LocationCode]
    instruction_summary_ko: Annotated[str, Field(min_length=1)]
    form_cues_ko: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    instruction_content_version: Annotated[str, Field(min_length=1, max_length=80)]
    review_status_code: CatalogReviewStatusCode
    source_track: SourceTrackCode
    source_identity: Annotated[str, Field(min_length=1, max_length=255)]

    @field_validator(
        "primary_body_area_codes",
        "secondary_body_area_codes",
        "equipment_codes",
        "location_codes",
    )
    @classmethod
    def validate_unique_codes(cls, value: list[object]) -> list[object]:
        if len(value) != len(set(value)):
            raise ValueError("code lists must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_timing_fields(self) -> "ExerciseRecord":
        if self.timing_mode_code is TimingModeCode.REPS:
            if self.default_seconds_per_rep is None or self.default_work_seconds is not None:
                raise ValueError("REPS requires seconds_per_rep and forbids work_seconds")
        elif self.default_work_seconds is None or self.default_seconds_per_rep is not None:
            raise ValueError("DURATION requires work_seconds and forbids seconds_per_rep")

        overlap = set(self.primary_body_area_codes) & set(self.secondary_body_area_codes)
        if overlap:
            raise ValueError("primary and secondary body areas must not overlap")
        if not self.primary_body_area_codes:
            raise ValueError("at least one primary body area is required")
        if not self.equipment_codes or not self.location_codes:
            raise ValueError("at least one equipment and location code is required")
        return self


class ExerciseDetailResponse(BaseModel):
    """Reviewed instruction content for one planned exercise block.

    This is presentation content only and never implies camera-based posture
    detection or automated form judgement.
    """

    exercise_id: UUID
    exercise_name: str
    training_type_code: str
    primary_body_area_codes: list[str]
    instruction_summary: str
    form_cues: list[str]
    media_asset_key: str | None = None
    mascot_animation_asset_key: str | None = None
    instruction_content_version: str
