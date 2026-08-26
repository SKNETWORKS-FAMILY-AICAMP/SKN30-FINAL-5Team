from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "sync_gymvisual_media.py"
spec = importlib.util.spec_from_file_location("sync_gymvisual_media", SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sync
spec.loader.exec_module(sync)


class FakeS3:
    def __init__(self, source_heads: dict[str, dict[str, object]]) -> None:
        self.objects = dict(source_heads)
        self.copies: list[tuple[str, str]] = []
        self.uploads: list[tuple[str, str]] = []

    def head_object(self, bucket: str, key: str) -> dict[str, object] | None:
        return self.objects.get(key)

    def put_object(self, bucket: str, key: str, body: Path, content_type: str) -> None:
        self.uploads.append((key, content_type))
        self.objects[key] = {
            "ContentLength": body.stat().st_size,
            "ContentType": content_type,
            "ETag": f'"uploaded-{key}"',
        }

    def copy_object(self, bucket: str, source_key: str, destination_key: str) -> None:
        self.copies.append((source_key, destination_key))
        source = self.objects[source_key]
        self.objects[destination_key] = dict(source)


class GymvisualMediaSyncTests(unittest.TestCase):
    def test_repository_local_media_has_87_exact_pairs_and_preserves_leading_zero(self) -> None:
        pairs = sync.validate_local_media()
        self.assertEqual(len(pairs), 87)
        deadlift = next(pair for pair in pairs if pair.representative_exercise_id == "REX-000004")
        self.assertEqual(deadlift.source_identity, "0032")
        self.assertEqual(deadlift.image_path.name, "0032-ila4NZS.jpg")
        self.assertEqual(deadlift.video_path.name, "0032-ila4NZS.gif")
        self.assertEqual(deadlift.image_key, "images/0032-ila4NZS.jpg")
        self.assertEqual(deadlift.video_key, "videos/0032-ila4NZS.gif")

    def test_mapping_manifest_has_only_source_traceability_columns(self) -> None:
        pairs = sync.validate_local_media()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "gymvisual_media_mapping_manifest.csv"
            sync.write_mapping_manifest(pairs, output)
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 87)
            self.assertEqual(tuple(rows[0]), sync.MAPPING_MANIFEST_COLUMNS)
            deadlift = next(row for row in rows if row["source_identity"] == "0032")
            self.assertEqual(deadlift["representative_exercise_id"], "REX-000004")
            self.assertEqual(deadlift["stable_code"], "barbell_deadlift_hip_dominant_barbell")
            self.assertEqual(deadlift["source_image_s3_key"], "images/0032-ila4NZS.jpg")
            self.assertEqual(deadlift["source_gif_s3_key"], "videos/0032-ila4NZS.gif")
            self.assertNotIn("catalog-media/", output.read_text(encoding="utf-8"))

    def test_local_validation_rejects_extra_media_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "images").mkdir()
            (root / "videos").mkdir()
            representative_path = root / "representatives.csv"
            with representative_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "representative_exercise_id",
                        "source_track",
                        "source_identity",
                        "stable_code",
                    ),
                )
                writer.writeheader()
                for source_identity in ("0032", "0041"):
                    writer.writerow(
                        {
                            "representative_exercise_id": f"REX-{int(source_identity):06d}",
                            "source_track": "gymvisual",
                            "source_identity": source_identity,
                            "stable_code": f"exercise_{source_identity}",
                        }
                    )
            for name in ("0032-a.jpg", "0041-b.jpg", "9999-extra.jpg"):
                (root / "images" / name).touch()
            for name in ("0032-a.gif", "0041-b.gif"):
                (root / "videos" / name).touch()
            raw_path = root / "exercises.json"
            raw_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "0032",
                            "image": "images/0032-a.jpg",
                            "gif_url": "videos/0032-a.gif",
                        },
                        {
                            "id": "0041",
                            "image": "images/0041-b.jpg",
                            "gif_url": "videos/0041-b.gif",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            source_path = root / "source.json"
            source_path.write_text(json.dumps({"record_count": 2}), encoding="utf-8")
            with patch.multiple(
                sync,
                REPRESENTATIVE_PATH=representative_path,
                RAW_EXERCISES_PATH=raw_path,
                RAW_SOURCE_PATH=source_path,
                IMAGE_DIR=root / "images",
                VIDEO_DIR=root / "videos",
                EXPECTED_COUNT=2,
            ):
                with self.assertRaisesRegex(sync.SyncError, "missing or extra"):
                    sync.validate_local_media()

    def test_s3_validation_and_copy_are_mocked_and_idempotent(self) -> None:
        pairs = sync.validate_local_media()
        source_heads: dict[str, dict[str, object]] = {}
        for pair in pairs:
            source_heads[pair.image_key] = {
                "ContentLength": pair.image_path.stat().st_size,
                "ContentType": "image/jpeg",
                "ETag": f'"jpg-{pair.source_identity}"',
            }
            source_heads[pair.video_key] = {
                "ContentLength": pair.video_path.stat().st_size,
                "ContentType": "image/gif",
                "ETag": f'"gif-{pair.source_identity}"',
            }
        client = FakeS3(source_heads)
        sync.validate_source_objects(pairs, client, "bucket")
        copied, reused = sync.copy_canonical_aliases(pairs, client, "bucket")
        self.assertEqual(copied, 174)
        self.assertEqual(reused, 0)
        copied_again, reused_again = sync.copy_canonical_aliases(pairs, client, "bucket")
        self.assertEqual(copied_again, 0)
        self.assertEqual(reused_again, 174)
        self.assertEqual(len(client.copies), 174)

    def test_s3_source_upload_is_idempotent_and_requires_local_bytes(self) -> None:
        pairs = sync.validate_local_media()
        source_heads = {
            pair.video_key: {
                "ContentLength": pair.video_path.stat().st_size,
                "ContentType": "image/gif",
                "ETag": f'"gif-{pair.source_identity}"',
            }
            for pair in pairs
        }
        client = FakeS3(source_heads)
        uploaded, reused, _ = sync.ensure_source_objects(pairs, client, "bucket")
        self.assertEqual(uploaded, 87)
        self.assertEqual(reused, 87)
        self.assertEqual(len(client.uploads), 87)
        uploaded_again, reused_again, _ = sync.ensure_source_objects(pairs, client, "bucket")
        self.assertEqual(uploaded_again, 0)
        self.assertEqual(reused_again, 174)

        with (
            patch.object(sync, "IMAGE_DIR", Path("/missing/images")),
            patch.object(sync, "VIDEO_DIR", Path("/missing/videos")),
        ):
            s3_only_pairs = sync.validate_local_media()
        missing = FakeS3({})
        with self.assertRaisesRegex(sync.SyncError, "no local bytes available"):
            sync.ensure_source_objects(s3_only_pairs, missing, "bucket")

    def test_source_validation_rejects_type_and_zero_length(self) -> None:
        pairs = sync.validate_local_media()
        source_heads = {
            key: {
                "ContentLength": 0,
                "ContentType": "image/jpeg" if key.startswith("images/") else "image/gif",
                "ETag": '"empty"',
            }
            for pair in pairs
            for key in (pair.image_key, pair.video_key)
        }
        with self.assertRaisesRegex(sync.SyncError, "Content-Length"):
            sync.validate_source_objects(pairs, FakeS3(source_heads), "bucket")

    def test_canonical_key_and_existing_object_conflicts_fail_closed(self) -> None:
        pairs = sync.validate_local_media()
        source_heads = {
            key: {
                "ContentLength": path.stat().st_size,
                "ContentType": expected_type,
                "ETag": f'"{key}"',
            }
            for pair in pairs
            for key, path, expected_type in (
                (pair.image_key, pair.image_path, "image/jpeg"),
                (pair.video_key, pair.video_path, "image/gif"),
            )
        }
        bad_pair = pairs[0]._replace(gif_s3_key="catalog-media/wrong/demo.gif")
        with self.assertRaisesRegex(sync.SyncError, "canonical key"):
            sync.copy_canonical_aliases([bad_pair], FakeS3(source_heads), "bucket")

        conflict_client = FakeS3(source_heads)
        conflict_client.objects[pairs[0].gif_s3_key] = {
            "ContentLength": pairs[0].video_path.stat().st_size,
            "ContentType": "image/gif",
            "ETag": '"different-object"',
        }
        with self.assertRaisesRegex(sync.SyncError, "refusing overwrite"):
            sync.copy_canonical_aliases(pairs, conflict_client, "bucket")

    def test_review_input_is_pending_and_has_metadata_columns(self) -> None:
        pairs = sync.validate_local_media()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "gymvisual_media_reviewed.csv"
            sync.write_review_csv(pairs, output, media_status="UNAVAILABLE")
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 87)
            self.assertEqual(tuple(rows[0]), sync.REVIEW_COLUMNS)
            self.assertTrue(all(row["media_status"] == "UNAVAILABLE" for row in rows))
            self.assertTrue(all(row["s3_technical_status"] == "NOT_EXECUTED" for row in rows))
            self.assertTrue(all(row["rights_review_status"] == "PENDING" for row in rows))
            self.assertTrue(all(not row["rights_reviewer"] for row in rows))
            self.assertTrue(all(not row["rights_reviewed_at"] for row in rows))

            mapping_only = Path(directory) / "mapping_only.csv"
            sync.write_review_csv(pairs, mapping_only, media_status="UNAVAILABLE")
            with mapping_only.open(encoding="utf-8", newline="") as handle:
                mapping_rows = list(csv.DictReader(handle))
            self.assertTrue(all(row["media_status"] == "UNAVAILABLE" for row in mapping_rows))

    def test_review_input_can_record_explicit_rights_approval(self) -> None:
        pairs = sync.validate_local_media()
        canonical_heads = {
            key: {
                "ContentLength": 1,
                "ContentType": "image/gif" if key.endswith("demo.gif") else "image/jpeg",
                "ETag": f'"{key}"',
            }
            for pair in pairs
            for key in (pair.gif_s3_key, pair.thumbnail_s3_key)
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "gymvisual_media_reviewed.csv"
            sync.write_review_csv(
                pairs,
                output,
                source_heads={},
                canonical_heads=canonical_heads,
                verified_at="2026-08-26T00:00:00+00:00",
                rights_review_status="APPROVED",
                rights_reviewer="Aliaksandr (Gym visual 관리자)",
                rights_reviewed_at="2026-08-18T00:00:00+09:00",
                rights_evidence_reference=(
                    "PM 메일보관함; Gym visual 관리자 Aliaksandr; "
                    "Gymvisual GIF/thumbnail 사용 허가 이메일; 2026-08-18"
                ),
            )
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 87)
            self.assertTrue(all(row["rights_review_status"] == "APPROVED" for row in rows))
            self.assertTrue(all(row["production_eligibility"] == "true" for row in rows))
            self.assertTrue(all(row["backend_visibility"] == "VISIBLE" for row in rows))


if __name__ == "__main__":
    unittest.main()
