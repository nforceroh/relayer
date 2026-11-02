"""Recipient store: the seam between Relayer and wherever recipient rows
live.

The interface is four operations over recipient rows:

    list_recipients(mailbox=None) -> list[dict]
    get_active_recipients(mailbox) -> list[str]
    add_recipient(mailbox, recipient, label) -> None
    set_enabled(row_id, enabled) -> None
    delete_recipient(row_id) -> None

Rows are dicts with at least: id, mailbox, recipient, label, enabled,
created_at. Addresses are normalized (stripped, lowercased) by the
adapter that writes; readers get back what was stored.

Two adapters satisfy this interface:
- MySQLRecipientStore -- production, backed by the forward_recipients table.
- InMemoryRecipientStore -- tests and local experiments; starts empty.

Pick one with store_from_env(), which reads the DB_* environment
variables once at startup.
"""

import os

from .config import Settings
from .db import MySQLRecipientStore


class InMemoryRecipientStore:
    """Dict-backed recipient store for tests. Rows get sequential ids."""

    def __init__(self, rows: list[dict] | None = None):
        self._rows = [dict(row) for row in (rows or [])]
        self._next_id = max((row["id"] for row in self._rows), default=0) + 1

    def list_recipients(self, mailbox: str | None = None) -> list[dict]:
        rows = self._rows
        if mailbox is not None:
            rows = [row for row in rows if row["mailbox"] == mailbox]
        return sorted(rows, key=lambda row: (row["mailbox"], row["recipient"]))

    def get_active_recipients(self, mailbox: str) -> list[str]:
        return [
            row["recipient"]
            for row in self._rows
            if row["mailbox"] == mailbox and row["enabled"]
        ]

    def add_recipient(self, mailbox: str, recipient: str, label: str | None) -> None:
        mailbox = mailbox.strip().lower()
        recipient = recipient.strip().lower()
        label = (label or "").strip() or None
        for row in self._rows:
            if row["mailbox"] == mailbox and row["recipient"] == recipient:
                row["label"] = label
                row["enabled"] = 1
                return
        self._rows.append({
            "id": self._next_id,
            "mailbox": mailbox,
            "recipient": recipient,
            "label": label,
            "enabled": 1,
            "created_at": "1970-01-01 00:00:00",
        })
        self._next_id += 1

    def set_enabled(self, row_id: int, enabled: bool) -> None:
        for row in self._rows:
            if row["id"] == row_id:
                row["enabled"] = 1 if enabled else 0
                return

    def delete_recipient(self, row_id: int) -> None:
        self._rows = [row for row in self._rows if row["id"] != row_id]


def store_from_env(settings: Settings | None = None) -> MySQLRecipientStore:
    """Returns the production store built from loaded settings (or from
    the environment directly when settings are not supplied)."""
    if settings is None:
        return MySQLRecipientStore(
            host=os.environ.get("DB_HOST", "mariadb"),
            port=int(os.environ.get("DB_PORT", "3306")),
            user=os.environ["DB_USER"],
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_DATABASE", "mail"),
        )
    return MySQLRecipientStore(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_database,
    )
