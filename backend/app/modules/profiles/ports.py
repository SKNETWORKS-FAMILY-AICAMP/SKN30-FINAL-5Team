from datetime import date
from typing import Protocol
from uuid import UUID


class BirthdateEncryptionError(Exception):
    """A birthdate could not be encrypted without exposing sensitive context."""


class BirthdateDecryptionError(Exception):
    """A protected birthdate could not be authenticated or decrypted."""


class BirthdateCipher(Protocol):
    def encrypt(self, user_id: UUID, birthdate: date) -> str: ...

    def decrypt(self, user_id: UUID, protected_value: str) -> date: ...


__all__ = [
    "BirthdateCipher",
    "BirthdateDecryptionError",
    "BirthdateEncryptionError",
]
