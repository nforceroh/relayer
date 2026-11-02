"""MySQL adapter for the recipient store. One table, few queries --
kept intentionally thin. The interface it satisfies lives in
app/store.py; this module only knows how to talk to forward_recipients.
"""

from contextlib import contextmanager

import pymysql
import pymysql.cursors


class MySQLRecipientStore:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self._connect_kwargs = dict(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=5,
        )

    @contextmanager
    def _cursor(self):
        conn = pymysql.connect(**self._connect_kwargs)
        try:
            with conn.cursor() as cur:
                yield cur
        finally:
            conn.close()

    def list_recipients(self, mailbox: str | None = None) -> list[dict]:
        with self._cursor() as cur:
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

    def get_active_recipients(self, mailbox: str) -> list[str]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT recipient FROM forward_recipients "
                "WHERE mailbox = %s AND enabled = 1",
                (mailbox,),
            )
            return [row["recipient"] for row in cur.fetchall()]

    def add_recipient(self, mailbox: str, recipient: str, label: str | None) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO forward_recipients (mailbox, recipient, label, enabled) "
                "VALUES (%s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE label = VALUES(label), enabled = 1",
                (mailbox.strip().lower(), recipient.strip().lower(), (label or "").strip() or None),
            )

    def set_enabled(self, row_id: int, enabled: bool) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE forward_recipients SET enabled = %s WHERE id = %s",
                (1 if enabled else 0, row_id),
            )

    def delete_recipient(self, row_id: int) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM forward_recipients WHERE id = %s", (row_id,))
