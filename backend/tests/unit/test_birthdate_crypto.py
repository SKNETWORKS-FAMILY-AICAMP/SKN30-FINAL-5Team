from datetime import date
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.core.config import Settings
from backend.app.integrations.birthdate_crypto import (
    AwsKmsBirthdateCipher,
    LocalAesGcmBirthdateCipher,
)
from backend.app.main import _build_birthdate_cipher
from backend.app.modules.profiles.ports import (
    BirthdateDecryptionError,
    BirthdateEncryptionError,
)


class _FakeKmsClient:
    def __init__(self) -> None:
        self._values: dict[bytes, tuple[bytes, dict[str, str], str]] = {}
        self.encrypt_calls: list[dict[str, object]] = []
        self.decrypt_calls: list[dict[str, object]] = []

    def encrypt(self, **kwargs: object) -> dict[str, object]:
        self.encrypt_calls.append(kwargs)
        plaintext = kwargs["Plaintext"]
        context = kwargs["EncryptionContext"]
        key_id = kwargs["KeyId"]
        assert isinstance(plaintext, bytes)
        assert isinstance(context, dict)
        assert isinstance(key_id, str)
        blob = f"opaque-kms-blob-{len(self._values) + 1}".encode()
        self._values[blob] = (plaintext, context, key_id)
        return {"CiphertextBlob": blob}

    def decrypt(self, **kwargs: object) -> dict[str, object]:
        self.decrypt_calls.append(kwargs)
        blob = kwargs["CiphertextBlob"]
        assert isinstance(blob, bytes)
        plaintext, expected_context, expected_key_id = self._values[blob]
        if kwargs["EncryptionContext"] != expected_context or kwargs["KeyId"] != expected_key_id:
            raise RuntimeError("kms rejected the request")
        return {"Plaintext": plaintext}


class _FailingKmsClient:
    def encrypt(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        raise RuntimeError("provider details must not escape")

    def decrypt(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        raise RuntimeError("provider details must not escape")


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


def test_kms_cipher_round_trip_binds_ciphertext_to_internal_user() -> None:
    client = _FakeKmsClient()
    cipher = AwsKmsBirthdateCipher(client, key_id="alias/helkki-staging-birthdate")
    user_id = uuid4()
    birthdate = date(2000, 2, 3)

    protected_value = cipher.encrypt(user_id, birthdate)

    assert protected_value.startswith("kms1:")
    assert birthdate.isoformat() not in protected_value
    assert cipher.decrypt(user_id, protected_value) == birthdate
    encrypt_context = client.encrypt_calls[0]["EncryptionContext"]
    assert encrypt_context == client.decrypt_calls[0]["EncryptionContext"]
    assert str(user_id) not in str(encrypt_context)

    with pytest.raises(BirthdateDecryptionError):
        cipher.decrypt(uuid4(), protected_value)


def test_kms_cipher_uses_the_configured_key_and_symmetric_algorithm() -> None:
    client = _FakeKmsClient()
    key_id = "arn:aws:kms:ap-northeast-2:123456789012:key/synthetic-key-id"
    cipher = AwsKmsBirthdateCipher(client, key_id=key_id)

    cipher.encrypt(uuid4(), date(2000, 2, 3))

    assert client.encrypt_calls[0]["KeyId"] == key_id
    assert client.encrypt_calls[0]["EncryptionAlgorithm"] == "SYMMETRIC_DEFAULT"


def test_kms_provider_failures_use_safe_domain_errors() -> None:
    cipher = AwsKmsBirthdateCipher(
        _FailingKmsClient(),
        key_id="alias/helkki-staging-birthdate",
    )
    protected_value = "kms1:b3BhcXVl"

    with pytest.raises(BirthdateEncryptionError) as encryption_error:
        cipher.encrypt(uuid4(), date(2000, 2, 3))
    with pytest.raises(BirthdateDecryptionError) as decryption_error:
        cipher.decrypt(uuid4(), protected_value)

    assert "provider details" not in str(encryption_error.value)
    assert protected_value not in str(decryption_error.value)


def test_staging_builds_the_kms_adapter_instead_of_disabling_onboarding() -> None:
    client = _FakeKmsClient()
    settings = Settings(
        _env_file=None,
        app_env="staging",
        birthdate_kms_key_id="alias/helkki-staging-birthdate",
        aws_region="ap-northeast-2",
    )

    cipher = _build_birthdate_cipher(settings, kms_client=client)

    assert isinstance(cipher, AwsKmsBirthdateCipher)
    user_id = uuid4()
    protected_value = cipher.encrypt(user_id, date(2000, 2, 3))
    assert cipher.decrypt(user_id, protected_value) == date(2000, 2, 3)


def test_deployed_environment_without_a_kms_key_remains_fail_closed() -> None:
    settings = Settings(
        _env_file=None,
        app_env="staging",
        birthdate_encryption_key_base64="local-key-must-not-be-used",
    )

    assert _build_birthdate_cipher(settings, kms_client=_FakeKmsClient()) is None
