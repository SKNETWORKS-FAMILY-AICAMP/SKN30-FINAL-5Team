"""The deployment, not the client build, decides which terms revision applies."""

import pytest

from backend.app.modules.profiles.codes import ConsentTypeCode
from backend.app.modules.profiles.legal import (
    RETIRED_CONSENT_TYPE_CODES,
    TermsVersionMismatchError,
    TermsVersionUnavailableError,
    build_onboarding_requirements,
    validate_submitted_terms_version,
)


def test_requirements_present_only_consents_that_are_still_collected() -> None:
    requirements = build_onboarding_requirements(
        terms_version="terms-v1.0.0", consent_policy_version="consent-v1"
    )

    presented = set(requirements.required_consent_type_codes) | set(
        requirements.optional_consent_type_codes
    )
    assert presented == {
        ConsentTypeCode.GENERAL_PERSONAL_DATA,
        ConsentTypeCode.SENSITIVE_DATA,
        ConsentTypeCode.MARKETING,
    }
    # The client renders this list, so a retired code cannot reach a screen.
    assert presented.isdisjoint(RETIRED_CONSENT_TYPE_CODES)


@pytest.mark.parametrize(
    ("terms_version", "consent_policy_version"),
    [(None, "consent-v1"), ("terms-v1.0.0", None), ("", "consent-v1")],
)
def test_requirements_fail_closed_when_a_version_is_not_approved(
    terms_version: str | None, consent_policy_version: str | None
) -> None:
    """Serving a blank revision would let a client record an agreement to nothing."""

    with pytest.raises(TermsVersionUnavailableError):
        build_onboarding_requirements(
            terms_version=terms_version, consent_policy_version=consent_policy_version
        )


def test_a_stale_revision_is_rejected_once_one_is_approved() -> None:
    with pytest.raises(TermsVersionMismatchError):
        validate_submitted_terms_version("terms-v0.9.0", approved="terms-v1.0.0")


def test_the_approved_revision_is_accepted() -> None:
    validate_submitted_terms_version("terms-v1.0.0", approved="terms-v1.0.0")


def test_no_approved_revision_keeps_the_previous_behaviour() -> None:
    """The setting has to be introducible without a coordinated client release,
    so a deployment that has not approved a revision must not lock users out."""

    validate_submitted_terms_version("anything-a-client-sends", approved=None)
