from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SocialAuthorizationInitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    redirect_uri: str = Field(min_length=1, max_length=2048)
    code_challenge: str = Field(min_length=43, max_length=43)
    code_challenge_method: Literal["S256"]


class SocialAuthorizationInitResponse(BaseModel):
    provider_code: Literal["GOOGLE", "KAKAO"]
    authorization_url: str
    state: str
    nonce: str
    expires_at: datetime


class SocialTokenExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_code: str = Field(min_length=1, max_length=4096)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=1024)
    nonce: str = Field(min_length=1, max_length=1024)
    code_verifier: str = Field(min_length=43, max_length=128)

    @field_validator("code_verifier")
    @classmethod
    def validate_pkce_charset(cls, value: str) -> str:
        allowed = all(
            character.isascii() and (character.isalnum() or character in "-._~")
            for character in value
        )
        if not allowed:
            raise ValueError("code_verifier must use RFC 7636 characters")
        return value


class SocialTokenExchangeResponse(BaseModel):
    token_type: Literal["FIREBASE_CUSTOM_TOKEN"]
    firebase_custom_token: str


__all__ = [
    "SocialAuthorizationInitRequest",
    "SocialAuthorizationInitResponse",
    "SocialTokenExchangeRequest",
    "SocialTokenExchangeResponse",
]
