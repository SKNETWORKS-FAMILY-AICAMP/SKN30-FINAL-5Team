import json
from dataclasses import replace
from pathlib import Path
from shutil import copytree

import pytest

from backend.app.modules.catalog.home_equipment import (
    ApprovedExerciseReference,
    HomeEquipmentBundleValidationError,
    load_home_equipment_bundle,
    validate_bundle_references,
)

BUNDLE = Path("data/generated/home-equipment-variants-v1-final/backend_bundle")


def _references(bundle) -> dict[str, ApprovedExerciseReference]:
    stable_codes = {guide.exercise_stable_code for guide in bundle.guides}
    stable_codes.update(
        code
        for variant in bundle.variants
        for code in (variant.source_exercise_stable_code, variant.candidate_exercise_stable_code)
    )
    equipment_codes = {guide.equipment_code for guide in bundle.guides} | {
        variant.missing_equipment_code for variant in bundle.variants
    }
    return {
        stable_code: ApprovedExerciseReference("catalog-v1", frozenset(equipment_codes))
        for stable_code in stable_codes
    }


def test_loads_exactly_the_approved_guide_and_variant_records() -> None:
    bundle = load_home_equipment_bundle(BUNDLE)

    assert len(bundle.guides) == 34
    assert len(bundle.variants) == 20
    validate_bundle_references(bundle, _references(bundle))


def test_hash_tampering_fails_closed_before_any_loading_workflow(tmp_path: Path) -> None:
    copied = tmp_path / "bundle"
    copytree(BUNDLE, copied)
    guide_data = copied / "guides/substitution_guides.jsonl"
    guide_data.write_text(guide_data.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(HomeEquipmentBundleValidationError, match="MANIFEST_BYTE_MISMATCH"):
        load_home_equipment_bundle(copied)


def test_record_count_mismatch_fails_closed(tmp_path: Path) -> None:
    copied = tmp_path / "bundle"
    copytree(BUNDLE, copied)
    manifest_path = copied / "bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == "guides/substitution_guides.jsonl":
            entry["records"] = 33
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(HomeEquipmentBundleValidationError, match="MANIFEST_RECORD_COUNT_MISMATCH"):
        load_home_equipment_bundle(copied)


@pytest.mark.parametrize("field", ["review_status_code", "reason_code"])
def test_unapproved_or_non_equipment_rows_are_rejected(field: str) -> None:
    bundle = load_home_equipment_bundle(BUNDLE)
    if field == "review_status_code":
        invalid_bundle = replace(
            bundle,
            guides=(replace(bundle.guides[0], review_status_code="DRAFT"),) + bundle.guides[1:],
        )
        expected = "GUIDE_RECORD_INVALID"
    else:
        invalid_bundle = replace(
            bundle,
            variants=(replace(bundle.variants[0], reason_code="LOCATION"),) + bundle.variants[1:],
        )
        expected = "VARIANT_RECORD_INVALID"

    with pytest.raises(HomeEquipmentBundleValidationError, match=expected):
        validate_bundle_references(invalid_bundle, _references(bundle))


def test_self_reference_and_unknown_exercise_codes_are_rejected() -> None:
    bundle = load_home_equipment_bundle(BUNDLE)
    self_referencing = replace(
        bundle,
        variants=(
            replace(
                bundle.variants[0],
                candidate_exercise_stable_code=bundle.variants[0].source_exercise_stable_code,
            ),
        )
        + bundle.variants[1:],
    )
    unknown_exercise = replace(
        bundle,
        variants=(replace(bundle.variants[0], candidate_exercise_stable_code="does_not_exist"),)
        + bundle.variants[1:],
    )

    with pytest.raises(HomeEquipmentBundleValidationError, match="VARIANT_RECORD_INVALID"):
        validate_bundle_references(self_referencing, _references(bundle))
    with pytest.raises(HomeEquipmentBundleValidationError, match="EXERCISE_REFERENCE_NOT_FOUND"):
        validate_bundle_references(unknown_exercise, _references(bundle))


def test_every_review_artifact_the_registry_names_is_shipped_in_the_image() -> None:
    """The loader is fail-closed on review evidence, so the image must carry it.

    Shipping the bundle alone left the runtime failing REVIEW_ARTIFACT_MISSING,
    which surfaced as a 503 on every GET /exercises/{id}. These paths are
    resolved against the container working directory, so a path the Dockerfile
    does not copy is a path the API cannot serve.
    """

    registry = json.loads((BUNDLE / "approval" / "production_approval_registry.json").read_text())
    required = {
        path for dataset in registry["datasets"] for path in dataset["review_artifact_paths"]
    }
    assert required, "the registry must name its review evidence"

    dockerfile = Path("backend/Dockerfile").read_text(encoding="utf-8")
    for path in sorted(required):
        assert Path(path).is_file(), f"{path} is missing from the repository"
        assert path in dockerfile, f"{path} is not copied into the image"
