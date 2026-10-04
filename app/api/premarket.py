"""Pre-market intelligence API endpoint.

The endpoint must never expose fixture prices as if they were genuine NSE
pre-open auction data. Until a real pre-open data source is wired in, the
production endpoint fails closed.
"""
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/premarket", tags=["premarket"])
VALID_ACCOUNTS = {"tiny", "real5k", "shadow"}


@router.get("/report")
async def get_premarket_report(account: str = Query("real5k")) -> dict[str, Any]:
    """Return only genuine pre-market intelligence; fail closed otherwise."""
    if account not in VALID_ACCOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid account '{account}'. Must be one of: {sorted(VALID_ACCOUNTS)}",
        )

    raise HTTPException(
        status_code=503,
        detail=(
            "PREMARKET_UNAVAILABLE: genuine NSE pre-open auction data is not "
            "connected. Synthetic fixture data is intentionally blocked from "
            "the production endpoint."
        ),
    )
