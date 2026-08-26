import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.modules.catalog.schemas import MediaAssetRecord
from backend.app.modules.catalog.service import CatalogImportError, load_media_artifact


def _approved_record(**updates: object) -> dict[str, object]:
    record: dict[str, object] = {
        "representative_exercise_id": "REX-000001",
        "s3_key": "catalog-media/exercises/rex-000001.webp",
        "media_status": "AVAILABLE",
        "rights_review_status": "APPROVED",
        "rights_reviewer": "DOMAIN_REVIEWER",
        "rights_reviewed_at": datetime(2026, 8, 26, tzinfo=UTC).isoformat(),
        "rights_evidence_reference": "MEDIA-RIGHTS-2026-08-26-R01",
        "source_metadata": {"source": "synthetic-test"},
    }
    record.update(updates)
    return record


def _write_media_artifact(root: Path, records: list[dict[str, object]]) -> None:
    raw = b"".join(
        (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8") for record in records
    )
    (root / "media_assets.jsonl").write_bytes(raw)
    manifest = {
        "schema_version": "1.0",
        "generator_version": "synthetic-test-v1",
        "media_set_version": {"version_code": "media-set-v2", "status_code": "DRAFT"},
        "catalog_version_code": "exercise-catalog-v2.0.0-final",
        "source": {"kind": "synthetic-test"},
        "review": {
            "status": "DOMAIN_APPROVED",
            "review_method_code": "DOMAIN_REVIEWER",
            "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
            "production_eligible": False,
        },
        "summary": {"media_asset_records": len(records)},
        "files": [
            {
                "path": "media_assets.jsonl",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "records": len(records),
            }
        ],
    }
    (root / "media_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def test_media_pydantic_parses_approved_asset() -> None:
    parsed = MediaAssetRecord.model_validate(_approved_record())
    assert parsed.rights_review_status == "APPROVED"
    assert parsed.s3_key == "catalog-media/exercises/rex-000001.webp"


@pytest.mark.parametrize(
    "s3_key",
    (
        "s3://bucket/catalog-media/rex.webp",
        "/catalog-media/rex.webp",
        "catalog-media/../secret.webp",
        "catalog-media/rex.exe",
        "Catalog-Media/rex.webp",
    ),
)
def test_media_rejects_noncanonical_s3_key(s3_key: str) -> None:
    with pytest.raises(ValidationError):
        MediaAssetRecord.model_validate(_approved_record(s3_key=s3_key))


def test_approved_media_requires_rights_evidence() -> None:
    with pytest.raises(ValidationError, match="requires reviewer"):
        MediaAssetRecord.model_validate(_approved_record(rights_reviewer=None))


def test_media_loader_maps_rex_to_stable_code(tmp_path: Path) -> None:
    _write_media_artifact(tmp_path, [_approved_record()])

    artifact = load_media_artifact(
        tmp_path,
        representative_to_stable_code={"REX-000001": "bodyweight_squat"},
    )

    assert artifact.exercise_stable_codes == ("bodyweight_squat",)


def test_media_loader_rejects_duplicate_exercise(tmp_path: Path) -> None:
    _write_media_artifact(
        tmp_path,
        [
            _approved_record(),
            _approved_record(
                representative_exercise_id="bodyweight_squat",
                s3_key="catalog-media/exercises/bodyweight-squat.png",
            ),
        ],
    )

    with pytest.raises(CatalogImportError) as exc_info:
        load_media_artifact(
            tmp_path,
            representative_to_stable_code={"REX-000001": "bodyweight_squat"},
        )

    assert exc_info.value.code == "DUPLICATE_MEDIA"
