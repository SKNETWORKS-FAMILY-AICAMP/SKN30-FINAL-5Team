from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from backend.app.modules.catalog.codes import (
    V2_BODY_FOCUS_CODES,
    BodyAreaCode,
    BodyAreaRoleCode,
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
    normalize_v2_equipment_code,
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


class BundleManifestFile(CatalogInputModel):
    path: Annotated[str, Field(min_length=1, max_length=500)]
    sha256: Sha256
    bytes: Annotated[int, Field(ge=0)]
    records: Annotated[int | None, Field(ge=0)] = None


class BundleDerivedSetVersions(CatalogInputModel):
    alternative_set_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    prescription_set_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    rule_set_version_code: Annotated[str, Field(min_length=1, max_length=120)]


class BundleSummary(CatalogInputModel):
    alternative_records: Annotated[int, Field(ge=0)]
    catalog_records: Annotated[int, Field(ge=0)]
    goal_tag_records: Annotated[int, Field(ge=0)]
    prescription_records: Annotated[int, Field(ge=0)]
    safety_rule_records: Annotated[int, Field(ge=0)]
    media_asset_records: Annotated[int | None, Field(ge=0)] = None


class CatalogBundleManifest(CatalogInputModel):
    schema_version: Literal["1.0"]
    bundle_version: Annotated[str, Field(min_length=1, max_length=120)]
    catalog_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    derived_set_versions: BundleDerivedSetVersions
    files: list[BundleManifestFile]
    importer_paths: dict[str, Annotated[str, Field(min_length=1, max_length=500)]]
    production_eligible: Literal[False]
    projection: dict[str, Any] | None = None
    status_code: Literal["DRAFT"]
    summary: BundleSummary

    @model_validator(mode="after")
    def validate_paths(self) -> "CatalogBundleManifest":
        required = {"catalog", "safety", "alternatives", "prescriptions"}
        optional = {"media"}
        if not required.issubset(self.importer_paths) or not set(self.importer_paths) <= (
            required | optional
        ):
            raise ValueError("bundle importer paths are incomplete or unsupported")
        paths = [entry.path for entry in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("bundle file paths must be unique")
        if not set(self.importer_paths.values()).issubset(paths):
            raise ValueError("bundle importer paths must reference listed files")
        return self


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

    @field_validator("body_focus_code", mode="before")
    @classmethod
    def validate_v2_body_focus_code(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        context = info.context if isinstance(info.context, dict) else {}
        if not context.get("v2_import"):
            return value
        try:
            code = value if isinstance(value, BodyFocusCode) else BodyFocusCode(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported V2 body focus code") from exc
        if code not in V2_BODY_FOCUS_CODES:
            raise ValueError("body focus code is not allowed in V2 artifacts")
        return code

    @field_validator("equipment_codes", mode="before")
    @classmethod
    def normalize_v2_equipment_codes(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        context = info.context if isinstance(info.context, dict) else {}
        if not context.get("v2_import"):
            return value
        if not isinstance(value, list):
            return value
        return [normalize_v2_equipment_code(code) for code in value]

    @field_validator("source_track")
    @classmethod
    def validate_exercise_source_track(cls, value: SourceTrackCode) -> SourceTrackCode:
        if value is SourceTrackCode.MERGED:
            raise ValueError("exercise records must retain their original source track")
        return value

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
    def validate_timing_fields(self, info: ValidationInfo) -> "ExerciseRecord":
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
        context = info.context if isinstance(info.context, dict) else {}
        if context.get("v2_import"):
            expected_focus = {
                TrainingTypeCode.CARDIO: BodyFocusCode.CARDIO,
                TrainingTypeCode.MOBILITY: BodyFocusCode.MOBILITY,
            }.get(self.training_type_code)
            if expected_focus is not None and self.body_focus_code is not expected_focus:
                raise ValueError("V2 cardio and mobility records require their matching focus code")
            if self.training_type_code is TrainingTypeCode.STRENGTH and self.body_focus_code in {
                BodyFocusCode.CARDIO,
                BodyFocusCode.MOBILITY,
            }:
                raise ValueError("V2 strength records cannot use cardio or mobility focus codes")
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


class ExerciseListItem(BaseModel):
    id: UUID
    name: str
    training_type_code: TrainingTypeCode
    difficulty_code: DifficultyCode
    primary_body_area_codes: list[BodyAreaCode]
    required_equipment_codes: list[EquipmentCode]
    media_asset_key: str | None = None


class ExerciseListResponse(BaseModel):
    items: list[ExerciseListItem]
    next_cursor: str | None
    catalog_version: str


class ExerciseVariantItem(BaseModel):
    exercise_id: UUID
    exercise_name: str
    required_equipment_codes: list[EquipmentCode]
    instruction_summary: str
    form_cues: list[str]
    media_asset_key: str | None = None
    goal_preservation_code: str


class ExerciseVariantsResponse(BaseModel):
    source_exercise_id: UUID
    source_required_equipment_codes: list[EquipmentCode]
    items: list[ExerciseVariantItem]
    catalog_version: str
    alternative_set_version: str | None


class DerivedArtifactVersion(CatalogInputModel):
    version_code: Annotated[str, Field(min_length=1, max_length=120)]
    status_code: CatalogVersionStatusCode


class DerivedArtifactSummary(CatalogInputModel):
    rule_records: Annotated[int, Field(ge=0)] | None = None
    exercise_records: Annotated[int, Field(ge=0)] | None = None
    pattern_scope_rules: Annotated[int, Field(ge=0)] | None = None
    exercise_scope_rules: Annotated[int, Field(ge=0)] | None = None
    alternative_records: Annotated[int, Field(ge=0)] | None = None
    sources_with_alternatives: Annotated[int, Field(ge=0)] | None = None


class DerivedArtifactManifest(CatalogInputModel):
    schema_version: Literal["1.0"]
    generator_version: Annotated[str, Field(min_length=1, max_length=80)]
    source: dict[str, Any]
    review: ManifestReview
    summary: DerivedArtifactSummary
    files: list[ManifestFile]


class SafetyRuleManifest(DerivedArtifactManifest):
    rule_set_version: DerivedArtifactVersion

    @model_validator(mode="after")
    def validate_rule_file(self) -> "SafetyRuleManifest":
        entries = [entry for entry in self.files if entry.path == "safety_rules.jsonl"]
        if len(entries) != 1 or self.summary.rule_records != entries[0].records:
            raise ValueError("manifest must describe one matching safety rule JSONL file")
        return self


class ExerciseSafetyRuleRecord(CatalogInputModel):
    body_area_code: BodyAreaCode
    body_part_role_code: BodyAreaRoleCode
    catalog_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    effect_code: Literal["EXCLUDE", "CAUTION"]
    exercise_stable_code: StableCode | None
    maximum_severity_code: Literal["MILD", "MODERATE", "SEVERE"]
    minimum_severity_code: Literal["MILD", "MODERATE", "SEVERE"]
    movement_pattern_code: MovementPatternCode | None
    reason_code: Literal["DIRECT_JOINT_LOAD", "STABILIZER_LOAD"]
    review_status_code: CatalogReviewStatusCode
    rule_scope: Literal["EXERCISE", "MOVEMENT_PATTERN"]
    rule_version: Annotated[str, Field(min_length=1, max_length=80)]
    rule_set_version_code: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    production_eligible: bool | None = None
    source_manifest_hash: Sha256 | None = None
    source_metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timezone_aware_audit_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("audit timestamps must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_scope_target(self) -> "ExerciseSafetyRuleRecord":
        if self.rule_scope == "EXERCISE":
            valid = self.exercise_stable_code is not None and self.movement_pattern_code is None
        else:
            valid = self.exercise_stable_code is None and self.movement_pattern_code is not None
        if not valid:
            raise ValueError("safety rule must target exactly the declared scope")
        severity_rank = {"MILD": 1, "MODERATE": 2, "SEVERE": 3}
        if severity_rank[self.minimum_severity_code] > severity_rank[self.maximum_severity_code]:
            raise ValueError("minimum severity must not exceed maximum severity")
        return self


class AlternativeManifest(DerivedArtifactManifest):
    alternative_set_version: DerivedArtifactVersion

    @model_validator(mode="after")
    def validate_alternative_file(self) -> "AlternativeManifest":
        entries = [entry for entry in self.files if entry.path == "alternatives.jsonl"]
        if len(entries) != 1 or self.summary.alternative_records != entries[0].records:
            raise ValueError("manifest must describe one matching alternatives JSONL file")
        return self


class ExerciseAlternativeRecord(CatalogInputModel):
    alternative_catalog_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    alternative_exercise_stable_code: StableCode
    created_at: datetime
    difficulty_delta: Literal[-1, 0]
    goal_preservation_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=80)]
    reason_code: Literal["DIFFICULTY", "EQUIPMENT", "LOCATION", "DISCOMFORT"]
    review_method_code: ReviewMethodCode
    review_status_code: CatalogReviewStatusCode
    rule_version: Annotated[str, Field(min_length=1, max_length=80)]
    source_catalog_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    source_exercise_stable_code: StableCode
    status_interpretation: ReviewStatusInterpretationCode
    alternative_set_version_code: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    production_eligible: bool | None = None
    source_manifest_hash: Sha256 | None = None
    source_metadata: dict[str, Any] | None = None
    updated_at: datetime | None = None

    @field_validator("created_at")
    @classmethod
    def validate_timezone_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include timezone information")
        return value

    @field_validator("updated_at")
    @classmethod
    def validate_timezone_aware_updated_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("updated_at must include timezone information")
        return value

    @field_validator("goal_preservation_code")
    @classmethod
    def reject_runtime_downshift_as_goal(cls, value: str) -> str:
        if value == "INTENSITY_REDUCED":
            raise ValueError("INTENSITY_REDUCED is a runtime downshift, not a preserved goal")
        return value


class PrescriptionArtifactSummary(CatalogInputModel):
    exercise_records: Annotated[int, Field(gt=0)]
    goal_tag_records: Annotated[int, Field(gt=0)]
    prescription_records: Annotated[int, Field(gt=0)]


class PrescriptionManifest(CatalogInputModel):
    schema_version: Literal["1.0"]
    generator_version: Annotated[str, Field(min_length=1, max_length=80)]
    prescription_set_version: DerivedArtifactVersion
    source: dict[str, Any]
    review: ManifestReview
    summary: PrescriptionArtifactSummary
    files: list[ManifestFile]

    @model_validator(mode="after")
    def validate_files(self) -> "PrescriptionManifest":
        entries = {entry.path: entry for entry in self.files}
        if set(entries) != {"goal_tag_links.jsonl", "prescription_profiles.jsonl"}:
            raise ValueError("prescription manifest must describe both JSONL files")
        if entries["goal_tag_links.jsonl"].records != self.summary.goal_tag_records:
            raise ValueError("goal tag count does not match manifest summary")
        if entries["prescription_profiles.jsonl"].records != self.summary.prescription_records:
            raise ValueError("prescription count does not match manifest summary")
        return self


class MediaArtifactSummary(CatalogInputModel):
    media_asset_records: Annotated[int, Field(ge=0)]


class MediaManifest(CatalogInputModel):
    schema_version: Literal["1.0"]
    generator_version: Annotated[str, Field(min_length=1, max_length=80)]
    media_set_version: DerivedArtifactVersion
    catalog_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    source: dict[str, Any]
    review: ManifestReview
    summary: MediaArtifactSummary
    files: list[ManifestFile]

    @model_validator(mode="after")
    def validate_file(self) -> "MediaManifest":
        entries = [entry for entry in self.files if entry.path == "media_assets.jsonl"]
        if len(entries) != 1 or entries[0].records != self.summary.media_asset_records:
            raise ValueError("media manifest must describe one matching media JSONL file")
        return self


class MediaAssetRecord(CatalogInputModel):
    representative_exercise_id: Annotated[
        str,
        Field(pattern=r"^(?:REX-[0-9]{6}|[a-z0-9]+(?:_[a-z0-9]+)*)$", max_length=120),
    ]
    s3_key: Annotated[
        str,
        Field(
            pattern=r"^catalog-media/[a-z0-9](?:[a-z0-9_./-]*[a-z0-9_-])?\.(?:gif|jpe?g|mp4|png|webp)$",
            max_length=500,
        ),
    ]
    media_status: Literal["AVAILABLE", "UNAVAILABLE"]
    rights_review_status: Literal["APPROVED", "PENDING", "REJECTED"]
    rights_reviewer: Annotated[str | None, Field(max_length=255)] = None
    rights_reviewed_at: datetime | None = None
    rights_evidence_reference: Annotated[str | None, Field(max_length=500)] = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("s3_key")
    @classmethod
    def validate_canonical_s3_key(cls, value: str) -> str:
        if ".." in value or "//" in value:
            raise ValueError("s3_key must be a canonical object key")
        return value

    @field_validator("rights_reviewed_at")
    @classmethod
    def validate_rights_reviewed_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("rights_reviewed_at must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_rights_evidence(self) -> "MediaAssetRecord":
        if self.rights_review_status == "APPROVED" and (
            not self.rights_reviewer
            or self.rights_reviewed_at is None
            or not self.rights_evidence_reference
        ):
            raise ValueError("approved media requires reviewer, timestamp, and evidence")
        return self


class ExerciseGoalTagRecord(CatalogInputModel):
    catalog_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    exercise_stable_code: StableCode
    goal_code: Literal["GENERAL_FITNESS"]
    role_eligibility_code: Literal["CORE", "SUPPORT", "OPTIONAL"]
    review_status_code: CatalogReviewStatusCode


class ExercisePrescriptionRecord(CatalogInputModel):
    catalog_version_code: Annotated[str, Field(min_length=1, max_length=120)]
    exercise_stable_code: StableCode
    goal_code: Literal["GENERAL_FITNESS"]
    experience_level_code: Literal["BEGINNER"]
    phase_code: Literal["WARMUP", "MAIN", "COOLDOWN"]
    sets: Annotated[int, Field(gt=0)]
    reps: Annotated[int | None, Field(gt=0)] = None
    work_seconds_per_set: Annotated[int | None, Field(gt=0)] = None
    rest_seconds_per_set: Annotated[int, Field(ge=0)]
    intensity_code: Literal["LOW", "MODERATE"]
    prescription_version: Annotated[str, Field(min_length=1, max_length=64)]
    review_status_code: CatalogReviewStatusCode

    @model_validator(mode="after")
    def validate_timing(self) -> "ExercisePrescriptionRecord":
        if (self.reps is None) == (self.work_seconds_per_set is None):
            raise ValueError("exactly one prescription timing value is required")
        return self
