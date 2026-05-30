"""Tests for JWT auth dependency — verify_jwt (D-AUTH-01).

Verifies:
- Missing Authorization header → 401
- Non-Bearer prefix → 401
- Invalid/malformed token → 401
- Expired token → 401
- Wrong signature (bad secret) → 401
- Missing 'sub' claim → 401
- Wrong audience → 401
- Valid token → correct UUID returned
"""

import time
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.deps import verify_jwt

# Test secret — not the real one
TEST_SECRET = "test-jwt-secret-with-at-least-32-characters-long"


def _make_token(
    user_id: str | None = None,
    secret: str = TEST_SECRET,
    algorithm: str = "HS256",
    audience: str = "authenticated",
    exp_offset: int = 3600,
    extra_claims: dict | None = None,
) -> str:
    """Build a Supabase-style JWT for testing."""
    now = int(time.time())
    payload: dict = {
        "aud": audience,
        "iat": now,
        "exp": now + exp_offset,
        "role": "authenticated",
    }
    if user_id is not None:
        payload["sub"] = user_id
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm=algorithm)


# -- Fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """Patch the supabase_jwt_secret setting for all tests."""
    from unittest.mock import MagicMock

    mock_secret = MagicMock()
    mock_secret.get_secret_value.return_value = TEST_SECRET
    monkeypatch.setattr("app.deps.settings.supabase_jwt_secret", mock_secret)


# -- Tests -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_authorization_header():
    """No Authorization header → 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization=None)
    assert exc_info.value.status_code == 401
    assert "Missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_empty_authorization_header():
    """Empty Authorization header → 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization="")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_non_bearer_prefix():
    """Authorization: Basic ... → 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization="Basic abc123")
    assert exc_info.value.status_code == 401
    assert "Missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_malformed_token():
    """Bearer <garbage> → 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization="Bearer not.a.real.jwt")
    assert exc_info.value.status_code == 401
    assert "Invalid" in exc_info.value.detail


@pytest.mark.asyncio
async def test_expired_token():
    """Token with exp in the past → 401 'Token expired'."""
    token = _make_token(user_id=str(uuid4()), exp_offset=-3600)
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_wrong_secret():
    """Token signed with wrong secret → 401."""
    token = _make_token(user_id=str(uuid4()), secret="wrong-secret-that-is-long-enough")
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401
    assert "Invalid" in exc_info.value.detail


@pytest.mark.asyncio
async def test_wrong_audience():
    """Token with wrong audience → 401."""
    token = _make_token(user_id=str(uuid4()), audience="anon")
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_sub_claim():
    """Token without 'sub' claim → 401."""
    token = _make_token(user_id=None)
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_sub_not_uuid():
    """Token with non-UUID sub → 401."""
    token = _make_token(user_id="not-a-uuid")
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_returns_uuid():
    """Valid token → returns correct UUID from sub claim."""
    uid = uuid4()
    token = _make_token(user_id=str(uid))
    result = await verify_jwt(authorization=f"Bearer {token}")
    assert isinstance(result, UUID)
    assert result == uid


@pytest.mark.asyncio
async def test_valid_token_with_extra_whitespace():
    """Bearer  <token> (extra space) still works."""
    uid = uuid4()
    token = _make_token(user_id=str(uid))
    result = await verify_jwt(authorization=f"Bearer  {token}")
    assert result == uid
