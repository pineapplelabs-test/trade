"""Security utilities: Argon2 password hashing and session tokens."""

from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from fastapi import Cookie, Depends, HTTPException, status

from app.config import get_settings

settings = get_settings()
ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash plaintext password with Argon2."""
    return ph.hash(password)


def verify_password(hashed_password: str, plain_password: str) -> bool:
    """Verify password against Argon2 hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


def get_fernet() -> Fernet:
    """Return Fernet cipher instance from configured encryption key."""
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_token(token: str) -> str:
    """Encrypt a secret token string."""
    return get_fernet().encrypt(token.encode()).decode()


def decrypt_token(cipher_token: str) -> str:
    """Decrypt a secret token string."""
    return get_fernet().decrypt(cipher_token.encode()).decode()


def create_session_token(username: str, role: str = "operator") -> str:
    """Create a tamper-proof encrypted session cookie string with role and expiry."""
    expiry = datetime.now(UTC) + timedelta(days=7)
    payload = f"{username}|{role}|{expiry.isoformat()}"
    return encrypt_token(payload)


def verify_session_token(token: str) -> tuple[str, str]:
    """Verify session cookie and return (username, role) if valid and unexpired."""
    try:
        decrypted = decrypt_token(token)
        parts = decrypted.split("|")
        if len(parts) == 3:
            username, role, expiry_str = parts
        elif len(parts) == 2:
            # Backward-compatible 2-part token
            username, expiry_str = parts
            role = "operator"
        else:
            raise ValueError("Malformed token")

        expiry = datetime.fromisoformat(expiry_str)
        if datetime.now(UTC) > expiry:
            raise ValueError("Token expired")
        return username, role
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from e


async def get_current_user_and_role(session_token: str | None = Cookie(None, alias="paperdesk_session")) -> tuple[str, str]:
    """FastAPI dependency to extract (username, role) from session cookie."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return verify_session_token(session_token)


async def get_current_user(session_token: str | None = Cookie(None, alias="paperdesk_session")) -> str:
    """FastAPI dependency to protect endpoints with httpOnly cookie auth (returns username)."""
    user, _ = await get_current_user_and_role(session_token)
    return user


def require_role(allowed_roles: list[str]):
    """FastAPI dependency factory to enforce role-based access control (403 on role mismatch)."""
    async def role_checker(user_and_role: tuple[str, str] = Depends(get_current_user_and_role)) -> str:
        username, role = user_and_role
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: role '{role}' is not authorized. Required: {allowed_roles}",
            )
        return username
    return role_checker
