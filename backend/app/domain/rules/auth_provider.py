"""Deterministic, provider-neutral social identity and OAuth contracts."""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

AUTH_PROVIDER_POLICY_VERSION = "auth-provider-policy-v1"
IDENTITY_SOCIAL_CODE_SET_VERSION = "identity-social-v1"
AUTHORIZATION_FLOW_TTL = timedelta(minutes=10)
IP_RATE_LIMIT = 10
IP_RATE_LIMIT_WINDOW = timedelta(minutes=1)
PROVIDER_REDIRECT_RATE_LIMIT = 60
PROVIDER_REDIRECT_RATE_LIMIT_WINDOW = timedelta(hours=1)
STANDALONE_UNLINK_DEADLINE = timedelta(hours=24)
UNLINK_RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=12),
)


class AuthProviderCode(StrEnum):
    GOOGLE = "GOOGLE"
    KAKAO = "KAKAO"
    NAVER = "NAVER"


class AuthenticationPathCode(StrEnum):
    FIREBASE_NATIVE = "FIREBASE_NATIVE"
    BACKEND_AUTHORIZATION_CODE = "BACKEND_AUTHORIZATION_CODE"


class SecurityControlModeCode(StrEnum):
    FIREBASE_SDK_MANAGED = "FIREBASE_SDK_MANAGED"
    REQUIRED = "REQUIRED"
    NOT_DOCUMENTED_BY_PROVIDER = "NOT_DOCUMENTED_BY_PROVIDER"


class AuthFailureCode(StrEnum):
    OAUTH_STATE_EXPIRED = "OAUTH_STATE_EXPIRED"
    AUTHORIZATION_CODE_REUSED = "AUTHORIZATION_CODE_REUSED"
    INVALID_OAUTH_STATE = "INVALID_OAUTH_STATE"
    INVALID_OAUTH_NONCE = "INVALID_OAUTH_NONCE"
    INVALID_PKCE_VERIFIER = "INVALID_PKCE_VERIFIER"
    INVALID_PROVIDER_TOKEN = "INVALID_PROVIDER_TOKEN"
    PROVIDER_TOKEN_EXPIRED = "PROVIDER_TOKEN_EXPIRED"
    PROVIDER_ISSUER_MISMATCH = "PROVIDER_ISSUER_MISMATCH"
    PROVIDER_AUDIENCE_MISMATCH = "PROVIDER_AUDIENCE_MISMATCH"
    PROVIDER_SUBJECT_MISSING = "PROVIDER_SUBJECT_MISSING"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    IDENTITY_ALREADY_LINKED = "IDENTITY_ALREADY_LINKED"
    EXPLICIT_IDENTITY_LINKING_NOT_SUPPORTED = "EXPLICIT_IDENTITY_LINKING_NOT_SUPPORTED"
    LAST_IDENTITY_UNLINK_FORBIDDEN = "LAST_IDENTITY_UNLINK_FORBIDDEN"
    IDENTITY_TRANSACTION_FAILED = "IDENTITY_TRANSACTION_FAILED"
    INVALID_IDENTITY_SCOPE = "INVALID_IDENTITY_SCOPE"
    UNSAFE_OBSERVABILITY_FIELD = "UNSAFE_OBSERVABILITY_FIELD"


class ProviderFailureKindCode(StrEnum):
    TIMEOUT = "TIMEOUT"
    HTTP_5XX = "HTTP_5XX"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_TOKEN = "INVALID_TOKEN"
    INVALID_CLIENT_CONFIGURATION = "INVALID_CLIENT_CONFIGURATION"
    AUTHORIZATION_CODE_INVALID_GRANT = "AUTHORIZATION_CODE_INVALID_GRANT"


class RateLimitDimensionCode(StrEnum):
    CLIENT_IP = "CLIENT_IP"
    PROVIDER_REDIRECT = "PROVIDER_REDIRECT"


class IdentityResolutionCode(StrEnum):
    CREATE_USER_AND_LINK = "CREATE_USER_AND_LINK"
    REUSE_LINKED_USER = "REUSE_LINKED_USER"
    LINK_TO_CURRENT_USER = "LINK_TO_CURRENT_USER"
    REPLAY_EXISTING_LINK = "REPLAY_EXISTING_LINK"


class IdentityLinkStatusCode(StrEnum):
    ACTIVE = "ACTIVE"
    REVOCATION_PENDING = "REVOCATION_PENDING"
    REVOCATION_RETRY_PENDING = "REVOCATION_RETRY_PENDING"
    REVOCATION_FAILED_REQUIRES_REVIEW = "REVOCATION_FAILED_REQUIRES_REVIEW"
    REVOKED = "REVOKED"


class UnlinkActionCode(StrEnum):
    CALL_PROVIDER = "CALL_PROVIDER"
    RETRY_PROVIDER = "RETRY_PROVIDER"
    NOOP_ALREADY_REVOKED = "NOOP_ALREADY_REVOKED"
    NOOP_IN_PROGRESS = "NOOP_IN_PROGRESS"


class AuthProviderContractError(ValueError):
    """A safe machine-code failure with no provider payload or secret material."""

    def __init__(self, code: AuthFailureCode) -> None:
        self.code = code
        super().__init__(code)


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")


def _require_uuid4(value: UUID, *, field_name: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise ValueError(f"{field_name} must be an opaque UUIDv4")


def _secret_digest(value: str) -> bytes:
    if not value:
        raise ValueError("transient OAuth values must not be empty")
    return hashlib.sha256(value.encode("utf-8")).digest()


def _pkce_s256(value: str) -> str:
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    provider_code: AuthProviderCode
    authentication_path_code: AuthenticationPathCode
    allowed_scopes: frozenset[str]
    state_mode_code: SecurityControlModeCode
    nonce_mode_code: SecurityControlModeCode
    pkce_mode_code: SecurityControlModeCode
    policy_version: str = AUTH_PROVIDER_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.policy_version != AUTH_PROVIDER_POLICY_VERSION:
            raise ValueError("auth provider policy version must be exact")


PROVIDER_POLICIES = {
    AuthProviderCode.GOOGLE: ProviderPolicy(
        provider_code=AuthProviderCode.GOOGLE,
        authentication_path_code=AuthenticationPathCode.FIREBASE_NATIVE,
        allowed_scopes=frozenset(),
        state_mode_code=SecurityControlModeCode.FIREBASE_SDK_MANAGED,
        nonce_mode_code=SecurityControlModeCode.FIREBASE_SDK_MANAGED,
        pkce_mode_code=SecurityControlModeCode.FIREBASE_SDK_MANAGED,
    ),
    AuthProviderCode.KAKAO: ProviderPolicy(
        provider_code=AuthProviderCode.KAKAO,
        authentication_path_code=AuthenticationPathCode.BACKEND_AUTHORIZATION_CODE,
        allowed_scopes=frozenset({"openid"}),
        state_mode_code=SecurityControlModeCode.REQUIRED,
        nonce_mode_code=SecurityControlModeCode.REQUIRED,
        pkce_mode_code=SecurityControlModeCode.REQUIRED,
    ),
    AuthProviderCode.NAVER: ProviderPolicy(
        provider_code=AuthProviderCode.NAVER,
        authentication_path_code=AuthenticationPathCode.BACKEND_AUTHORIZATION_CODE,
        allowed_scopes=frozenset({"openid"}),
        state_mode_code=SecurityControlModeCode.REQUIRED,
        nonce_mode_code=SecurityControlModeCode.NOT_DOCUMENTED_BY_PROVIDER,
        pkce_mode_code=SecurityControlModeCode.REQUIRED,
    ),
}

MVP_PROVIDER_CODE = AuthProviderCode.KAKAO


def provider_policy(provider_code: AuthProviderCode) -> ProviderPolicy:
    return PROVIDER_POLICIES[provider_code]


def validate_requested_scopes(
    *, provider_code: AuthProviderCode, requested_scopes: frozenset[str]
) -> None:
    if requested_scopes != provider_policy(provider_code).allowed_scopes:
        raise AuthProviderContractError(AuthFailureCode.INVALID_IDENTITY_SCOPE)


@dataclass(frozen=True, slots=True)
class AuthorizationFlow:
    flow_id: UUID
    provider_code: AuthProviderCode
    state_digest: bytes
    nonce_digest: bytes | None
    pkce_challenge_s256: str
    redirect_uri_key: str
    created_at: datetime
    expires_at: datetime
    policy_version: str = AUTH_PROVIDER_POLICY_VERSION

    def __post_init__(self) -> None:
        _require_uuid4(self.flow_id, field_name="flow_id")
        _require_aware(self.created_at, field_name="created_at")
        _require_aware(self.expires_at, field_name="expires_at")
        if self.expires_at != self.created_at + AUTHORIZATION_FLOW_TTL:
            raise ValueError("authorization flow must expire after ten minutes")
        if not self.redirect_uri_key or "://" in self.redirect_uri_key:
            raise ValueError("redirect_uri_key must name a server-side allowlisted URI")
        if self.policy_version != AUTH_PROVIDER_POLICY_VERSION:
            raise ValueError("auth provider policy version must be exact")


@dataclass(frozen=True, slots=True)
class AuthorizationExchangeClaim:
    """Transient evidence returned after the durable flow row is deleted."""

    flow_id: UUID
    provider_code: AuthProviderCode
    claimed_at: datetime
    expected_nonce_digest: bytes | None = dataclass_field(repr=False)

    def __post_init__(self) -> None:
        _require_uuid4(self.flow_id, field_name="flow_id")
        _require_aware(self.claimed_at, field_name="claimed_at")


def create_authorization_flow(
    *,
    flow_id: UUID,
    provider_code: AuthProviderCode,
    state: str,
    nonce: str | None,
    pkce_challenge_s256: str,
    redirect_uri_key: str,
    created_at: datetime,
) -> AuthorizationFlow:
    policy = provider_policy(provider_code)
    if policy.authentication_path_code is not AuthenticationPathCode.BACKEND_AUTHORIZATION_CODE:
        raise ValueError("Firebase-native providers do not use the backend OAuth flow")
    if policy.nonce_mode_code is SecurityControlModeCode.REQUIRED and not nonce:
        raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_NONCE)
    if len(pkce_challenge_s256) != 43:
        raise AuthProviderContractError(AuthFailureCode.INVALID_PKCE_VERIFIER)
    try:
        encoded_challenge = pkce_challenge_s256.encode("ascii")
    except UnicodeEncodeError as exc:
        raise AuthProviderContractError(AuthFailureCode.INVALID_PKCE_VERIFIER) from exc
    if any(
        character not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for character in encoded_challenge
    ):
        raise AuthProviderContractError(AuthFailureCode.INVALID_PKCE_VERIFIER)
    _require_aware(created_at, field_name="created_at")
    return AuthorizationFlow(
        flow_id=flow_id,
        provider_code=provider_code,
        state_digest=_secret_digest(state),
        nonce_digest=_secret_digest(nonce) if nonce is not None else None,
        pkce_challenge_s256=pkce_challenge_s256,
        redirect_uri_key=redirect_uri_key,
        created_at=created_at,
        expires_at=created_at + AUTHORIZATION_FLOW_TTL,
    )


def claim_authorization_flow(
    flow: AuthorizationFlow | None,
    *,
    returned_state: str,
    returned_nonce: str | None,
    code_verifier: str,
    claimed_at: datetime,
) -> AuthorizationExchangeClaim:
    _require_aware(claimed_at, field_name="claimed_at")
    if flow is None:
        raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_STATE)
    if claimed_at >= flow.expires_at:
        raise AuthProviderContractError(AuthFailureCode.OAUTH_STATE_EXPIRED)
    if not hmac.compare_digest(flow.state_digest, _secret_digest(returned_state)):
        raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_STATE)
    if flow.nonce_digest is not None:
        if returned_nonce is None or not hmac.compare_digest(
            flow.nonce_digest, _secret_digest(returned_nonce)
        ):
            raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_STATE)
    try:
        challenge = _pkce_s256(code_verifier)
    except (UnicodeEncodeError, ValueError) as exc:
        raise AuthProviderContractError(AuthFailureCode.INVALID_PKCE_VERIFIER) from exc
    if not hmac.compare_digest(flow.pkce_challenge_s256, challenge):
        raise AuthProviderContractError(AuthFailureCode.INVALID_PKCE_VERIFIER)
    return AuthorizationExchangeClaim(
        flow_id=flow.flow_id,
        provider_code=flow.provider_code,
        claimed_at=claimed_at,
        expected_nonce_digest=flow.nonce_digest,
    )


def validate_provider_nonce(
    claim: AuthorizationExchangeClaim,
    *,
    token_nonce_claim: str | None,
) -> None:
    expected = claim.expected_nonce_digest
    if expected is None:
        return
    if token_nonce_claim is None or not hmac.compare_digest(
        expected, _secret_digest(token_nonce_claim)
    ):
        raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_NONCE)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    count_after_attempt: int
    limit: int
    retry_after: timedelta | None


def rate_limit_key_digest(*, raw_key: str, hmac_key: bytes) -> bytes:
    """Return a non-reversible PostgreSQL key; raw IP/URI values must not be stored."""

    if not raw_key or not hmac_key:
        raise ValueError("rate-limit key material must not be empty")
    return hmac.new(hmac_key, raw_key.encode("utf-8"), hashlib.sha256).digest()


def evaluate_fixed_window_limit(
    *,
    dimension_code: RateLimitDimensionCode,
    count_before_attempt: int,
    attempted_at: datetime,
    window_started_at: datetime,
) -> RateLimitDecision:
    _require_aware(attempted_at, field_name="attempted_at")
    _require_aware(window_started_at, field_name="window_started_at")
    if count_before_attempt < 0:
        raise ValueError("rate-limit count cannot be negative")
    if dimension_code is RateLimitDimensionCode.CLIENT_IP:
        limit = IP_RATE_LIMIT
        duration = IP_RATE_LIMIT_WINDOW
    else:
        limit = PROVIDER_REDIRECT_RATE_LIMIT
        duration = PROVIDER_REDIRECT_RATE_LIMIT_WINDOW
    window_end = window_started_at + duration
    if attempted_at >= window_end:
        count_before_attempt = 0
        window_started_at = attempted_at
        window_end = attempted_at + duration
    count_after_attempt = count_before_attempt + 1
    allowed = count_after_attempt <= limit
    return RateLimitDecision(
        allowed=allowed,
        count_after_attempt=count_after_attempt,
        limit=limit,
        retry_after=None if allowed else window_end - attempted_at,
    )


@dataclass(frozen=True, slots=True)
class ProviderTokenEvidence:
    provider_code: AuthProviderCode
    issuer_matches: bool
    audience_matches: bool
    signature_valid: bool
    token_not_expired: bool
    provider_subject: str | None
    nonce_matches: bool | None


@dataclass(frozen=True, slots=True)
class VerifiedProviderSubject:
    provider_code: AuthProviderCode
    provider_subject: str
    policy_version: str = AUTH_PROVIDER_POLICY_VERSION
    code_set_version: str = IDENTITY_SOCIAL_CODE_SET_VERSION

    def __post_init__(self) -> None:
        if not self.provider_subject:
            raise AuthProviderContractError(AuthFailureCode.PROVIDER_SUBJECT_MISSING)
        if len(self.provider_subject) > 255:
            raise AuthProviderContractError(AuthFailureCode.INVALID_PROVIDER_TOKEN)
        if self.policy_version != AUTH_PROVIDER_POLICY_VERSION:
            raise ValueError("auth provider policy version must be exact")
        if self.code_set_version != IDENTITY_SOCIAL_CODE_SET_VERSION:
            raise ValueError("social identity code-set version must be exact")


def validate_provider_token(evidence: ProviderTokenEvidence) -> VerifiedProviderSubject:
    if not evidence.signature_valid:
        raise AuthProviderContractError(AuthFailureCode.INVALID_PROVIDER_TOKEN)
    if not evidence.issuer_matches:
        raise AuthProviderContractError(AuthFailureCode.PROVIDER_ISSUER_MISMATCH)
    if not evidence.audience_matches:
        raise AuthProviderContractError(AuthFailureCode.PROVIDER_AUDIENCE_MISMATCH)
    if not evidence.token_not_expired:
        raise AuthProviderContractError(AuthFailureCode.PROVIDER_TOKEN_EXPIRED)
    if evidence.nonce_matches is False:
        raise AuthProviderContractError(AuthFailureCode.INVALID_OAUTH_NONCE)
    if evidence.provider_subject is None:
        raise AuthProviderContractError(AuthFailureCode.PROVIDER_SUBJECT_MISSING)
    return VerifiedProviderSubject(
        provider_code=evidence.provider_code,
        provider_subject=evidence.provider_subject,
    )


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    resolution_code: IdentityResolutionCode
    user_id: UUID | None


def resolve_verified_subject(
    *,
    existing_identity_user_id: UUID | None,
    current_user_id: UUID | None,
    explicit_linking_enabled: bool = False,
) -> IdentityResolution:
    if existing_identity_user_id is not None:
        if current_user_id is not None and current_user_id != existing_identity_user_id:
            raise AuthProviderContractError(AuthFailureCode.IDENTITY_ALREADY_LINKED)
        return IdentityResolution(
            resolution_code=(
                IdentityResolutionCode.REPLAY_EXISTING_LINK
                if current_user_id is not None
                else IdentityResolutionCode.REUSE_LINKED_USER
            ),
            user_id=existing_identity_user_id,
        )
    if current_user_id is not None:
        if not explicit_linking_enabled:
            raise AuthProviderContractError(AuthFailureCode.EXPLICIT_IDENTITY_LINKING_NOT_SUPPORTED)
        return IdentityResolution(
            resolution_code=IdentityResolutionCode.LINK_TO_CURRENT_USER,
            user_id=current_user_id,
        )
    return IdentityResolution(
        resolution_code=IdentityResolutionCode.CREATE_USER_AND_LINK,
        user_id=None,
    )


@dataclass(frozen=True, slots=True)
class IdentityLinkState:
    identity_id: UUID
    status_code: IdentityLinkStatusCode
    attempt_count: int = 0
    unlink_requested_at: datetime | None = None
    next_retry_at: datetime | None = None
    failure_code: AuthFailureCode | None = None

    def __post_init__(self) -> None:
        _require_uuid4(self.identity_id, field_name="identity_id")
        if self.attempt_count < 0:
            raise ValueError("attempt_count cannot be negative")
        for field_name in ("unlink_requested_at", "next_retry_at"):
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class UnlinkDecision:
    action_code: UnlinkActionCode
    state: IdentityLinkState


def request_identity_unlink(
    state: IdentityLinkState,
    *,
    active_identity_count: int,
    requested_at: datetime,
    account_deletion: bool = False,
) -> UnlinkDecision:
    _require_aware(requested_at, field_name="requested_at")
    if state.status_code is IdentityLinkStatusCode.REVOKED:
        return UnlinkDecision(UnlinkActionCode.NOOP_ALREADY_REVOKED, state)
    if state.status_code in {
        IdentityLinkStatusCode.REVOCATION_PENDING,
        IdentityLinkStatusCode.REVOCATION_RETRY_PENDING,
        IdentityLinkStatusCode.REVOCATION_FAILED_REQUIRES_REVIEW,
    }:
        return UnlinkDecision(UnlinkActionCode.NOOP_IN_PROGRESS, state)
    if not account_deletion and active_identity_count <= 1:
        raise AuthProviderContractError(AuthFailureCode.LAST_IDENTITY_UNLINK_FORBIDDEN)
    pending = replace(
        state,
        status_code=IdentityLinkStatusCode.REVOCATION_PENDING,
        unlink_requested_at=state.unlink_requested_at or requested_at,
        next_retry_at=None,
        failure_code=None,
    )
    return UnlinkDecision(UnlinkActionCode.CALL_PROVIDER, pending)


def resume_identity_unlink_retry(
    state: IdentityLinkState,
    *,
    resumed_at: datetime,
) -> UnlinkDecision:
    _require_aware(resumed_at, field_name="resumed_at")
    if (
        state.status_code is not IdentityLinkStatusCode.REVOCATION_RETRY_PENDING
        or state.next_retry_at is None
    ):
        raise ValueError("only a scheduled unlink retry can be resumed")
    if resumed_at < state.next_retry_at:
        raise ValueError("unlink retry is not due")
    return UnlinkDecision(
        UnlinkActionCode.RETRY_PROVIDER,
        replace(
            state,
            status_code=IdentityLinkStatusCode.REVOCATION_PENDING,
            next_retry_at=None,
        ),
    )


def record_identity_unlink_success(
    state: IdentityLinkState,
) -> IdentityLinkState:
    if state.status_code is IdentityLinkStatusCode.REVOKED:
        return state
    if state.status_code not in {
        IdentityLinkStatusCode.REVOCATION_PENDING,
        IdentityLinkStatusCode.REVOCATION_RETRY_PENDING,
    }:
        raise ValueError("unlink success requires a pending revocation")
    return replace(
        state,
        status_code=IdentityLinkStatusCode.REVOKED,
        next_retry_at=None,
        failure_code=None,
    )


def record_identity_unlink_failure(
    state: IdentityLinkState,
    *,
    failed_at: datetime,
    retryable: bool,
) -> IdentityLinkState:
    _require_aware(failed_at, field_name="failed_at")
    if state.unlink_requested_at is None:
        raise ValueError("unlink failure requires unlink_requested_at")
    attempt_count = state.attempt_count + 1
    deadline = state.unlink_requested_at + STANDALONE_UNLINK_DEADLINE
    if retryable and attempt_count < len(UNLINK_RETRY_DELAYS) and failed_at < deadline:
        next_retry_at = min(failed_at + UNLINK_RETRY_DELAYS[attempt_count - 1], deadline)
        return replace(
            state,
            status_code=IdentityLinkStatusCode.REVOCATION_RETRY_PENDING,
            attempt_count=attempt_count,
            next_retry_at=next_retry_at,
            failure_code=AuthFailureCode.PROVIDER_UNAVAILABLE,
        )
    return replace(
        state,
        status_code=IdentityLinkStatusCode.REVOCATION_FAILED_REQUIRES_REVIEW,
        attempt_count=attempt_count,
        next_retry_at=None,
        failure_code=AuthFailureCode.PROVIDER_UNAVAILABLE,
    )


@dataclass(frozen=True, slots=True)
class ProviderFailureClassification:
    public_error_code: AuthFailureCode
    retryable: bool


def classify_provider_failure(
    failure_kind_code: ProviderFailureKindCode,
) -> ProviderFailureClassification:
    if failure_kind_code is ProviderFailureKindCode.AUTHORIZATION_CODE_INVALID_GRANT:
        return ProviderFailureClassification(
            public_error_code=AuthFailureCode.AUTHORIZATION_CODE_REUSED,
            retryable=False,
        )
    if failure_kind_code in {
        ProviderFailureKindCode.TIMEOUT,
        ProviderFailureKindCode.HTTP_5XX,
        ProviderFailureKindCode.RATE_LIMITED,
    }:
        return ProviderFailureClassification(
            public_error_code=AuthFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
        )
    if failure_kind_code is ProviderFailureKindCode.INVALID_TOKEN:
        return ProviderFailureClassification(
            public_error_code=AuthFailureCode.INVALID_PROVIDER_TOKEN,
            retryable=False,
        )
    return ProviderFailureClassification(
        public_error_code=AuthFailureCode.PROVIDER_UNAVAILABLE,
        retryable=False,
    )


def commit_identity_mutation[T](*, original: T, proposed: T, persistence_succeeded: bool) -> T:
    """Expose the proposed state only after the transaction commits."""

    del original
    if not persistence_succeeded:
        raise AuthProviderContractError(AuthFailureCode.IDENTITY_TRANSACTION_FAILED)
    return proposed


SAFE_OBSERVABILITY_FIELDS = frozenset(
    {
        "event_id",
        "flow_id",
        "provider_code",
        "outcome_code",
        "failure_code",
        "policy_version",
        "attempt_count",
        "occurred_at",
        "latency_bucket",
    }
)

FORBIDDEN_IDENTITY_CLAIMS = frozenset(
    {
        "authorization_code",
        "access_token",
        "refresh_token",
        "id_token",
        "firebase_custom_token",
        "email",
        "email_verified",
        "name",
        "given_name",
        "family_name",
        "nickname",
        "picture",
        "profile_image",
        "profile",
        "phone_number",
        "phone",
        "birthday",
        "birth_date",
        "date_of_birth",
        "birthyear",
        "age",
        "gender",
        "locale",
        "provider_subject",
        "firebase_subject",
        "raw_response",
        "raw_error",
        "state",
        "nonce",
        "code_verifier",
    }
)


def validate_observability_fields(field_names: frozenset[str]) -> None:
    if not field_names.issubset(SAFE_OBSERVABILITY_FIELDS):
        raise AuthProviderContractError(AuthFailureCode.UNSAFE_OBSERVABILITY_FIELD)


__all__ = [
    "AUTHORIZATION_FLOW_TTL",
    "AUTH_PROVIDER_POLICY_VERSION",
    "IDENTITY_SOCIAL_CODE_SET_VERSION",
    "IP_RATE_LIMIT",
    "IP_RATE_LIMIT_WINDOW",
    "MVP_PROVIDER_CODE",
    "PROVIDER_REDIRECT_RATE_LIMIT",
    "PROVIDER_REDIRECT_RATE_LIMIT_WINDOW",
    "FORBIDDEN_IDENTITY_CLAIMS",
    "PROVIDER_POLICIES",
    "SAFE_OBSERVABILITY_FIELDS",
    "STANDALONE_UNLINK_DEADLINE",
    "UNLINK_RETRY_DELAYS",
    "AuthFailureCode",
    "AuthProviderCode",
    "AuthProviderContractError",
    "AuthenticationPathCode",
    "AuthorizationFlow",
    "AuthorizationExchangeClaim",
    "IdentityLinkState",
    "IdentityLinkStatusCode",
    "IdentityResolutionCode",
    "ProviderFailureKindCode",
    "ProviderTokenEvidence",
    "RateLimitDecision",
    "RateLimitDimensionCode",
    "SecurityControlModeCode",
    "UnlinkActionCode",
    "classify_provider_failure",
    "commit_identity_mutation",
    "claim_authorization_flow",
    "create_authorization_flow",
    "evaluate_fixed_window_limit",
    "provider_policy",
    "rate_limit_key_digest",
    "record_identity_unlink_failure",
    "record_identity_unlink_success",
    "request_identity_unlink",
    "resume_identity_unlink_retry",
    "resolve_verified_subject",
    "validate_observability_fields",
    "validate_provider_nonce",
    "validate_provider_token",
    "validate_requested_scopes",
]
