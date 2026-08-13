from hashlib import sha256
from threading import Lock
from typing import Any

import firebase_admin
from firebase_admin import auth, exceptions
from google.auth.exceptions import DefaultCredentialsError

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
    def __init__(self, project_id: str) -> None:
        normalized_project_id = project_id.strip()
        if not normalized_project_id:
            raise ValueError("project_id must not be empty")
        self._project_id = normalized_project_id
        project_hash = sha256(normalized_project_id.encode("utf-8")).hexdigest()[:16]
        self._app_name = f"exercise-wellness-{project_hash}"
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
                    app = firebase_admin.initialize_app(
                        options={"projectId": self._project_id},
                        name=self._app_name,
                    )
                except (ValueError, exceptions.FirebaseError, DefaultCredentialsError) as exc:
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
            )
        except auth.CertificateFetchError as exc:
            raise FirebaseVerifierUnavailableError from exc
        except (
            auth.ExpiredIdTokenError,
            auth.InvalidIdTokenError,
            auth.RevokedIdTokenError,
            auth.UserDisabledError,
            ValueError,
        ) as exc:
            raise InvalidFirebaseTokenError from exc
        except exceptions.FirebaseError as exc:
            raise FirebaseVerifierUnavailableError from exc

        subject = decoded.get("uid")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise InvalidFirebaseTokenError
        return VerifiedFirebaseIdentity(firebase_subject=subject)


def build_firebase_token_verifier(project_id: str | None) -> FirebaseTokenVerifier:
    if project_id is None:
        return UnavailableFirebaseTokenVerifier()
    return FirebaseAdminTokenVerifier(project_id)


__all__ = [
    "FirebaseAdminTokenVerifier",
    "UnavailableFirebaseTokenVerifier",
    "build_firebase_token_verifier",
]
