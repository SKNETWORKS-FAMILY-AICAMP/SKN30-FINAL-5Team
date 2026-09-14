"""What a client must present before it can submit onboarding.

The terms revision a user accepted is a consent record, so the deployment has to
decide it. Before this module the mobile client held the string in a constant and
told the server which revision the user had agreed to, which meant the record
said whatever the oldest installed build said.
"""

from dataclasses import dataclass

from backend.app.modules.profiles.codes import ConsentTypeCode

# Approval is required before the service may store personal and health data, so
# onboarding rejects a request that withholds either.
REQUIRED_CONSENT_TYPE_CODES: tuple[ConsentTypeCode, ...] = (
    ConsentTypeCode.GENERAL_PERSONAL_DATA,
    ConsentTypeCode.SENSITIVE_DATA,
)

# Offered, refusable, and not a precondition for using the service.
OPTIONAL_CONSENT_TYPE_CODES: tuple[ConsentTypeCode, ...] = (ConsentTypeCode.MARKETING,)

# Codes kept only so existing records stay readable. They are never presented.
# CALENDAR_INTEGRATION was retired by ADR-0016, WEARABLE_INTEGRATION by ADR-0019.
RETIRED_CONSENT_TYPE_CODES: tuple[ConsentTypeCode, ...] = (
    ConsentTypeCode.WEARABLE_INTEGRATION,
    ConsentTypeCode.CALENDAR_INTEGRATION,
)


class TermsVersionUnavailableError(Exception):
    """The deployment has not approved a terms revision to present."""


class TermsVersionMismatchError(Exception):
    """The submitted revision is not the one this deployment asks users to accept."""


@dataclass(frozen=True, slots=True)
class OnboardingRequirements:
    terms_version: str
    consent_policy_version: str
    required_consent_type_codes: tuple[ConsentTypeCode, ...]
    optional_consent_type_codes: tuple[ConsentTypeCode, ...]


def build_onboarding_requirements(
    *, terms_version: str | None, consent_policy_version: str | None
) -> OnboardingRequirements:
    """Fail closed: a client must not invent a revision when none is approved."""

    if not terms_version or not consent_policy_version:
        raise TermsVersionUnavailableError
    return OnboardingRequirements(
        terms_version=terms_version,
        consent_policy_version=consent_policy_version,
        required_consent_type_codes=REQUIRED_CONSENT_TYPE_CODES,
        optional_consent_type_codes=OPTIONAL_CONSENT_TYPE_CODES,
    )


def validate_submitted_terms_version(submitted: str, *, approved: str | None) -> None:
    """Reject a stale revision, but only once the deployment has approved one.

    A deployment without an approved revision keeps the previous behaviour rather
    than locking every client out, so this setting can be introduced without a
    coordinated release.
    """

    if approved is None:
        return
    if submitted != approved:
        raise TermsVersionMismatchError


__all__ = [
    "OPTIONAL_CONSENT_TYPE_CODES",
    "REQUIRED_CONSENT_TYPE_CODES",
    "RETIRED_CONSENT_TYPE_CODES",
    "OnboardingRequirements",
    "TermsVersionMismatchError",
    "TermsVersionUnavailableError",
    "build_onboarding_requirements",
    "validate_submitted_terms_version",
]
