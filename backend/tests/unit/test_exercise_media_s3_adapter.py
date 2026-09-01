import logging
from typing import Any
from unittest import mock

from botocore.exceptions import ClientError

from backend.app.core.config import Settings
from backend.app.integrations.s3.exercise_media import (
    S3ExerciseMediaAdapter,
    build_s3_exercise_media_adapter,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.content_type = "image/gif"
        self.url: str | Exception = "https://signed.example/media?token=secret"
        self.head_error: Exception | None = None

    def head_object(self, **kwargs: object) -> dict[str, Any]:
        if self.head_error is not None:
            raise self.head_error
        return {"ContentType": self.content_type}

    def generate_presigned_url(
        self, ClientMethod: str, Params: dict[str, str], ExpiresIn: int
    ) -> str:
        assert ClientMethod == "get_object"
        assert Params["Key"] == "videos/0073-i6LWJok.gif"
        assert ExpiresIn == 300
        if isinstance(self.url, Exception):
            raise self.url
        return self.url

    def get_paginator(self, operation_name: str) -> object:
        raise AssertionError(operation_name)


class FakePaginator:
    def paginate(self, **kwargs: object) -> tuple[dict[str, object], ...]:
        assert kwargs == {"Bucket": "exercise-media-test", "Prefix": "videos/"}
        return (
            {"Contents": [{"Key": "videos/"}, {"Key": "videos/0073-i6LWJok.gif"}]},
            {"Contents": [{"Key": "videos/0082-LsZkfU6.gif"}]},
        )


class FakeListingS3Client(FakeS3Client):
    def get_paginator(self, operation_name: str) -> object:
        assert operation_name == "list_objects_v2"
        return FakePaginator()


def _adapter(client: FakeS3Client) -> S3ExerciseMediaAdapter:
    return S3ExerciseMediaAdapter(
        client,
        bucket="exercise-media-test",
        prefix="videos/",
        expiry_seconds=300,
    )


def test_approved_gif_object_gets_presigned_url() -> None:
    client = FakeS3Client()

    assert _adapter(client).create_url("videos/0073-i6LWJok.gif") == client.url


def test_listing_paginates_and_ignores_the_prefix_marker() -> None:
    assert _adapter(FakeListingS3Client()).list_source_object_keys() == (
        "videos/0073-i6LWJok.gif",
        "videos/0082-LsZkfU6.gif",
    )


def test_missing_wrong_mime_or_presign_failure_returns_none_without_sensitive_logs(
    caplog,
) -> None:
    client = FakeS3Client()
    client.content_type = "image/jpeg"
    assert _adapter(client).create_url("videos/0073-i6LWJok.gif") is None

    client.content_type = "image/gif"
    client.head_error = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "aws-secret-detail"}},
        "HeadObject",
    )
    with caplog.at_level(logging.WARNING, logger="backend.integrations.exercise_media"):
        assert _adapter(client).create_url("videos/0073-i6LWJok.gif") is None

    log_text = caplog.text
    assert "aws-secret-detail" not in log_text
    assert "signed.example" not in log_text
    assert "token=secret" not in log_text


def test_invalid_or_non_video_key_never_calls_s3() -> None:
    client = FakeS3Client()
    client.head_error = AssertionError("S3 must not be called")

    assert _adapter(client).create_url("images/0073-i6LWJok.gif") is None
    assert _adapter(client).create_url("videos/73-i6LWJok.gif") is None


def test_client_signs_against_the_regional_endpoint() -> None:
    """A global-endpoint signature is rejected after S3 redirects to the region.

    region_name alone leaves boto3 signing against s3.amazonaws.com, so every
    presigned URL for a bucket outside us-east-1 came back as
    SignatureDoesNotMatch once the redirect was followed.
    """

    captured: dict[str, object] = {}

    def fake_client(service: str, **kwargs: object) -> object:
        captured.update(kwargs)
        captured["service"] = service
        return object()

    settings = Settings(
        _env_file=None,
        exercise_media_s3_bucket="exercise-media-bucket",
        exercise_media_s3_region="ap-northeast-2",
    )
    with mock.patch("boto3.client", fake_client):
        build_s3_exercise_media_adapter(settings)

    assert captured["region_name"] == "ap-northeast-2"
    assert captured["endpoint_url"] == "https://s3.ap-northeast-2.amazonaws.com"
