"""Application configuration and YAML specification loader."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    ENVIRONMENT: str = "development"  # development | staging | production
    SECRET_KEY: str = "change-this-in-production-to-a-random-secret"
    ENCRYPTION_KEY: str = "W3uG_1H9m3n8xK9Z8gV2eY7wQ6sL5pM4rT2bN1vC0xA="
    ADMIN_USERNAME: str = "trader"
    ADMIN_PASSWORD: str = "ChangeMeNow123!"

    # Database
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATA_DIR}/paperdesk.db"

    # Groww Market Data API (Read-Only)
    GROWW_API_KEY: str = ""
    GROWW_TOTP_TOKEN: str = ""

    # Operational
    FEED_MODE: str = "sim"  # sim | replay | groww
    PESSIMISTIC_FILLS: bool = True
    LOG_LEVEL: str = "INFO"

    # Optional alerts
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Security & CORS
    CORS_ALLOWED_ORIGINS: list[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
    ]
    COOKIE_SECURE: bool = False

    def model_post_init(self, __context: Any) -> None:
        if self.ENVIRONMENT.lower() in {"production", "prod"}:
            if self.ADMIN_PASSWORD in {"ChangeMeNow123!", "", "admin", "adminpassword"} or len(self.ADMIN_PASSWORD) < 8:
                raise ValueError("SECURITY VIOLATION: Default or empty ADMIN_PASSWORD cannot be used in production environment.")
            if "change-this" in self.SECRET_KEY or self.SECRET_KEY == "" or len(self.SECRET_KEY) < 16:
                raise ValueError("SECURITY VIOLATION: Default or empty SECRET_KEY cannot be used in production environment.")
            if self.ENCRYPTION_KEY in {"W3uG_1H9m3n8xK9Z8gV2eY7wQ6sL5pM4rT2bN1vC0xA=", ""} or len(self.ENCRYPTION_KEY) < 16:
                raise ValueError("SECURITY VIOLATION: Default or empty ENCRYPTION_KEY cannot be used in production environment.")
            if "*" in self.CORS_ALLOWED_ORIGINS:
                raise ValueError("SECURITY VIOLATION: Wildcard CORS origins are forbidden in production environment.")


def load_yaml(file_path: Path) -> dict[str, Any]:
    """Safely load YAML configuration file."""
    if not file_path.exists():
        return {}
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()


def get_accounts_config() -> dict[str, Any]:
    res = load_yaml(CONFIG_DIR / "accounts.yaml").get("accounts", {})
    return res if isinstance(res, dict) else {}


def get_account_spec(account_id: str) -> dict[str, Any]:
    """Retrieve validated configuration for a specific account with fallback defaults."""
    accts = get_accounts_config()
    if account_id in accts and isinstance(accts[account_id], dict):
        return dict(accts[account_id])
    # Default fallback spec if not in yaml
    defaults = {
        "tiny": {"starting_capital": 1000.0, "max_position_pct": 50.0, "max_open_positions": 2, "ev_min_pct": 0.15, "risk_per_trade_pct": 1.0},
        "real5k": {"starting_capital": 5000.0, "max_position_pct": 50.0, "max_open_positions": 2, "ev_min_pct": 0.12, "risk_per_trade_pct": 1.0},
        "shadow": {"starting_capital": 100000.0, "max_position_pct": 20.0, "max_open_positions": 5, "ev_min_pct": 0.10, "risk_per_trade_pct": 0.5},
    }
    return defaults.get(account_id, {"starting_capital": 1000.0, "max_position_pct": 50.0, "max_open_positions": 2, "ev_min_pct": 0.15, "risk_per_trade_pct": 1.0})


def get_charges_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "charges.yaml")


def get_risk_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "risk.yaml")


def get_strategy_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "strategy.yaml")
