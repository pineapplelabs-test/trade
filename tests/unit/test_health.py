import pytest
from httpx import AsyncClient

from app.auth.security import create_session_token


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Verify health endpoint reports DB connectivity and paper safety."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"]["connected"] is True
    assert data["safety"]["real_orders_disabled"] is True
    assert data["safety"]["paper_trading_only"] is True


@pytest.mark.asyncio
async def test_accounts_endpoint(client: AsyncClient):
    """Verify all 3 configured paper accounts (real5k, tiny, shadow) are loaded."""
    response = await client.get("/api/accounts")
    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) >= 3

    account_ids = {a["id"]: a for a in accounts}
    assert "real5k" in account_ids
    assert "tiny" in account_ids
    assert "shadow" in account_ids

    # Check real5k values
    real5k = account_ids["real5k"]
    assert real5k["starting_capital"] == 5000.0
    assert real5k["equity"] == 5000.0
    assert real5k["max_positions"] == 2


@pytest.mark.asyncio
async def test_kill_and_resume_switch(client: AsyncClient):
    """Verify emergency kill switch enforces authentication, halts system, and resume restores it."""
    # 1. Unauthenticated request must be rejected with 401
    unauth_res = await client.post("/api/kill")
    assert unauth_res.status_code == 401

    # 2. Authenticated request succeeds
    auth_cookie = create_session_token("trader")
    client.cookies.set("paperdesk_session", auth_cookie)

    kill_res = await client.post("/api/kill")
    assert kill_res.status_code == 200
    assert kill_res.json()["status"] == "halted"

    status_res = await client.get("/api/system-status")
    assert status_res.status_code == 200
    assert status_res.json()["system_halted"] is True

    resume_res = await client.post("/api/resume")
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "active"
