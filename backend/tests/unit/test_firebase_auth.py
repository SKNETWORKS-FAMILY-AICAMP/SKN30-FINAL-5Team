from typing import Any

import pytest
from firebase_admin import auth

from backend.app.integrations.firebase_auth import (
    FirebaseAdminTokenVerifier,
    UnavailableFirebaseTokenVerifier,
    build_firebase_token_verifier,
)
from backend.app.modules.identity.ports import (
    FirebaseVerifierUnavailableError,
    InvalidFirebaseTokenError,
)


def verifier(monkeypatch: pytest.MonkeyPatch) -> FirebaseAdminTokenVerifier:
    instance = FirebaseAdminTokenVerifier("test-project")
    monkeypatch.setattr(instance, "_get_app", lambda: object())
    return instance


def test_verifies_with_revocation_check_and_returns_only_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = verifier(monkeypatch)
    captured: dict[str, Any] = {}

    def verify(token: str, *, app: object, check_revoked: bool) -> dict[str, str]:
        captured.update(token=token, app=app, check_revoked=check_revoked)
        return {"uid": "firebase-subject", "email": "must-not-cross-boundary@example.com"}

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
