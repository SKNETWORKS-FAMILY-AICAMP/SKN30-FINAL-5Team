from enum import StrEnum

IDENTITY_CODE_SET_VERSION = "identity-mvp-v1"


class UserStatusCode(StrEnum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    DELETION_PENDING = "DELETION_PENDING"
    DISABLED = "DISABLED"


class IdentityProviderCode(StrEnum):
    """Provider codes implemented by the first identity vertical slice."""

    FIREBASE = "FIREBASE"


class PremiumStatusCode(StrEnum):
    NOT_AVAILABLE = "NOT_AVAILABLE"


__all__ = [
    "IDENTITY_CODE_SET_VERSION",
    "IdentityProviderCode",
    "PremiumStatusCode",
    "UserStatusCode",
]
