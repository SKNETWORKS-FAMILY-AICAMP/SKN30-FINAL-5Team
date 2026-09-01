from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials, exceptions
from google.auth.exceptions import DefaultCredentialsError, InvalidValue

from backend.app.modules.identity.ports import (
    FirebaseTokenVerifier,
    FirebaseVerifierUnavailableError,
    InvalidFirebaseTokenError,
    VerifiedFirebaseIdentity,
)

_APP_INITIALIZATION_LOCK = Lock()


class UnavailableFirebaseTokenVerifier:
    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        del token
        raise FirebaseVerifierUnavailableError


class FirebaseAdminTokenVerifier:
    def __init__(
        self,
        project_id: str,
        clock_skew_seconds: int = 0,
        credentials_path: Path | None = None,
    ) -> None:
        normalized_project_id = project_id.strip()
        if not normalized_project_id:
            raise ValueError("project_id must not be empty")
        if not 0 <= clock_skew_seconds <= 60:
            raise ValueError("clock_skew_seconds must be within [0, 60]")
        self._project_id = normalized_project_id
        self._clock_skew_seconds = clock_skew_seconds
        self._credentials_path = credentials_path
        # The credential is part of the app's identity: two verifiers for one
        # project but different credentials must not silently share the first
        # app that happened to be initialized.
        identity = f"{normalized_project_id}|{credentials_path or ''}"
        identity_hash = sha256(identity.encode("utf-8")).hexdigest()[:16]
        self._app_name = f"exercise-wellness-{identity_hash}"
        self._app: firebase_admin.App | None = None

    def _get_app(self) -> firebase_admin.App:
        if self._app is not None:
            return self._app

        with _APP_INITIALIZATION_LOCK:
            if self._app is not None:
                return self._app
            try:
                app = firebase_admin.get_app(self._app_name)
            except ValueError:
                try:
                    # An explicit key removes the dependency on an exported
                    # GOOGLE_APPLICATION_CREDENTIALS. Without one the SDK
                    # resolves Application Default Credentials, which is how
                    # cloud deployments supply the identity.
                    credential = (
                        credentials.Certificate(str(self._credentials_path))
                        if self._credentials_path is not None
                        else None
                    )
                    app = firebase_admin.initialize_app(
                        credential=credential,
                        options={"projectId": self._project_id},
                        name=self._app_name,
                    )
                except (
                    OSError,
                    ValueError,
                    exceptions.FirebaseError,
                    DefaultCredentialsError,
                ) as exc:
                    # A missing or malformed key file is a server
                    # misconfiguration, and this verifier fails closed on it.
                    raise FirebaseVerifierUnavailableError from exc
            self._app = app
            return app

    def verify_id_token(self, token: str) -> VerifiedFirebaseIdentity:
        if not token.strip():
            raise InvalidFirebaseTokenError

        app = self._get_app()
        try:
            decoded: dict[str, Any] = auth.verify_id_token(
                token,
                app=app,
                check_revoked=True,
                clock_skew_seconds=self._clock_skew_seconds,
            )
        except auth.CertificateFetchError as exc:
            raise FirebaseVerifierUnavailableError from exc
        except (
            auth.ExpiredIdTokenError,
            auth.InvalidIdTokenError,
            auth.RevokedIdTokenError,
            auth.UserDisabledError,
            # `google.auth` derives InvalidValue from DefaultCredentialsError,
            # so a claim rejection must be classified before the credential
            # clause below or a bad token would report as a provider outage.
            InvalidValue,
        ) as exc:
            raise InvalidFirebaseTokenError from exc
        except DefaultCredentialsError as exc:
            # Credentials resolve lazily, so a deployment without them fails
            # here rather than at initialization. That is a server
            # misconfiguration, not a rejected token: it must not read as a bad
            # credential, and it must not escape as an unhandled 500.
            raise FirebaseVerifierUnavailableError from exc
        except ValueError as exc:
            raise InvalidFirebaseTokenError from exc
        except exceptions.FirebaseError as exc:
            raise FirebaseVerifierUnavailableError from exc

        subject = decoded.get("uid")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise InvalidFirebaseTokenError
        return VerifiedFirebaseIdentity(firebase_subject=subject)


def build_firebase_token_verifier(
    project_id: str | None,
    clock_skew_seconds: int = 0,
    credentials_path: Path | None = None,
) -> FirebaseTokenVerifier:
    if project_id is None:
        return UnavailableFirebaseTokenVerifier()
    return FirebaseAdminTokenVerifier(project_id, clock_skew_seconds, credentials_path)


__all__ = [
    "FirebaseAdminTokenVerifier",
    "UnavailableFirebaseTokenVerifier",
    "build_firebase_token_verifier",
]
