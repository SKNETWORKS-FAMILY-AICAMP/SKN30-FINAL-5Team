"""Validate published catalog bundles against the schemas that import them.

The v2.0.3 publication added provenance fields to two manifests. Both schemas
forbid unknown fields, so the bundle only failed when it was imported on the
host -- after building an image and copying it there. These tests move that
failure back to the repository, where it costs seconds.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.modules.catalog.schemas import (
    AlternativeManifest,
    CatalogBundleManifest,
    CatalogManifest,
    ExerciseAlternativeRecord,
    ExerciseGoalTagRecord,
    ExercisePrescriptionRecord,
    ExerciseRecord,
    ExerciseSafetyRuleRecord,
    MediaAssetRecord,
    MediaManifest,
    PrescriptionManifest,
    SafetyRuleManifest,
)

GENERATED = Path(__file__).resolve().parents[3] / "data" / "generated"
PUBLISHED_BUNDLES = sorted(
    path.parent for path in GENERATED.glob("exercise-catalog-*/backend_bundle/bundle_manifest.json")
)

# Manifests alone were not enough: v2.0.3 shipped manifests that validated and
# records that did not, and the mismatch only surfaced on the host.
#
# Record validation covers the bundles the current v2 importer path targets.
# v2.0.0 and v2.0.1 were imported under the earlier contract and their exercise
# rows carry fields this schema no longer accepts; asserting today's shape on
# those historical artifacts would say nothing useful about a future release.
V2_RECORD_BUNDLES = [
    bundle for bundle in PUBLISHED_BUNDLES if bundle.parent.name >= "exercise-catalog-v2.0.2"
]
RECORD_SCHEMAS = (
    ("catalog/exercises.jsonl", ExerciseRecord),
    ("prescriptions/goal_tag_links.jsonl", ExerciseGoalTagRecord),
    ("prescriptions/prescription_profiles.jsonl", ExercisePrescriptionRecord),
    # v2.0.4 is the first release to add safety rules and exercise records at
    # publication time rather than carry them over, so the payloads a release
    # can now change are all covered here instead of only the prescription set.
    ("safety/safety_rules.jsonl", ExerciseSafetyRuleRecord),
    ("alternatives/alternatives.jsonl", ExerciseAlternativeRecord),
    ("media/media_assets.jsonl", MediaAssetRecord),
)

SUB_MANIFEST_SCHEMAS = (
    ("catalog/seed_manifest.json", CatalogManifest),
    ("safety/rules_manifest.json", SafetyRuleManifest),
    ("alternatives/alternatives_manifest.json", AlternativeManifest),
    ("prescriptions/prescription_manifest.json", PrescriptionManifest),
    ("media/media_manifest.json", MediaManifest),
)


def _bundle_ids() -> list[str]:
    return [bundle.parent.name for bundle in PUBLISHED_BUNDLES]


def test_at_least_one_bundle_is_published() -> None:
    # Guards the globs themselves: a rename would otherwise silently skip
    # everything and the suite would still be green.
    assert PUBLISHED_BUNDLES
    assert V2_RECORD_BUNDLES


@pytest.mark.parametrize("bundle", PUBLISHED_BUNDLES, ids=_bundle_ids())
def test_published_bundle_manifest_matches_the_importer_schema(bundle: Path) -> None:
    raw = (bundle / "bundle_manifest.json").read_text(encoding="utf-8")

    try:
        CatalogBundleManifest.model_validate_json(raw)
    except ValidationError as exc:  # pragma: no cover - failure path is the point
        pytest.fail(f"{bundle.parent.name} bundle_manifest.json is not importable: {exc}")


@pytest.mark.parametrize("bundle", PUBLISHED_BUNDLES, ids=_bundle_ids())
def test_published_sub_manifests_match_their_schemas(bundle: Path) -> None:
    for relative, schema in SUB_MANIFEST_SCHEMAS:
        path = bundle / relative
        if not path.exists():
            # media is optional; the others are covered by the importer contract.
            continue
        try:
            schema.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except ValidationError as exc:  # pragma: no cover - failure path is the point
            pytest.fail(f"{bundle.parent.name} {relative} is not importable: {exc}")


@pytest.mark.parametrize(
    "bundle", V2_RECORD_BUNDLES, ids=[bundle.parent.name for bundle in V2_RECORD_BUNDLES]
)
def test_published_records_match_their_schemas(bundle: Path) -> None:
    for relative, schema in RECORD_SCHEMAS:
        path = bundle / relative
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    schema.model_validate_json(line)
                except ValidationError as exc:  # pragma: no cover - failure is the point
                    pytest.fail(
                        f"{bundle.parent.name} {relative}:{number} is not importable: {exc}"
                    )
