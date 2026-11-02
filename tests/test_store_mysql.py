"""The recipient store contract, run against the MySQL adapter.

Opt-in: these tests need a live database, so they skip unless the
TEST_DB_* variables are set. Point them at the local Compose stack to
check the adapter has not drifted from the in-memory fake:

    TEST_DB_HOST=127.0.0.1 TEST_DB_USER=relayer \\
    TEST_DB_PASSWORD=relayerpass TEST_DB_DATABASE=mail \\
    python -m unittest tests.test_store_mysql -v

The tests create the forward_recipients table if it is missing and
delete its rows between tests, so only ever point them at a database
you are willing to lose data from.
"""

import os
import unittest

from tests.store_contract import StoreContractTests

SKIP_REASON = (
    "MySQL store contract tests need a database: set TEST_DB_HOST, "
    "TEST_DB_USER, TEST_DB_PASSWORD and TEST_DB_DATABASE (the local "
    "Compose stack is a valid target)"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS forward_recipients (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    mailbox     VARCHAR(255) NOT NULL,
    recipient   VARCHAR(255) NOT NULL,
    label       VARCHAR(255) NULL,
    enabled     TINYINT(1) NOT NULL DEFAULT 1,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_mailbox_recipient (mailbox, recipient),
    KEY idx_mailbox_enabled (mailbox, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


@unittest.skipUnless(os.environ.get("TEST_DB_HOST"), SKIP_REASON)
class MySQLStoreTests(StoreContractTests, unittest.TestCase):
    def make_store(self):
        import pymysql

        from app.db import MySQLRecipientStore

        self.connection_params = dict(
            host=os.environ["TEST_DB_HOST"],
            port=int(os.environ.get("TEST_DB_PORT", "3306")),
            user=os.environ["TEST_DB_USER"],
            password=os.environ.get("TEST_DB_PASSWORD", ""),
            database=os.environ.get("TEST_DB_DATABASE", "mail"),
        )
        with pymysql.connect(**self.connection_params, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
        return MySQLRecipientStore(**self.connection_params)

    def setUp(self):
        super().setUp()
        self._truncate()

    def tearDown(self):
        self._truncate()

    def _truncate(self):
        import pymysql

        with pymysql.connect(**self.connection_params, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM forward_recipients")


if __name__ == "__main__":
    unittest.main()