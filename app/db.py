"""MySQL adapter for the recipient store. One table, few queries --
kept intentionally thin. The interface it satisfies lives in
app/store.py; this module only knows how to talk to forward_recipients.
"""

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

    def _connection(self):
        return pymysql.connect(**self._connect_kwargs)

    def list_recipients(self, mailbox: str | None = None) -> list[dict]:
        conn = self._connection()
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

    def get_active_recipients(self, mailbox: str) -> list[str]:
        conn = self._connection()
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

    def add_recipient(self, mailbox: str, recipient: str, label: str | None) -> None:
        conn = self._connection()
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

    def set_enabled(self, row_id: int, enabled: bool) -> None:
        conn = self._connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE forward_recipients SET enabled = %s WHERE id = %s",
                    (1 if enabled else 0, row_id),
                )
        finally:
            conn.close()

    def delete_recipient(self, row_id: int) -> None:
        conn = self._connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM forward_recipients WHERE id = %s", (row_id,))
        finally:
            conn.close()
