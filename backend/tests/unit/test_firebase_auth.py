from pathlib import Path
from typing import Any

import pytest
from firebase_admin import auth, credentials
from google.auth.exceptions import DefaultCredentialsError, InvalidValue

from backend.app.integrations import firebase_auth
from backend.app.integrations.firebase_auth import (
    FirebaseAdminTokenVerifier,
    UnavailableFirebaseTokenVerifier,
    build_firebase_token_verifier,
)
from backend.app.modules.identity.ports import (
    FirebaseVerifierUnavailableError,
    InvalidFirebaseTokenError,
)


def verifier(
    monkeypatch: pytest.MonkeyPatch,
    clock_skew_seconds: int = 0,
) -> FirebaseAdminTokenVerifier:
    instance = FirebaseAdminTokenVerifier("test-project", clock_skew_seconds)
    monkeypatch.setattr(instance, "_get_app", lambda: object())
    return instance


def test_verifies_with_revocation_check_and_returns_only_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = verifier(monkeypatch)
    captured: dict[str, Any] = {}

    def verify(
        token: str,
        *,
        app: object,
        check_revoked: bool,
        clock_skew_seconds: int,
    ) -> dict[str, str]:
        captured.update(
            token=token,
            app=app,
            check_revoked=check_revoked,
            clock_skew_seconds=clock_skew_seconds,
        )
        return {"uid": "firebase-subject", "email": "sensitive-claim-not-consumed"}

    monkeypatch.setattr(auth, "verify_id_token", verify)

    result = instance.verify_id_token("id-token")

    assert result.firebase_subject == "firebase-subject"
    assert captured["token"] == "id-token"
    assert captured["check_revoked"] is True
    assert not hasattr(result, "email")


@pytest.mark.parametrize(
    "decoded",
    [{}, {"uid": ""}, {"uid": 123}, {"uid": "x" * 256}],
)
def test_rejects_missing_or_invalid_subject(
    monkeypatch: pytest.MonkeyPatch,
    decoded: dict[str, object],
) -> None:
    instance = verifier(monkeypatch)
    monkeypatch.setattr(auth, "verify_id_token", lambda *args, **kwargs: decoded)

    with pytest.raises(InvalidFirebaseTokenError):
        instance.verify_id_token("id-token")


def test_maps_invalid_sdk_token_without_exposing_sdk_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = verifier(monkeypatch)
    secret = "secret-token-material"

    def fail(*args: object, **kwargs: object) -> None:
        raise auth.InvalidIdTokenError(secret)

    monkeypatch.setattr(auth, "verify_id_token", fail)

    with pytest.raises(InvalidFirebaseTokenError) as captured:
        instance.verify_id_token("id-token")

    assert secret not in str(captured.value)


def test_maps_certificate_failure_to_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = verifier(monkeypatch)

    def fail(*args: object, **kwargs: object) -> None:
        raise auth.CertificateFetchError("certificate unavailable", RuntimeError())

    monkeypatch.setattr(auth, "verify_id_token", fail)

    with pytest.raises(FirebaseVerifierUnavailableError):
        instance.verify_id_token("id-token")


def test_missing_project_id_builds_fail_closed_verifier() -> None:
    instance = build_firebase_token_verifier(None)

    assert isinstance(instance, UnavailableFirebaseTokenVerifier)
    with pytest.raises(FirebaseVerifierUnavailableError):
        instance.verify_id_token("id-token")


def test_passes_configured_clock_skew_to_the_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Firebase mints `iat` against Google's clock. With zero tolerance a server
    # running a second behind rejects fresh tokens as "used too early", which
    # reaches the client as an intermittent 401.
    instance = verifier(monkeypatch, clock_skew_seconds=60)
    captured: dict[str, Any] = {}

    def verify(token: str, **kwargs: object) -> dict[str, str]:
        captured.update(kwargs)
        return {"uid": "firebase-subject"}

    monkeypatch.setattr(auth, "verify_id_token", verify)

    instance.verify_id_token("id-token")

    assert captured["clock_skew_seconds"] == 60


@pytest.mark.parametrize("clock_skew_seconds", [-1, 61])
def test_rejects_a_clock_skew_the_sdk_would_refuse(clock_skew_seconds: int) -> None:
    with pytest.raises(ValueError):
        FirebaseAdminTokenVerifier("test-project", clock_skew_seconds)


def test_maps_missing_credentials_to_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Credentials resolve lazily, so this surfaces during verification. It is a
    # server misconfiguration and must not escape as an unhandled 500.
    instance = verifier(monkeypatch)

    def fail(*args: object, **kwargs: object) -> None:
        raise DefaultCredentialsError("credentials were not found")

    monkeypatch.setattr(auth, "verify_id_token", fail)

    with pytest.raises(FirebaseVerifierUnavailableError):
        instance.verify_id_token("id-token")


def test_claim_rejection_outranks_the_credential_clause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # InvalidValue subclasses DefaultCredentialsError, so ordering decides
    # whether a stale-clock token reports as a bad token or a provider outage.
    assert issubclass(InvalidValue, DefaultCredentialsError)
    instance = verifier(monkeypatch)

    def fail(*args: object, **kwargs: object) -> None:
        raise InvalidValue("Token used too early, 1787125850 < 1787125851")

    monkeypatch.setattr(auth, "verify_id_token", fail)

    with pytest.raises(InvalidFirebaseTokenError):
        instance.verify_id_token("id-token")


def test_uses_the_configured_key_instead_of_an_exported_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The SDK reads GOOGLE_APPLICATION_CREDENTIALS from the process
    # environment, which pydantic-settings never writes to. Handing the key to
    # the SDK directly is what makes a path in `.env` take effect.
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    key = tmp_path / "service-account.json"
    key.write_text("{}", encoding="utf-8")
    captured: dict[str, Any] = {}

    monkeypatch.setattr(credentials, "Certificate", lambda path: captured.setdefault("path", path))
    monkeypatch.setattr(
        firebase_auth.firebase_admin,
        "initialize_app",
        lambda **kwargs: captured.setdefault("app", kwargs) or object(),
    )
    monkeypatch.setattr(
        firebase_auth.firebase_admin,
        "get_app",
        lambda name: (_ for _ in ()).throw(ValueError(name)),
    )

    instance = FirebaseAdminTokenVerifier("test-project", 60, key)
    instance._get_app()

    assert captured["path"] == str(key)
    assert captured["app"]["credential"] is not None


def test_falls_back_to_default_credentials_when_no_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cloud deployments supply the identity through ADC, so an unset path must
    # keep the previous behaviour rather than fail.
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        firebase_auth.firebase_admin,
        "initialize_app",
        lambda **kwargs: captured.setdefault("app", kwargs) or object(),
    )
    monkeypatch.setattr(
        firebase_auth.firebase_admin,
        "get_app",
        lambda name: (_ for _ in ()).throw(ValueError(name)),
    )

    FirebaseAdminTokenVerifier("test-project")._get_app()

    assert captured["app"]["credential"] is None


def test_unreadable_key_fails_closed_as_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        firebase_auth.firebase_admin,
        "get_app",
        lambda name: (_ for _ in ()).throw(ValueError(name)),
    )
    missing = tmp_path / "absent.json"

    instance = FirebaseAdminTokenVerifier("test-project", 0, missing)

    with pytest.raises(FirebaseVerifierUnavailableError):
        instance._get_app()


def test_credentials_are_part_of_the_app_identity() -> None:
    # Same project, different credential must not reuse the first app.
    default = FirebaseAdminTokenVerifier("test-project")
    explicit = FirebaseAdminTokenVerifier("test-project", 0, Path("key.json"))

    assert default._app_name != explicit._app_name
