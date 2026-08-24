"""MySQL access layer for Relayer. One table, few queries -- kept intentionally thin."""

import os

import pymysql
import pymysql.cursors


def get_connection():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "mariadb"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_DATABASE", "mail"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=5,
    )


def list_recipients(mailbox: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if mailbox:
                cur.execute(
                    "SELECT * FROM forward_recipients WHERE mailbox = %s "
                    "ORDER BY recipient",
                    (mailbox,),
                )
            else:
                cur.execute(
                    "SELECT * FROM forward_recipients "
                    "ORDER BY mailbox, recipient"
                )
            return list(cur.fetchall())
    finally:
        conn.close()


def get_active_recipients(mailbox: str) -> list[str]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT recipient FROM forward_recipients "
                "WHERE mailbox = %s AND enabled = 1",
                (mailbox,),
            )
            return [row["recipient"] for row in cur.fetchall()]
    finally:
        conn.close()


def add_recipient(mailbox: str, recipient: str, label: str | None) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO forward_recipients (mailbox, recipient, label, enabled) "
                "VALUES (%s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE label = VALUES(label), enabled = 1",
                (mailbox.strip().lower(), recipient.strip().lower(), (label or "").strip() or None),
            )
    finally:
        conn.close()


def set_enabled(row_id: int, enabled: bool) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE forward_recipients SET enabled = %s WHERE id = %s",
                (1 if enabled else 0, row_id),
            )
    finally:
        conn.close()


def delete_recipient(row_id: int) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM forward_recipients WHERE id = %s", (row_id,))
    finally:
        conn.close()
