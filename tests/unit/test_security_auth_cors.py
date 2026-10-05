from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.security import create_session_token, verify_session_token
from app.config import Settings
from app.main import app


def test_production_settings_validation() -> None:
    """Production mode must forbid default credentials, empty secrets, and wildcard CORS."""
    # 1. Default admin password in production fails
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        Settings(
            ENVIRONMENT="production",
            ADMIN_PASSWORD="admin",
            SECRET_KEY="supersecretkey123456789012345678901234",
            ENCRYPTION_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            CORS_ALLOWED_ORIGINS=["https://paperdesk.internal"],
        )

    # 2. Wildcard CORS in production fails
    with pytest.raises(ValueError, match="Wildcard CORS"):
        Settings(
            ENVIRONMENT="production",
            ADMIN_PASSWORD="StrongProductionPassword987!#",
            SECRET_KEY="supersecretkey123456789012345678901234",
            ENCRYPTION_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            CORS_ALLOWED_ORIGINS=["*"],
        )


def test_role_based_session_tokens() -> None:
    """Session token carries role and can be verified."""
    token = create_session_token(username="admin", role="operator")
    username, role = verify_session_token(token)
    assert username == "admin"
    assert role == "operator"

    token_viewer = create_session_token(username="viewer", role="viewer")
    user_v, role_v = verify_session_token(token_viewer)
    assert user_v == "viewer"
    assert role_v == "viewer"


@pytest.mark.asyncio
async def test_auth_login_and_cookie() -> None:
    """Login issues session cookie with role metadata."""
    from app.config import get_settings
    settings = get_settings()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Invalid credentials
        res_bad = await client.post("/auth/login", json={"username": "admin", "password": "wrongpassword"})
        assert res_bad.status_code == 401

        # Valid credentials
        res_good = await client.post("/auth/login", json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
        assert res_good.status_code == 200
        assert res_good.json()["status"] == "ok"
        assert "paperdesk_session" in res_good.cookies

        # Status check using cookie
        res_status = await client.get("/auth/status")
        assert res_status.status_code == 200
        status_data = res_status.json()
        assert status_data["authenticated"] is True
        assert status_data["role"] == "operator"
