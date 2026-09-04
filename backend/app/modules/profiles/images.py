from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.app.modules.profiles.codes import (
    PROFILE_IMAGE_RESPONSE_SCHEMA_VERSION,
    MutationEndpointCode,
)
from backend.app.modules.profiles.ports import ProfileRepositoryPort
from backend.app.modules.profiles.service import (
    IdempotencyKeyReusedError,
    ProfileNotFoundError,
    StaleProfileError,
)

MAX_PROFILE_IMAGE_BYTES = 10 * 1024 * 1024
_IMAGE_TYPES = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", b"RIFF"),
}


class ProfileImageStoragePort(Protocol):
    def put(self, object_key: str, content: bytes, content_type: str) -> bool: ...
    def delete(self, object_key: str) -> bool: ...
    def create_url(self, object_key: str) -> str | None: ...


class InvalidProfileImageError(Exception):
    pass


class ProfileImageStorageUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class ProfileImageMutation:
    profile_image_url: str | None
    profile_version: int
    updated_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProfileImageService:
    def __init__(
        self,
        repository: ProfileRepositoryPort,
        storage: ProfileImageStoragePort | None,
        *,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository, self._storage, self._clock, self._uuid_factory = (
            repository,
            storage,
            clock,
            uuid_factory,
        )

    def upload(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
        expected_profile_version: int,
        content_type: str | None,
        content: bytes,
    ) -> ProfileImageMutation:
        extension = self._validate(content_type, content)
        storage, now = self._require_storage(), self._clock()
        object_key = f"profile-images/{user_id}/{self._uuid_factory()}.{extension}"
        old_key: str | None = None
        try:
            with session.begin():
                request_hash = self._request_hash(
                    "POST_ME_PROFILE_IMAGE", expected_profile_version, content_type, content
                )
                existing = self._existing_response(
                    session,
                    user_id,
                    MutationEndpointCode.PROFILE_IMAGE_UPLOAD,
                    idempotency_key,
                    request_hash,
                )
                if existing is not None:
                    return existing
                current = self._repository.get_profile_image_for_update(session, user_id)
                if current is None:
                    raise ProfileNotFoundError
                if current.profile_version != expected_profile_version:
                    raise StaleProfileError
                if not storage.put(object_key, content, content_type or ""):
                    raise ProfileImageStorageUnavailableError
                old_key = current.object_key
                version, updated_at = self._repository.update_profile_image(
                    session,
                    user_id,
                    object_key=object_key,
                    content_type=content_type or "",
                    byte_size=len(content),
                    now=now,
                )
                response = ProfileImageMutation(storage.create_url(object_key), version, updated_at)
                self._save_response(
                    session,
                    user_id,
                    MutationEndpointCode.PROFILE_IMAGE_UPLOAD,
                    idempotency_key,
                    request_hash,
                    response,
                    now,
                )
        except Exception:
            storage.delete(object_key)
            raise
        if old_key is not None:
            storage.delete(old_key)
        return response

    def delete(
        self,
        session: Session,
        user_id: UUID,
        idempotency_key: UUID,
        expected_profile_version: int,
    ) -> ProfileImageMutation:
        storage, now = self._require_storage(), self._clock()
        with session.begin():
            request_hash = self._request_hash(
                "DELETE_ME_PROFILE_IMAGE", expected_profile_version, None, b""
            )
            existing = self._existing_response(
                session,
                user_id,
                MutationEndpointCode.PROFILE_IMAGE_DELETE,
                idempotency_key,
                request_hash,
            )
            if existing is not None:
                return existing
            current = self._repository.get_profile_image_for_update(session, user_id)
            if current is None:
                raise ProfileNotFoundError
            if current.profile_version != expected_profile_version:
                raise StaleProfileError
            old_key = current.object_key
            if old_key is None:
                response = ProfileImageMutation(
                    None, current.profile_version, current.updated_at or now
                )
            else:
                version, updated_at = self._repository.update_profile_image(
                    session, user_id, object_key=None, content_type=None, byte_size=None, now=now
                )
                response = ProfileImageMutation(None, version, updated_at)
            self._save_response(
                session,
                user_id,
                MutationEndpointCode.PROFILE_IMAGE_DELETE,
                idempotency_key,
                request_hash,
                response,
                now,
            )
        # Clearing DB first never returns a dangling public reference. A failed
        # physical deletion leaves a private orphan for lifecycle cleanup only.
        if old_key is not None:
            storage.delete(old_key)
        return response

    def _existing_response(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
        request_hash: str,
    ) -> ProfileImageMutation | None:
        self._repository.acquire_idempotency_lock(session, user_id, endpoint_code, idempotency_key)
        existing = self._repository.get_idempotency_record(
            session, user_id, endpoint_code, idempotency_key
        )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            raise IdempotencyKeyReusedError
        payload = existing.response_payload
        return ProfileImageMutation(
            payload.get("profile_image_url")
            if isinstance(payload.get("profile_image_url"), str)
            else None,
            int(payload["profile_version"]),
            datetime.fromisoformat(str(payload["updated_at"])),
        )

    def _save_response(
        self,
        session: Session,
        user_id: UUID,
        endpoint_code: MutationEndpointCode,
        idempotency_key: UUID,
        request_hash: str,
        response: ProfileImageMutation,
        now: datetime,
    ) -> None:
        self._repository.save_idempotency_record(
            session,
            user_id,
            endpoint_code,
            idempotency_key,
            request_hash,
            {
                "profile_image_url": response.profile_image_url,
                "profile_version": response.profile_version,
                "updated_at": response.updated_at.isoformat(),
            },
            PROFILE_IMAGE_RESPONSE_SCHEMA_VERSION,
            now,
        )

    @staticmethod
    def _request_hash(
        endpoint_code: str,
        expected_profile_version: int,
        content_type: str | None,
        content: bytes,
    ) -> str:
        digest = sha256()
        digest.update(endpoint_code.encode())
        digest.update(b"\x00")
        digest.update(str(expected_profile_version).encode())
        digest.update(b"\x00")
        digest.update((content_type or "").encode())
        digest.update(b"\x00")
        digest.update(content)
        return digest.hexdigest()

    @staticmethod
    def _validate(content_type: str | None, content: bytes) -> str:
        normalized = (content_type or "").lower().split(";", 1)[0].strip()
        expected = _IMAGE_TYPES.get(normalized)
        if expected is None or not content or len(content) > MAX_PROFILE_IMAGE_BYTES:
            raise InvalidProfileImageError
        extension, signature = expected
        if not content.startswith(signature):
            raise InvalidProfileImageError
        if normalized == "image/webp" and content[8:12] != b"WEBP":
            raise InvalidProfileImageError
        return extension

    def _require_storage(self) -> ProfileImageStoragePort:
        if self._storage is None:
            raise ProfileImageStorageUnavailableError
        return self._storage
