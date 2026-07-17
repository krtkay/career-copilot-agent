"""Unit tests for configuration and security primitives."""

from __future__ import annotations

import pytest

from app.core.config import Environment, Settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("s3cret-password")
    assert verify_password("s3cret-password", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    token = create_access_token("user-123")
    claims = decode_access_token(token)
    assert claims is not None
    assert claims["sub"] == "user-123"


def test_jwt_rejects_tampered_token():
    token = create_access_token("user-123") + "tamper"
    assert decode_access_token(token) is None


def test_cors_origins_split_from_string():
    s = Settings(cors_origins="http://a.com, http://b.com", app_env="development")
    assert s.cors_origins == ["http://a.com", "http://b.com"]


def test_production_rejects_default_secret():
    with pytest.raises(ValueError):
        Settings(
            app_env=Environment.PRODUCTION,
            jwt_secret_key="change-me-in-production-use-a-64-char-random-string",
        )


def test_llm_providers_filters_unconfigured():
    s = Settings(
        app_env="development",
        llm1_api_key="",
        llm2_api_key="",
        llm3_api_key="",
        llm4_api_key="",
    )
    assert s.llm_providers() == []
    s2 = Settings(
        app_env="development",
        llm1_api_key="key",
        llm2_api_key="",
        llm3_api_key="",
        llm4_api_key="",
    )
    providers = s2.llm_providers()
    assert len(providers) == 1
    assert providers[0].name == "openai"
