"""Validate S3 videos/ objects and persist safe exercise source-object mappings."""

import argparse
import json
from datetime import UTC, datetime

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.config import Settings, get_settings
from backend.app.db.repositories.catalog import CatalogRepository
from backend.app.db.session import DatabaseManager
from backend.app.integrations.s3.exercise_media import build_s3_exercise_media_adapter
from backend.app.modules.catalog.media_mapping import MediaMappingReport, map_source_objects


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="persist verified mappings; otherwise only print the validation report",
    )
    return parser


def _report_payload(
    report: MediaMappingReport,
    *,
    gif_verified_count: int,
    mime_or_head_failure_count: int,
    stored_count: int,
    applied: bool,
) -> dict[str, int | bool]:
    return {
        "target_object_count": report.target_object_count,
        "mapped_count": report.mapped_count,
        "unmatched_count": report.unmatched_count,
        "duplicate_count": report.duplicate_count,
        "invalid_filename_count": report.invalid_filename_count,
        "gif_verified_count": gif_verified_count,
        "mime_or_head_failure_count": mime_or_head_failure_count,
        "stored_count": stored_count,
        "applied": applied,
    }


def main(argv: list[str] | None = None, *, settings: Settings | None = None) -> int:
    args = _parser().parse_args(argv)
    current_settings = settings or get_settings()
    adapter = build_s3_exercise_media_adapter(current_settings)
    if adapter is None:
        raise SystemExit("EXERCISE_MEDIA_S3_BUCKET and EXERCISE_MEDIA_S3_REGION must be configured")

    database = DatabaseManager(current_settings.database_url.get_secret_value())
    repository = CatalogRepository()
    try:
        with database.new_session() as session, session.begin():
            exercises = repository.list_media_mapping_exercises(session)
            if not exercises:
                print(json.dumps({"error_code": "APPROVED_CATALOG_UNAVAILABLE"}))
                return 1
            report = map_source_objects(adapter.list_source_object_keys(), exercises)
            verified = tuple(
                mapping
                for mapping in report.mappings
                if adapter.validate_source_object(mapping.source_object_key)
            )
            failed_count = report.mapped_count - len(verified)
            stored_count = 0
            if args.apply and report.duplicate_count == 0:
                stored_count = repository.store_media_source_mappings(
                    session,
                    verified,
                    verified_at=datetime.now(UTC).isoformat(),
                )
            payload = _report_payload(
                report,
                gif_verified_count=len(verified),
                mime_or_head_failure_count=failed_count,
                stored_count=stored_count,
                applied=bool(args.apply and report.duplicate_count == 0),
            )
            print(json.dumps(payload, sort_keys=True))
            return 2 if report.duplicate_count > 0 else 0
    except SQLAlchemyError:
        print(json.dumps({"error_code": "DATABASE_UNAVAILABLE"}))
        return 1
    except (BotoCoreError, ClientError, OSError):
        print(json.dumps({"error_code": "S3_UNAVAILABLE"}))
        return 1
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
