import logging
from typing import Any, Protocol, cast

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from backend.app.core.config import Settings

logger = logging.getLogger("backend.integrations.profile_image")


class S3ProfileImageClient(Protocol):
    def put_object(self, **kwargs: object) -> dict[str, Any]: ...
    def delete_object(self, **kwargs: object) -> dict[str, Any]: ...
    def generate_presigned_url(
        self, ClientMethod: str, Params: dict[str, str], ExpiresIn: int
    ) -> str: ...


class S3ProfileImageAdapter:
    def __init__(
        self, client: S3ProfileImageClient, *, bucket: str, prefix: str, expiry_seconds: int
    ) -> None:
        self._client, self._bucket, self._prefix, self._expiry_seconds = (
            client,
            bucket,
            prefix,
            expiry_seconds,
        )

    def put(self, object_key: str, content: bytes, content_type: str) -> bool:
        if not self._valid_key(object_key):
            return False
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=object_key,
                Body=content,
                ContentType=content_type,
                CacheControl="private, max-age=300",
            )
            return True
        except (BotoCoreError, ClientError, OSError):
            logger.warning("profile_image_s3_put_failed")
            return False

    def delete(self, object_key: str) -> bool:
        if not self._valid_key(object_key):
            return False
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)
            return True
        except (BotoCoreError, ClientError, OSError):
            logger.warning("profile_image_s3_delete_failed")
            return False

    def create_url(self, object_key: str) -> str | None:
        if not self._valid_key(object_key):
            return None
        try:
            value = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=self._expiry_seconds,
            )
        except (BotoCoreError, ClientError, OSError, ValueError):
            logger.warning("profile_image_s3_presign_failed")
            return None
        return value if isinstance(value, str) and value.startswith("https://") else None

    def _valid_key(self, object_key: str) -> bool:
        return object_key.startswith(self._prefix) and ".." not in object_key


def build_s3_profile_image_adapter(settings: Settings) -> S3ProfileImageAdapter | None:
    # Deliberately reuse the reviewed bucket, but never the videos/ namespace or adapter.
    if settings.exercise_media_s3_bucket is None or settings.exercise_media_s3_region is None:
        return None
    import boto3

    region = settings.exercise_media_s3_region
    try:
        client = cast(
            S3ProfileImageClient,
            boto3.client(
                "s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com"
            ),
        )
    except (BotoCoreError, OSError):
        logger.warning("profile_image_s3_client_unavailable")
        return None
    return S3ProfileImageAdapter(
        client,
        bucket=settings.exercise_media_s3_bucket,
        prefix=settings.profile_image_s3_prefix,
        expiry_seconds=settings.profile_image_url_expiry_seconds,
    )


__all__ = ["S3ProfileImageAdapter", "build_s3_profile_image_adapter"]
