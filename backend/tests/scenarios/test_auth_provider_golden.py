import base64
import hashlib
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.app.domain.rules.auth_provider import (
    AUTH_PROVIDER_POLICY_VERSION,
    FORBIDDEN_IDENTITY_CLAIMS,
    SAFE_OBSERVABILITY_FIELDS,
    AuthFailureCode,
    AuthorizationFlow,
    AuthProviderCode,
    AuthProviderContractError,
    IdentityLinkState,
    IdentityLinkStatusCode,
    IdentityResolutionCode,
    ProviderFailureKindCode,
    ProviderTokenEvidence,
    RateLimitDimensionCode,
    UnlinkActionCode,
    claim_authorization_flow,
    classify_provider_failure,
    commit_identity_mutation,
    create_authorization_flow,
    evaluate_fixed_window_limit,
    record_identity_unlink_success,
    request_identity_unlink,
    resolve_verified_subject,
    validate_provider_nonce,
    validate_provider_token,
)

NOW = datetime(2026, 8, 14, 5, 0, tzinfo=UTC)
FLOW_ID = UUID("1d344a1a-9c1f-4350-9a25-f413caf206c4")
IDENTITY_ID = UUID("f63cb1af-cce8-4708-a8a1-838010362c83")
VERIFIER = "z" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode("ascii")).digest())
    .rstrip(b"=")
    .decode("ascii")
)


def _flow() -> AuthorizationFlow:
    return create_authorization_flow(
        flow_id=FLOW_ID,
        provider_code=AuthProviderCode.KAKAO,
        state="expected-state",
        nonce="expected-nonce",
        pkce_challenge_s256=CHALLENGE,
        redirect_uri_key="mobile-login-v1",
        created_at=NOW,
    )


def _evidence(**changes: object) -> ProviderTokenEvidence:
    values: dict[str, object] = {
        "provider_code": AuthProviderCode.KAKAO,
        "issuer_matches": True,
        "audience_matches": True,
        "signature_valid": True,
        "token_not_expired": True,
        "provider_subject": "opaque-subject",
        "nonce_matches": True,
    }
    values.update(changes)
    return ProviderTokenEvidence(**values)  # type: ignore[arg-type]


def test_golden_invalid_state_and_nonce_are_rejected_before_identity_lookup() -> None:
    with pytest.raises(AuthProviderContractError) as state_error:
        claim_authorization_flow(
            _flow(),
            returned_state="wrong-state",
            returned_nonce="expected-nonce",
            code_verifier=VERIFIER,
            claimed_at=NOW + timedelta(seconds=1),
        )
    assert state_error.value.code is AuthFailureCode.INVALID_OAUTH_STATE

    claim = claim_authorization_flow(
        _flow(),
        returned_state="expected-state",
        returned_nonce="expected-nonce",
        code_verifier=VERIFIER,
        claimed_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(AuthProviderContractError) as nonce_error:
        validate_provider_nonce(
            claim,
            token_nonce_claim="wrong-nonce",
        )
    assert nonce_error.value.code is AuthFailureCode.INVALID_OAUTH_NONCE


def test_golden_issuer_and_audience_mismatch_fail_closed() -> None:
    for changes, expected in (
        ({"issuer_matches": False}, AuthFailureCode.PROVIDER_ISSUER_MISMATCH),
        ({"audience_matches": False}, AuthFailureCode.PROVIDER_AUDIENCE_MISMATCH),
    ):
        with pytest.raises(AuthProviderContractError) as captured:
            validate_provider_token(_evidence(**changes))
        assert captured.value.code is expected


def test_golden_expired_or_tampered_token_never_resolves_identity() -> None:
    for changes, expected in (
        ({"token_not_expired": False}, AuthFailureCode.PROVIDER_TOKEN_EXPIRED),
        ({"signature_valid": False}, AuthFailureCode.INVALID_PROVIDER_TOKEN),
    ):
        with pytest.raises(AuthProviderContractError) as captured:
            validate_provider_token(_evidence(**changes))
        assert captured.value.code is expected


def test_golden_provider_timeout_and_5xx_map_to_one_retryable_public_error() -> None:
    for kind in (ProviderFailureKindCode.TIMEOUT, ProviderFailureKindCode.HTTP_5XX):
        result = classify_provider_failure(kind)
        assert result.public_error_code is AuthFailureCode.PROVIDER_UNAVAILABLE
        assert result.retryable is True


def test_golden_kakao_invalid_grant_is_a_safe_code_reuse_conflict() -> None:
    result = classify_provider_failure(ProviderFailureKindCode.AUTHORIZATION_CODE_INVALID_GRANT)

    assert result.public_error_code is AuthFailureCode.AUTHORIZATION_CODE_REUSED
    assert result.retryable is False


def test_golden_authorize_init_rate_limit_boundaries_are_deterministic() -> None:
    ip_blocked = evaluate_fixed_window_limit(
        dimension_code=RateLimitDimensionCode.CLIENT_IP,
        count_before_attempt=10,
        attempted_at=NOW + timedelta(seconds=30),
        window_started_at=NOW,
    )
    provider_redirect_blocked = evaluate_fixed_window_limit(
        dimension_code=RateLimitDimensionCode.PROVIDER_REDIRECT,
        count_before_attempt=60,
        attempted_at=NOW + timedelta(minutes=30),
        window_started_at=NOW,
    )

    assert ip_blocked.allowed is False and ip_blocked.count_after_attempt == 11
    assert provider_redirect_blocked.allowed is False
    assert provider_redirect_blocked.count_after_attempt == 61


def test_golden_missing_subject_is_rejected() -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        validate_provider_token(_evidence(provider_subject=None))

    assert captured.value.code is AuthFailureCode.PROVIDER_SUBJECT_MISSING


def test_golden_subject_uniqueness_conflict_does_not_merge_accounts() -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        resolve_verified_subject(
            existing_identity_user_id=uuid4(),
            current_user_id=uuid4(),
        )

    assert captured.value.code is AuthFailureCode.IDENTITY_ALREADY_LINKED


def test_golden_repeated_login_reuses_the_same_internal_user() -> None:
    user_id = uuid4()

    first_replay = resolve_verified_subject(
        existing_identity_user_id=user_id,
        current_user_id=None,
    )
    second_replay = resolve_verified_subject(
        existing_identity_user_id=user_id,
        current_user_id=None,
    )

    assert first_replay == second_replay
    assert first_replay.resolution_code is IdentityResolutionCode.REUSE_LINKED_USER
    assert first_replay.user_id == user_id


def test_golden_repeated_unlink_is_idempotent() -> None:
    pending = request_identity_unlink(
        IdentityLinkState(IDENTITY_ID, IdentityLinkStatusCode.ACTIVE),
        active_identity_count=2,
        requested_at=NOW,
    )
    in_progress_replay = request_identity_unlink(
        pending.state,
        active_identity_count=2,
        requested_at=NOW + timedelta(milliseconds=1),
    )
    revoked = record_identity_unlink_success(pending.state)

    replay = request_identity_unlink(
        revoked,
        active_identity_count=1,
        requested_at=NOW + timedelta(seconds=1),
    )

    assert in_progress_replay.action_code is UnlinkActionCode.NOOP_IN_PROGRESS
    assert in_progress_replay.state == pending.state
    assert replay.action_code is UnlinkActionCode.NOOP_ALREADY_REVOKED
    assert replay.state == revoked


def test_golden_database_failure_rolls_back_identity_mutation() -> None:
    original = IdentityLinkState(IDENTITY_ID, IdentityLinkStatusCode.ACTIVE)
    proposed = request_identity_unlink(
        original,
        active_identity_count=2,
        requested_at=NOW,
    ).state

    with pytest.raises(AuthProviderContractError) as captured:
        commit_identity_mutation(
            original=original,
            proposed=proposed,
            persistence_succeeded=False,
        )

    assert captured.value.code is AuthFailureCode.IDENTITY_TRANSACTION_FAILED
    assert original.status_code is IdentityLinkStatusCode.ACTIVE


def test_golden_logs_snapshots_and_errors_have_no_identity_material() -> None:
    flow = _flow()
    safe_event = {
        "event_id": uuid4(),
        "flow_id": flow.flow_id,
        "provider_code": flow.provider_code,
        "outcome_code": "REJECTED",
        "failure_code": AuthFailureCode.INVALID_OAUTH_STATE,
        "policy_version": AUTH_PROVIDER_POLICY_VERSION,
        "attempt_count": 1,
        "occurred_at": NOW,
        "latency_bucket": "LT_1S",
    }

    assert frozenset(safe_event) == SAFE_OBSERVABILITY_FIELDS
    assert frozenset(safe_event).isdisjoint(FORBIDDEN_IDENTITY_CLAIMS)
    assert frozenset(field.name for field in fields(flow)).isdisjoint(
        {
            "authorization_code",
            "access_token",
            "refresh_token",
            "id_token",
            "firebase_custom_token",
            "email",
            "name",
            "nickname",
            "raw_response",
        }
    )
