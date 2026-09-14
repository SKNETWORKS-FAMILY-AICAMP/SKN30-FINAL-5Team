from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.db.models.identity import (
    SocialOAuthAuthorizationRequest,
    SocialOAuthRateLimitWindow,
    User,
    UserIdentity,
)
from backend.app.db.repositories.identity import AI_TRIAL_DURATION
from backend.app.domain.rules.auth_provider import (
    AuthorizationFlow,
    AuthProviderCode,
    RateLimitDimensionCode,
)
from backend.app.modules.identity.codes import (
    IDENTITY_SOCIAL_CODE_SET_VERSION,
    IdentityProviderCode,
    PremiumStatusCode,
    UserStatusCode,
)
from backend.app.modules.identity.ports import IdentityUserRecord


def _lock_key(provider_code: AuthProviderCode, provider_subject: str) -> int:
    # PostgreSQL advisory locks avoid a duplicate user under simultaneous first
    # login attempts without retaining the external subject outside its row.
    from hashlib import sha256

    digest = sha256(f"social:{provider_code}:{provider_subject}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class SocialOAuthRepository:
    def consume_rate_limit(
        self,
        session: Session,
        *,
        provider_code: AuthProviderCode,
        dimension_code: RateLimitDimensionCode,
        key_digest_hex: str,
        window_started_at: datetime,
        window_seconds: int,
        attempted_at: datetime,
    ) -> int:
        statement = insert(SocialOAuthRateLimitWindow).values(
            id=uuid4(),
            provider_code=provider_code,
            dimension_code=dimension_code,
            key_digest=key_digest_hex,
            window_started_at=window_started_at,
            window_seconds=window_seconds,
            request_count=1,
            expires_at=window_started_at + timedelta(seconds=window_seconds),
            created_at=attempted_at,
            updated_at=attempted_at,
        )
        returning_statement = statement.on_conflict_do_update(
            constraint="uq_social_oauth_rate_limit_window",
            set_={
                "request_count": SocialOAuthRateLimitWindow.request_count + 1,
                "updated_at": attempted_at,
            },
        ).returning(SocialOAuthRateLimitWindow.request_count)
        count = session.scalar(returning_statement)
        if count is None:
            raise RuntimeError("social OAuth rate-limit counter did not return a count")
        return count

    def create_flow(self, session: Session, flow: AuthorizationFlow) -> None:
        session.add(
            SocialOAuthAuthorizationRequest(
                id=flow.flow_id,
                provider_code=flow.provider_code,
                state_hash=flow.state_digest.hex(),
                nonce_hash=(flow.nonce_digest or b"").hex(),
                redirect_uri_hash=flow.redirect_uri_key,
                code_challenge=flow.pkce_challenge_s256,
                code_challenge_method="S256",
                created_at=flow.created_at,
                expires_at=flow.expires_at,
            )
        )
        session.flush()

    def claim_flow(self, session: Session, state_digest_hex: str) -> AuthorizationFlow | None:
        row = session.scalar(
            select(SocialOAuthAuthorizationRequest)
            .where(SocialOAuthAuthorizationRequest.state_hash == state_digest_hex)
            .with_for_update()
        )
        if row is None:
            return None
        flow = AuthorizationFlow(
            flow_id=row.id,
            provider_code=AuthProviderCode(row.provider_code),
            state_digest=bytes.fromhex(row.state_hash),
            nonce_digest=bytes.fromhex(row.nonce_hash),
            pkce_challenge_s256=row.code_challenge,
            redirect_uri_key=row.redirect_uri_hash,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )
        session.delete(row)
        session.flush()
        return flow

    def resolve_social_identity(
        self,
        session: Session,
        *,
        provider_code: AuthProviderCode,
        provider_subject: str,
        now: datetime,
    ) -> IdentityUserRecord:
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _lock_key(provider_code, provider_subject)},
        )
        identity = session.scalar(
            select(UserIdentity)
            .where(
                UserIdentity.provider_code == provider_code,
                UserIdentity.provider_subject == provider_subject,
                UserIdentity.revoked_at.is_(None),
            )
            .with_for_update()
        )
        if identity is not None:
            user = session.get(User, identity.user_id)
            if user is None:
                raise RuntimeError("active social identity user does not exist")
            user.last_active_at = now
            user.updated_at = now
            return IdentityUserRecord(user.id, UserStatusCode(user.status_code), now)

        user_id = uuid4()
        firebase_subject = str(user_id)
        user = User(
            id=user_id,
            status_code=UserStatusCode.ACTIVE,
            code_set_version=IDENTITY_SOCIAL_CODE_SET_VERSION,
            last_active_at=now,
            ai_trial_started_at=now,
            ai_trial_ends_at=now + AI_TRIAL_DURATION,
            premium_status_code=PremiumStatusCode.NOT_AVAILABLE,
        )
        identity = UserIdentity(
            id=uuid4(),
            user=user,
            provider_code=IdentityProviderCode(provider_code),
            provider_subject=provider_subject,
            firebase_subject=firebase_subject,
            code_set_version=IDENTITY_SOCIAL_CODE_SET_VERSION,
        )
        session.add_all((user, identity))
        session.flush()
        return IdentityUserRecord(user_id, UserStatusCode.ACTIVE, now)


__all__ = ["SocialOAuthRepository"]
