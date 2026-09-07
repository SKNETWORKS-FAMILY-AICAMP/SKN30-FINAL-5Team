from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.app.modules.profiles.codes import MutationEndpointCode
from backend.app.modules.profiles.images import (
    InvalidProfileImageError,
    ProfileImageService,
    ProfileImageStorageUnavailableError,
)
from backend.app.modules.profiles.ports import IdempotencyRecord, ProfileImageRecord
from backend.app.modules.profiles.service import StaleProfileError


class FakeSession:
    def begin(self):
        return nullcontext()


class FakeRepository:
    def __init__(self) -> None:
        self.record = ProfileImageRecord(None, 1)
        self.idempotency: dict[tuple[MutationEndpointCode, UUID], IdempotencyRecord] = {}

    def get_profile_image_for_update(
        self, session: FakeSession, user_id: UUID
    ) -> ProfileImageRecord:
        del session, user_id
        return self.record

    def update_profile_image(
        self, session: FakeSession, user_id: UUID, **values: object
    ) -> tuple[int, datetime]:
        del session, user_id
        self.record = ProfileImageRecord(values["object_key"], self.record.profile_version + 1)  # type: ignore[arg-type]
        return self.record.profile_version, NOW

    def acquire_idempotency_lock(
        self, session: FakeSession, user_id: UUID, endpoint_code: MutationEndpointCode, key: UUID
    ) -> None:
        del session, user_id, endpoint_code, key

    def get_idempotency_record(
        self, session: FakeSession, user_id: UUID, endpoint_code: MutationEndpointCode, key: UUID
    ) -> IdempotencyRecord | None:
        del session, user_id
        return self.idempotency.get((endpoint_code, key))

    def save_idempotency_record(
        self,
        session: FakeSession,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        key: UUID,
        request_hash: str,
        response_payload: dict[str, object],
        response_schema_version: str,
        now: datetime,
    ) -> None:
        del session, user_id, response_schema_version, now
        self.idempotency[(endpoint_code, key)] = IdempotencyRecord(request_hash, response_payload)


class FakeStorage:
    def __init__(self, *, presign_fails: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.presign_fails = presign_fails

    def put(self, object_key: str, content: bytes, content_type: str) -> bool:
        del content_type
        self.objects[object_key] = content
        return True

    def delete(self, object_key: str) -> bool:
        self.objects.pop(object_key, None)
        return True

    def create_url(self, object_key: str) -> str | None:
        if self.presign_fails:
            return None
        return f"https://example.test/{object_key}"


NOW = datetime(2026, 9, 4, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\nvalid"


def test_upload_replaces_metadata_only_after_valid_private_object_write() -> None:
    repository, storage = FakeRepository(), FakeStorage()
    result = ProfileImageService(
        repository, storage, clock=lambda: NOW, uuid_factory=lambda: UUID(int=1)
    ).upload(FakeSession(), uuid4(), uuid4(), 1, "image/png", PNG)

    assert result.profile_version == 2
    assert result.profile_image_url.endswith("/00000000-0000-0000-0000-000000000001.png")
    assert len(storage.objects) == 1


def test_invalid_type_and_stale_replacement_do_not_change_metadata() -> None:
    repository, storage = FakeRepository(), FakeStorage()
    service = ProfileImageService(repository, storage, clock=lambda: NOW)

    with pytest.raises(InvalidProfileImageError):
        service.upload(FakeSession(), uuid4(), uuid4(), 1, "image/jpeg", PNG)
    with pytest.raises(StaleProfileError):
        service.upload(FakeSession(), uuid4(), uuid4(), 2, "image/png", PNG)

    assert repository.record == ProfileImageRecord(None, 1)
    assert storage.objects == {}


def test_upload_reuses_the_stored_response_for_the_same_idempotency_key() -> None:
    repository, storage = FakeRepository(), FakeStorage()
    user_id, idempotency_key = uuid4(), uuid4()
    service = ProfileImageService(
        repository, storage, clock=lambda: NOW, uuid_factory=lambda: UUID(int=1)
    )

    first = service.upload(FakeSession(), user_id, idempotency_key, 1, "image/png", PNG)
    replay = service.upload(FakeSession(), user_id, idempotency_key, 1, "image/png", PNG)

    assert replay == first
    assert repository.record.profile_version == 2
    assert len(storage.objects) == 1


def test_upload_fails_when_the_stored_object_cannot_be_handed_back() -> None:
    """A 200 with a null URL is indistinguishable from "no picture" to a client,
    so the upload appears to succeed while nothing changes on screen. The write
    must fail loudly instead, and must not leave the object behind."""

    repository, storage = FakeRepository(), FakeStorage(presign_fails=True)
    service = ProfileImageService(
        repository, storage, clock=lambda: NOW, uuid_factory=lambda: UUID(int=1)
    )

    with pytest.raises(ProfileImageStorageUnavailableError):
        service.upload(FakeSession(), uuid4(), uuid4(), 1, "image/png", PNG)

    # The object this call wrote is removed rather than left orphaned. The
    # metadata write is undone by `session.begin()` in production; FakeSession
    # does not model rollback, so that is not asserted here.
    assert storage.objects == {}
