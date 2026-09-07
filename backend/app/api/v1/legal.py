from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_current_user
from backend.app.core.errors import AppError
from backend.app.modules.identity.service import CurrentUser
from backend.app.modules.profiles.legal import (
    TermsVersionUnavailableError,
    build_onboarding_requirements,
)
from backend.app.modules.profiles.schemas import OnboardingRequirementsResponse

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/onboarding-requirements", response_model=OnboardingRequirementsResponse)
def get_onboarding_requirements(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> OnboardingRequirementsResponse:
    """Tell the client which revision to submit and which consents to present.

    The client used to hold the terms revision in a build-time constant, so the
    stored agreement recorded whatever the oldest installed build believed. The
    deployment owns that value now.
    """

    del current_user
    settings = request.app.state.settings
    try:
        requirements = build_onboarding_requirements(
            terms_version=settings.terms_version,
            consent_policy_version=settings.consent_policy_version,
        )
    except TermsVersionUnavailableError:
        raise AppError(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code="LEGAL_POLICY_UNAVAILABLE",
            message="약관 정보를 일시적으로 사용할 수 없습니다.",
        ) from None
    return OnboardingRequirementsResponse(
        terms_version=requirements.terms_version,
        consent_policy_version=requirements.consent_policy_version,
        required_consent_type_codes=list(requirements.required_consent_type_codes),
        optional_consent_type_codes=list(requirements.optional_consent_type_codes),
    )


__all__ = ["router"]
