"""Authentication API routes."""

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pydantic import BaseModel

from app.auth.security import create_session_token, verify_session_token
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    username: str | None = None
    role: str | None = None


@router.post("/login")
async def login(req: LoginRequest, response: Response) -> dict[str, str]:
    """Validate credentials and set secure httpOnly session cookie."""
    if req.username != settings.ADMIN_USERNAME or req.password != settings.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    cookie_val = create_session_token(req.username, role="operator")
    is_secure = settings.ENVIRONMENT.lower() in {"production", "prod"} or settings.COOKIE_SECURE
    response.set_cookie(
        key="paperdesk_session",
        value=cookie_val,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return {"status": "ok", "message": "Logged in successfully"}


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """Clear session cookie."""
    response.delete_cookie("paperdesk_session")
    return {"status": "ok", "message": "Logged out"}


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    session_token: str | None = Cookie(None, alias="paperdesk_session"),
) -> AuthStatusResponse:
    """Check current authentication status by verifying session cookie."""
    if not session_token:
        return AuthStatusResponse(authenticated=False, username=None, role=None)
    try:
        username, role = verify_session_token(session_token)
        return AuthStatusResponse(authenticated=True, username=username, role=role)
    except Exception:
        return AuthStatusResponse(authenticated=False, username=None, role=None)
