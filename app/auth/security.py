"""Security utilities: Argon2 password hashing and session tokens."""

from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from fastapi import Cookie, HTTPException, status

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


def create_session_token(username: str) -> str:
    """Create a tamper-proof encrypted session cookie string with expiry."""
    expiry = datetime.now(UTC) + timedelta(days=7)
    payload = f"{username}|{expiry.isoformat()}"
    return encrypt_token(payload)


def verify_session_token(token: str) -> str:
    """Verify session cookie and return username if valid and unexpired."""
    try:
        decrypted = decrypt_token(token)
        parts = decrypted.split("|", 1)
        if len(parts) != 2:
            raise ValueError("Malformed token")
        username, expiry_str = parts
        expiry = datetime.fromisoformat(expiry_str)
        if datetime.now(UTC) > expiry:
            raise ValueError("Token expired")
        return username
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from e


async def get_current_user(session_token: str | None = Cookie(None, alias="paperdesk_session")) -> str:
    """FastAPI dependency to protect endpoints with httpOnly cookie auth."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return verify_session_token(session_token)
