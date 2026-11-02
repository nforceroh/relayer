"""Configuration: environment is read and validated once, at startup.

The interface is one function:

    load() -> Settings

It raises ConfigError naming the missing or invalid variable, so a
misconfigured deployment fails loudly at boot instead of mid-request.
Modules receive typed settings; none of them read os.environ directly.
"""

import os
from dataclasses import dataclass


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    # Recipient store
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_database: str
    # Ingest auth
    ingest_token: str
    # Web UI
    admin_user: str
    admin_pass: str | None
    secret_key: str
    ui_prototype: bool
    # Outbound mail
    postfix_host: str
    postfix_port: int
    debug_smtp: bool
    @classmethod
    def for_tests(cls, **overrides) -> "Settings":
        """A valid Settings instance for tests, with every field given a
        benign value. Overrides replace individual fields."""
        defaults = dict(
            db_host="mariadb",
            db_port=3306,
            db_user="test-relayer",
            db_password="test-password",
            db_database="mail",
            ingest_token="test-ingest-token",
            admin_user="admin",
            admin_pass="test-password",
            secret_key="test-secret",
            ui_prototype=False,
            postfix_host="postfix",
            postfix_port=25,
            debug_smtp=False,
        )
        defaults.update(overrides)
        return cls(**defaults)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"required environment variable {name} is not set")
    return value


def _int(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"environment variable {name} must be an integer, got {raw!r}")


def load() -> Settings:
    return Settings(
        db_host=os.environ.get("DB_HOST", "mariadb"),
        db_port=_int("DB_PORT", "3306"),
        db_user=_require("DB_USER"),
        db_password=os.environ.get("DB_PASSWORD", ""),
        db_database=os.environ.get("DB_DATABASE", "mail"),
        ingest_token=_require("INGEST_TOKEN"),
        admin_user=os.environ.get("ADMIN_USER", "admin"),
        admin_pass=os.environ.get("ADMIN_PASS") or None,
        secret_key=os.environ.get("SECRET_KEY", "change-me-in-production"),
        ui_prototype=os.environ.get("UI_PROTOTYPE") == "1",
        postfix_host=os.environ.get("POSTFIX_HOST", "postfix"),
        postfix_port=_int("POSTFIX_PORT", "25"),
        debug_smtp=os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG",
    )
