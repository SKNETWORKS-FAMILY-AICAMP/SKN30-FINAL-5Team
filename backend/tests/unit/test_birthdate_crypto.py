from datetime import date
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.integrations.birthdate_crypto import LocalAesGcmBirthdateCipher
from backend.app.modules.profiles.ports import BirthdateDecryptionError


@pytest.fixture
def cipher() -> LocalAesGcmBirthdateCipher:
    return LocalAesGcmBirthdateCipher(
        AESGCM.generate_key(bit_length=256),
        key_id="unit-test-v1",
        app_env="test",
    )


def test_encrypts_and_decrypts_for_the_same_user(
    cipher: LocalAesGcmBirthdateCipher,
) -> None:
    user_id = uuid4()
    birthdate = date(2000, 2, 3)

    protected_value = cipher.encrypt(user_id, birthdate)

    assert cipher.decrypt(user_id, protected_value) == birthdate
    assert birthdate.isoformat() not in protected_value


def test_same_birthdate_uses_a_fresh_nonce(cipher: LocalAesGcmBirthdateCipher) -> None:
    user_id = uuid4()
    birthdate = date(2000, 2, 3)

    first = cipher.encrypt(user_id, birthdate)
    second = cipher.encrypt(user_id, birthdate)

    assert first != second


def test_ciphertext_is_bound_to_internal_user(cipher: LocalAesGcmBirthdateCipher) -> None:
    protected_value = cipher.encrypt(uuid4(), date(2000, 2, 3))

    with pytest.raises(BirthdateDecryptionError):
        cipher.decrypt(uuid4(), protected_value)


def test_tampered_ciphertext_is_rejected_without_echoing_value(
    cipher: LocalAesGcmBirthdateCipher,
) -> None:
    user_id = uuid4()
    protected_value = cipher.encrypt(user_id, date(2000, 2, 3))
    envelope_parts = protected_value.split(":")
    encoded_ciphertext = envelope_parts[3]
    envelope_parts[3] = ("A" if encoded_ciphertext[0] != "A" else "B") + encoded_ciphertext[1:]
    tampered = ":".join(envelope_parts)

    with pytest.raises(BirthdateDecryptionError) as captured:
        cipher.decrypt(user_id, tampered)

    assert tampered not in str(captured.value)


@pytest.mark.parametrize("key_length", [0, 16, 24, 31, 33])
def test_requires_256_bit_key(key_length: int) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        LocalAesGcmBirthdateCipher(
            b"x" * key_length,
            key_id="unit-test-v1",
            app_env="test",
        )


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_local_adapter_is_forbidden_in_deployed_environments(app_env: str) -> None:
    with pytest.raises(ValueError, match="forbidden"):
        LocalAesGcmBirthdateCipher(
            AESGCM.generate_key(bit_length=256),
            key_id="unit-test-v1",
            app_env=app_env,
        )


def test_wrong_key_id_is_rejected_without_decryption_attempt(
    cipher: LocalAesGcmBirthdateCipher,
) -> None:
    user_id = uuid4()
    protected_value = cipher.encrypt(user_id, date(2000, 2, 3))
    other_cipher = LocalAesGcmBirthdateCipher(
        AESGCM.generate_key(bit_length=256),
        key_id="unit-test-v2",
        app_env="test",
    )

    with pytest.raises(BirthdateDecryptionError):
        other_cipher.decrypt(user_id, protected_value)
