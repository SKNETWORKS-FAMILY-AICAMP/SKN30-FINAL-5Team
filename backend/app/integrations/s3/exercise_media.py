import logging
from typing import Any, Protocol, cast

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from backend.app.core.config import Settings
from backend.app.modules.catalog.media_mapping import parse_source_identity
from backend.app.modules.catalog.service import ExerciseMediaUrlPort, NullExerciseMediaUrlProvider

logger = logging.getLogger("backend.integrations.exercise_media")


class S3Client(Protocol):
    def head_object(self, **kwargs: object) -> dict[str, Any]: ...

    def generate_presigned_url(
        self,
        ClientMethod: str,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str: ...

    def get_paginator(self, operation_name: str) -> Any: ...


class S3ExerciseMediaAdapter:
    def __init__(
        self,
        client: S3Client,
        *,
        bucket: str,
        prefix: str,
        expiry_seconds: int,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix
        self._expiry_seconds = expiry_seconds

    def list_source_object_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
                for item in page.get("Contents", []):
                    key = item.get("Key")
                    if isinstance(key, str) and key != self._prefix:
                        keys.append(key)
        except (BotoCoreError, ClientError, OSError):
            logger.warning("exercise_media_s3_list_failed")
            raise
        return tuple(sorted(keys))

    def create_url(self, source_object_key: str) -> str | None:
        if (
            not source_object_key.startswith(self._prefix)
            or parse_source_identity(source_object_key) is None
        ):
            return None
        try:
            if not self.validate_source_object(source_object_key):
                return None
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": source_object_key},
                ExpiresIn=self._expiry_seconds,
            )
        except (BotoCoreError, ClientError, OSError, ValueError):
            logger.warning("exercise_media_url_generation_failed")
            return None
        return url if isinstance(url, str) and url.startswith("https://") else None

    def validate_source_object(self, source_object_key: str) -> bool:
        if (
            not source_object_key.startswith(self._prefix)
            or parse_source_identity(source_object_key) is None
        ):
            return False
        try:
            metadata = self._client.head_object(Bucket=self._bucket, Key=source_object_key)
        except (BotoCoreError, ClientError, OSError):
            logger.warning("exercise_media_s3_head_failed")
            return False
        content_type = metadata.get("ContentType")
        return (
            isinstance(content_type, str)
            and content_type.lower().split(";", 1)[0].strip() == "image/gif"
        )


def build_s3_exercise_media_adapter(settings: Settings) -> S3ExerciseMediaAdapter | None:
    if settings.exercise_media_s3_bucket is None or settings.exercise_media_s3_region is None:
        return None
    import boto3

    # region_name alone still signs against the legacy global endpoint, and S3
    # answers a bucket outside us-east-1 with a TemporaryRedirect. Following it
    # then fails as SignatureDoesNotMatch because the signature was computed for
    # the global host, so every presigned URL was unusable. Sign against the
    # regional endpoint directly.
    region = settings.exercise_media_s3_region
    try:
        client = cast(
            S3Client,
            boto3.client(
                "s3",
                region_name=region,
                endpoint_url=f"https://s3.{region}.amazonaws.com",
            ),
        )
    except (BotoCoreError, OSError):
        logger.warning("exercise_media_s3_client_unavailable")
        return None
    return S3ExerciseMediaAdapter(
        client,
        bucket=settings.exercise_media_s3_bucket,
        prefix=settings.exercise_media_s3_prefix,
        expiry_seconds=settings.exercise_media_url_expiry_seconds,
    )


def build_exercise_media_url_provider(settings: Settings) -> ExerciseMediaUrlPort:
    return build_s3_exercise_media_adapter(settings) or NullExerciseMediaUrlProvider()


__all__ = [
    "S3ExerciseMediaAdapter",
    "build_exercise_media_url_provider",
    "build_s3_exercise_media_adapter",
]
