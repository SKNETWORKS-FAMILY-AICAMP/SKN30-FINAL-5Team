import base64
import hashlib
import re
import secrets
from datetime import date
from typing import Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.modules.profiles.ports import (
    BirthdateDecryptionError,
    BirthdateEncryptionError,
)

_ENVELOPE_VERSION = "agcm1"
_KMS_ENVELOPE_VERSION = "kms1"
_NONCE_LENGTH = 12
_KEY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
_KMS_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,2047}$")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def _associated_data(user_id: UUID) -> bytes:
    return b"exercise-wellness:birthdate:v1:" + user_id.bytes


def _kms_encryption_context(user_id: UUID) -> dict[str, str]:
    return {
        "purpose": "exercise-wellness:birthdate:v1",
        # AWS records encryption context in CloudTrail. Bind the ciphertext to
        # the user without sending the internal UUID itself to those logs.
        "user_binding_sha256": hashlib.sha256(_associated_data(user_id)).hexdigest(),
    }


class KmsClient(Protocol):
    def encrypt(self, **kwargs: object) -> dict[str, object]: ...

    def decrypt(self, **kwargs: object) -> dict[str, object]: ...


class LocalAesGcmBirthdateCipher:
    """Local/test adapter. Production must provide a separately reviewed KMS adapter."""

    def __init__(self, key: bytes, *, key_id: str, app_env: str) -> None:
        if app_env not in {"local", "test"}:
            raise ValueError("local birthdate cipher is forbidden outside local/test")
        if len(key) != 32:
            raise ValueError("birthdate encryption key must be 32 bytes")
        if _KEY_ID_PATTERN.fullmatch(key_id) is None:
            raise ValueError("birthdate encryption key_id is invalid")
        self._cipher = AESGCM(key)
        self._key_id = key_id

    def encrypt(self, user_id: UUID, birthdate: date) -> str:
        try:
            nonce = secrets.token_bytes(_NONCE_LENGTH)
            ciphertext = self._cipher.encrypt(
                nonce,
                birthdate.isoformat().encode("ascii"),
                _associated_data(user_id),
            )
            return ":".join((_ENVELOPE_VERSION, self._key_id, _encode(nonce), _encode(ciphertext)))
        except Exception as exc:
            raise BirthdateEncryptionError from exc

    def decrypt(self, user_id: UUID, protected_value: str) -> date:
        try:
            version, key_id, encoded_nonce, encoded_ciphertext = protected_value.split(":")
            if version != _ENVELOPE_VERSION or key_id != self._key_id:
                raise ValueError
            nonce = _decode(encoded_nonce)
            if len(nonce) != _NONCE_LENGTH:
                raise ValueError
            plaintext = self._cipher.decrypt(
                nonce,
                _decode(encoded_ciphertext),
                _associated_data(user_id),
            )
            return date.fromisoformat(plaintext.decode("ascii"))
        except (InvalidTag, UnicodeError, ValueError) as exc:
            raise BirthdateDecryptionError from exc


class AwsKmsBirthdateCipher:
    """AWS KMS adapter for staging and production birthdate protection."""

    def __init__(self, client: KmsClient, *, key_id: str) -> None:
        if _KMS_KEY_ID_PATTERN.fullmatch(key_id) is None:
            raise ValueError("birthdate KMS key_id is invalid")
        self._client = client
        self._key_id = key_id

    def encrypt(self, user_id: UUID, birthdate: date) -> str:
        try:
            response = self._client.encrypt(
                KeyId=self._key_id,
                Plaintext=birthdate.isoformat().encode("ascii"),
                EncryptionContext=_kms_encryption_context(user_id),
                EncryptionAlgorithm="SYMMETRIC_DEFAULT",
            )
            ciphertext = response.get("CiphertextBlob")
            if not isinstance(ciphertext, bytes) or not ciphertext:
                raise ValueError
            return f"{_KMS_ENVELOPE_VERSION}:{_encode(ciphertext)}"
        except Exception as exc:
            raise BirthdateEncryptionError from exc

    def decrypt(self, user_id: UUID, protected_value: str) -> date:
        try:
            version, encoded_ciphertext = protected_value.split(":")
            if version != _KMS_ENVELOPE_VERSION:
                raise ValueError
            ciphertext = _decode(encoded_ciphertext)
            if not ciphertext:
                raise ValueError
            response = self._client.decrypt(
                KeyId=self._key_id,
                CiphertextBlob=ciphertext,
                EncryptionContext=_kms_encryption_context(user_id),
                EncryptionAlgorithm="SYMMETRIC_DEFAULT",
            )
            plaintext = response.get("Plaintext")
            if not isinstance(plaintext, bytes):
                raise ValueError
            return date.fromisoformat(plaintext.decode("ascii"))
        except Exception as exc:
            raise BirthdateDecryptionError from exc


__all__ = ["AwsKmsBirthdateCipher", "KmsClient", "LocalAesGcmBirthdateCipher"]
