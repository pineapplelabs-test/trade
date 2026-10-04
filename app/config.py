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


def get_charges_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "charges.yaml")


def get_risk_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "risk.yaml")


def get_strategy_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "strategy.yaml")
