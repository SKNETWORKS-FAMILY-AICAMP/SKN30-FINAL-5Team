import base64
import hashlib
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.app.domain.rules.auth_provider import (
    AUTH_PROVIDER_POLICY_VERSION,
    AUTHORIZATION_FLOW_TTL,
    FORBIDDEN_IDENTITY_CLAIMS,
    IDENTITY_SOCIAL_CODE_SET_VERSION,
    MVP_PROVIDER_CODE,
    SAFE_OBSERVABILITY_FIELDS,
    AuthenticationPathCode,
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
    SecurityControlModeCode,
    UnlinkActionCode,
    claim_authorization_flow,
    classify_provider_failure,
    commit_identity_mutation,
    create_authorization_flow,
    evaluate_fixed_window_limit,
    provider_policy,
    rate_limit_key_digest,
    record_identity_unlink_failure,
    record_identity_unlink_success,
    request_identity_unlink,
    resolve_verified_subject,
    resume_identity_unlink_retry,
    validate_observability_fields,
    validate_provider_nonce,
    validate_provider_token,
    validate_requested_scopes,
)

NOW = datetime(2026, 8, 14, 4, 0, tzinfo=UTC)
FLOW_ID = UUID("4c3f8f58-c0bf-4fe7-ad2f-24787ed9e4f7")
IDENTITY_ID = UUID("ce3a9d71-95af-4242-b80c-87f838fc90bc")
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode("ascii")).digest())
    .rstrip(b"=")
    .decode("ascii")
)


def _flow() -> AuthorizationFlow:
    return create_authorization_flow(
        flow_id=FLOW_ID,
        provider_code=AuthProviderCode.KAKAO,
        state="transient-state",
        nonce="transient-nonce",
        pkce_challenge_s256=CHALLENGE,
        redirect_uri_key="mobile-login-v1",
        created_at=NOW,
    )


def _valid_evidence(**changes: object) -> ProviderTokenEvidence:
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


def test_kakao_is_selected_while_google_remains_firebase_native() -> None:
    policy = provider_policy(AuthProviderCode.GOOGLE)

    assert MVP_PROVIDER_CODE is AuthProviderCode.KAKAO
    assert IDENTITY_SOCIAL_CODE_SET_VERSION == "identity-social-v1"
    assert policy.authentication_path_code is AuthenticationPathCode.FIREBASE_NATIVE
    assert policy.allowed_scopes == frozenset()
    assert policy.state_mode_code is SecurityControlModeCode.FIREBASE_SDK_MANAGED
    assert policy.policy_version == AUTH_PROVIDER_POLICY_VERSION


def test_direct_providers_require_state_and_pkce_without_profile_scopes() -> None:
    kakao = provider_policy(AuthProviderCode.KAKAO)
    naver = provider_policy(AuthProviderCode.NAVER)

    assert kakao.allowed_scopes == naver.allowed_scopes == frozenset({"openid"})
    assert kakao.nonce_mode_code is SecurityControlModeCode.REQUIRED
    assert naver.nonce_mode_code is SecurityControlModeCode.NOT_DOCUMENTED_BY_PROVIDER
    assert kakao.pkce_mode_code is naver.pkce_mode_code is SecurityControlModeCode.REQUIRED


def test_profile_scope_is_rejected() -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        validate_requested_scopes(
            provider_code=AuthProviderCode.KAKAO,
            requested_scopes=frozenset({"openid", "profile"}),
        )

    assert captured.value.code is AuthFailureCode.INVALID_IDENTITY_SCOPE

    with pytest.raises(AuthProviderContractError) as missing_openid:
        validate_requested_scopes(
            provider_code=AuthProviderCode.KAKAO,
            requested_scopes=frozenset(),
        )

    assert missing_openid.value.code is AuthFailureCode.INVALID_IDENTITY_SCOPE


def test_authorization_flow_stores_only_digests_and_s256_challenge() -> None:
    flow = _flow()

    assert flow.expires_at == NOW + AUTHORIZATION_FLOW_TTL
    assert flow.state_digest != b"transient-state"
    assert flow.nonce_digest != b"transient-nonce"
    assert flow.pkce_challenge_s256 == CHALLENGE
    assert "transient" not in repr(flow)
    assert VERIFIER not in repr(flow)


def test_authorization_flow_is_single_use_and_expires_at_ten_minutes() -> None:
    claim = claim_authorization_flow(
        _flow(),
        returned_state="transient-state",
        returned_nonce="transient-nonce",
        code_verifier=VERIFIER,
        claimed_at=NOW + timedelta(seconds=1),
    )

    assert not hasattr(claim, "state_digest")
    assert not hasattr(claim, "pkce_challenge_s256")
    validate_provider_nonce(claim, token_nonce_claim="transient-nonce")

    with pytest.raises(AuthProviderContractError) as replay:
        claim_authorization_flow(
            None,
            returned_state="transient-state",
            returned_nonce="transient-nonce",
            code_verifier=VERIFIER,
            claimed_at=NOW + timedelta(seconds=2),
        )
    assert replay.value.code is AuthFailureCode.INVALID_OAUTH_STATE

    with pytest.raises(AuthProviderContractError) as expired:
        claim_authorization_flow(
            _flow(),
            returned_state="transient-state",
            returned_nonce="transient-nonce",
            code_verifier=VERIFIER,
            claimed_at=NOW + AUTHORIZATION_FLOW_TTL,
        )
    assert expired.value.code is AuthFailureCode.OAUTH_STATE_EXPIRED


def test_fixed_window_rate_limits_have_exact_boundaries_and_hashed_keys() -> None:
    digest = rate_limit_key_digest(
        raw_key="203.0.113.10",
        hmac_key=b"test-only-rate-limit-key",
    )
    assert digest != b"203.0.113.10"
    assert b"203.0.113.10" not in digest

    tenth = evaluate_fixed_window_limit(
        dimension_code=RateLimitDimensionCode.CLIENT_IP,
        count_before_attempt=9,
        attempted_at=NOW + timedelta(seconds=59),
        window_started_at=NOW,
    )
    eleventh = evaluate_fixed_window_limit(
        dimension_code=RateLimitDimensionCode.CLIENT_IP,
        count_before_attempt=10,
        attempted_at=NOW + timedelta(seconds=59),
        window_started_at=NOW,
    )
    reset = evaluate_fixed_window_limit(
        dimension_code=RateLimitDimensionCode.CLIENT_IP,
        count_before_attempt=10,
        attempted_at=NOW + timedelta(minutes=1),
        window_started_at=NOW,
    )
    sixtieth = evaluate_fixed_window_limit(
        dimension_code=RateLimitDimensionCode.PROVIDER_REDIRECT,
        count_before_attempt=59,
        attempted_at=NOW,
        window_started_at=NOW,
    )

    assert tenth.allowed is True
    assert eleventh.allowed is False
    assert eleventh.retry_after == timedelta(seconds=1)
    assert reset.allowed is True and reset.count_after_attempt == 1
    assert sixtieth.allowed is True and sixtieth.limit == 60


def test_wrong_pkce_verifier_is_rejected() -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        claim_authorization_flow(
            _flow(),
            returned_state="transient-state",
            returned_nonce="transient-nonce",
            code_verifier="x" * 64,
            claimed_at=NOW + timedelta(seconds=1),
        )

    assert captured.value.code is AuthFailureCode.INVALID_PKCE_VERIFIER


def test_client_returned_nonce_is_checked_before_provider_call() -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        claim_authorization_flow(
            _flow(),
            returned_state="transient-state",
            returned_nonce="wrong-nonce",
            code_verifier=VERIFIER,
            claimed_at=NOW + timedelta(seconds=1),
        )

    assert captured.value.code is AuthFailureCode.INVALID_OAUTH_STATE


def test_kakao_invalid_grant_maps_to_code_reused_without_payload() -> None:
    classified = classify_provider_failure(ProviderFailureKindCode.AUTHORIZATION_CODE_INVALID_GRANT)

    assert classified.public_error_code is AuthFailureCode.AUTHORIZATION_CODE_REUSED
    assert classified.retryable is False


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"signature_valid": False}, AuthFailureCode.INVALID_PROVIDER_TOKEN),
        ({"issuer_matches": False}, AuthFailureCode.PROVIDER_ISSUER_MISMATCH),
        ({"audience_matches": False}, AuthFailureCode.PROVIDER_AUDIENCE_MISMATCH),
        ({"token_not_expired": False}, AuthFailureCode.PROVIDER_TOKEN_EXPIRED),
        ({"nonce_matches": False}, AuthFailureCode.INVALID_OAUTH_NONCE),
        ({"provider_subject": None}, AuthFailureCode.PROVIDER_SUBJECT_MISSING),
    ],
)
def test_provider_token_fail_closed(changes: dict[str, object], expected: AuthFailureCode) -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        validate_provider_token(_valid_evidence(**changes))

    assert captured.value.code is expected


def test_valid_token_reduces_to_provider_and_subject_only() -> None:
    verified = validate_provider_token(_valid_evidence())

    assert verified.provider_code is AuthProviderCode.KAKAO
    assert verified.provider_subject == "opaque-subject"
    assert {field.name for field in fields(verified)} == {
        "provider_code",
        "provider_subject",
        "policy_version",
        "code_set_version",
    }


def test_subject_over_existing_storage_limit_fails_closed_without_truncation() -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        validate_provider_token(_valid_evidence(provider_subject="s" * 256))

    assert captured.value.code is AuthFailureCode.INVALID_PROVIDER_TOKEN


def test_identity_resolution_never_uses_profile_claims() -> None:
    existing_user = uuid4()

    repeated = resolve_verified_subject(
        existing_identity_user_id=existing_user,
        current_user_id=None,
    )
    first = resolve_verified_subject(
        existing_identity_user_id=None,
        current_user_id=None,
    )

    assert repeated.resolution_code is IdentityResolutionCode.REUSE_LINKED_USER
    assert repeated.user_id == existing_user
    assert first.resolution_code is IdentityResolutionCode.CREATE_USER_AND_LINK


def test_subject_linked_to_another_user_is_a_conflict() -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        resolve_verified_subject(
            existing_identity_user_id=uuid4(),
            current_user_id=uuid4(),
        )

    assert captured.value.code is AuthFailureCode.IDENTITY_ALREADY_LINKED


def test_mvp_does_not_link_a_new_subject_to_the_current_user() -> None:
    with pytest.raises(AuthProviderContractError) as captured:
        resolve_verified_subject(
            existing_identity_user_id=None,
            current_user_id=uuid4(),
        )

    assert captured.value.code is AuthFailureCode.EXPLICIT_IDENTITY_LINKING_NOT_SUPPORTED


def test_last_identity_cannot_be_unlinked_outside_account_deletion() -> None:
    state = IdentityLinkState(IDENTITY_ID, IdentityLinkStatusCode.ACTIVE)

    with pytest.raises(AuthProviderContractError) as captured:
        request_identity_unlink(
            state,
            active_identity_count=1,
            requested_at=NOW,
        )

    assert captured.value.code is AuthFailureCode.LAST_IDENTITY_UNLINK_FORBIDDEN

    deletion = request_identity_unlink(
        state,
        active_identity_count=1,
        requested_at=NOW,
        account_deletion=True,
    )
    assert deletion.action_code is UnlinkActionCode.CALL_PROVIDER


def test_standalone_unlink_deadline_is_inclusive() -> None:
    pending = request_identity_unlink(
        IdentityLinkState(IDENTITY_ID, IdentityLinkStatusCode.ACTIVE),
        active_identity_count=2,
        requested_at=NOW,
    ).state

    failed = record_identity_unlink_failure(
        pending,
        failed_at=NOW + timedelta(hours=24),
        retryable=True,
    )

    assert failed.status_code is IdentityLinkStatusCode.REVOCATION_FAILED_REQUIRES_REVIEW
    assert failed.next_retry_at is None


def test_unlink_timeout_retries_then_requires_review_after_fifth_attempt() -> None:
    state = request_identity_unlink(
        IdentityLinkState(IDENTITY_ID, IdentityLinkStatusCode.ACTIVE),
        active_identity_count=2,
        requested_at=NOW,
    ).state

    for attempt in range(1, 5):
        state = record_identity_unlink_failure(
            state,
            failed_at=NOW + timedelta(hours=attempt),
            retryable=True,
        )
        assert state.status_code is IdentityLinkStatusCode.REVOCATION_RETRY_PENDING
        assert state.next_retry_at is not None
        state = resume_identity_unlink_retry(
            state,
            resumed_at=state.next_retry_at,
        ).state

    state = record_identity_unlink_failure(
        state,
        failed_at=NOW + timedelta(hours=5),
        retryable=True,
    )
    assert state.attempt_count == 5
    assert state.status_code is IdentityLinkStatusCode.REVOCATION_FAILED_REQUIRES_REVIEW


def test_repeated_unlink_after_success_is_a_noop() -> None:
    pending = request_identity_unlink(
        IdentityLinkState(IDENTITY_ID, IdentityLinkStatusCode.ACTIVE),
        active_identity_count=2,
        requested_at=NOW,
    )
    revoked = record_identity_unlink_success(pending.state)

    replay = request_identity_unlink(
        revoked,
        active_identity_count=1,
        requested_at=NOW + timedelta(minutes=1),
    )

    assert replay.action_code is UnlinkActionCode.NOOP_ALREADY_REVOKED
    assert replay.state is revoked


@pytest.mark.parametrize(
    "kind",
    [
        ProviderFailureKindCode.TIMEOUT,
        ProviderFailureKindCode.HTTP_5XX,
        ProviderFailureKindCode.RATE_LIMITED,
    ],
)
def test_transient_provider_failures_share_safe_public_error(
    kind: ProviderFailureKindCode,
) -> None:
    classified = classify_provider_failure(kind)

    assert classified.public_error_code is AuthFailureCode.PROVIDER_UNAVAILABLE
    assert classified.retryable is True


def test_failed_database_commit_cannot_expose_proposed_identity() -> None:
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


def test_observability_allowlist_excludes_tokens_profiles_and_subjects() -> None:
    validate_observability_fields(SAFE_OBSERVABILITY_FIELDS)
    assert SAFE_OBSERVABILITY_FIELDS.isdisjoint(FORBIDDEN_IDENTITY_CLAIMS)

    for field_name in FORBIDDEN_IDENTITY_CLAIMS:
        with pytest.raises(AuthProviderContractError):
            validate_observability_fields(frozenset({field_name}))
