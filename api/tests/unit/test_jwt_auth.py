"""Tests for JWT auth dependency — verify_jwt (D-AUTH-01).

Verifies:
- Missing Authorization header → 401
- Non-Bearer prefix → 401
- Invalid/malformed token → 401
- Expired token → 401
- Wrong signature (bad key) → 401
- Missing 'sub' claim → 401
- Wrong audience → 401
- Valid token → correct UUID returned
"""

import time
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app.deps import verify_jwt

# Generate a test EC key pair for ES256
_TEST_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_TEST_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key()

# Second key pair for "wrong key" tests
_WRONG_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


def _make_token(
    user_id: str | None = None,
    private_key=_TEST_PRIVATE_KEY,
    audience: str = "authenticated",
    exp_offset: int = 3600,
) -> str:
    """Build a Supabase-style JWT signed with ES256 for testing."""
    now = int(time.time())
    payload: dict = {
        "aud": audience,
        "iat": now,
        "exp": now + exp_offset,
        "role": "authenticated",
    }
    if user_id is not None:
        payload["sub"] = user_id
    return jwt.encode(payload, private_key, algorithm="ES256")


# -- Fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_jwk_client():
    """Patch the JWKS client to return our test public key."""
    mock_signing_key = MagicMock()
    mock_signing_key.key = _TEST_PUBLIC_KEY

    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with patch("app.deps._jwk_client", mock_client):
        yield mock_client


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
async def test_wrong_key():
    """Token signed with different key → 401."""
    token = _make_token(user_id=str(uuid4()), private_key=_WRONG_PRIVATE_KEY)
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
