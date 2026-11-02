"""The recipient store contract, run against the MySQL adapter.

Opt-in: these tests need a live database, so they skip unless all the
TEST_DB_* variables are set. Point them at the local Compose stack to
check the adapter has not drifted from the in-memory fake:

    TEST_DB_HOST=127.0.0.1 TEST_DB_PORT=3306 TEST_DB_USER=relayer \
    TEST_DB_PASSWORD=relayerpass TEST_DB_DATABASE=mail \
    python -m unittest tests.test_store_mysql -v

The schema comes from the canonical schema.sql, so this also proves the
shipped DDL is what the adapter works against. These tests delete every
row in forward_recipients between tests: only run them against a
database you are willing to lose data from.
"""

import os
import re
import unittest

import pymysql

from app.db import MySQLRecipientStore
from tests.store_contract import StoreContractTests

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "schema.sql")

REQUIRED_DB_VARS = (
    "TEST_DB_HOST",
    "TEST_DB_USER",
    "TEST_DB_PASSWORD",
    "TEST_DB_DATABASE",
)


def missing_db_vars():
    return [name for name in REQUIRED_DB_VARS if not os.environ.get(name)]


def skip_reason():
    missing = missing_db_vars()
    return (
        "MySQL store contract tests need a database (missing: "
        + ", ".join(missing)
        + "); the local Compose stack is a valid target"
    )


def canonical_schema() -> str:
    """The forward_recipients DDL, read from schema.sql so the contract
    runs against the table this repo actually ships."""
    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        ddl = handle.read()
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS forward_recipients\s*\(.*?\)\s*ENGINE=[^;]+;",
        ddl,
        re.S,
    )
    if not match:
        raise AssertionError(f"no forward_recipients DDL found in {SCHEMA_PATH}")
    return match.group(0)


def connection_params() -> dict:
    return dict(
        host=os.environ["TEST_DB_HOST"],
        port=int(os.environ.get("TEST_DB_PORT", "3306")),
        user=os.environ["TEST_DB_USER"],
        password=os.environ["TEST_DB_PASSWORD"],
        database=os.environ["TEST_DB_DATABASE"],
    )


def execute(statement: str) -> None:
    with pymysql.connect(**connection_params(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(statement)


@unittest.skipIf(missing_db_vars(), skip_reason())
class MySQLStoreTests(StoreContractTests, unittest.TestCase):
    def setUp(self):
        execute(canonical_schema())
        self._truncate()
        super().setUp()

    def tearDown(self):
        self._truncate()

    def make_store(self):
        return MySQLRecipientStore(**connection_params())

    def _truncate(self):
        execute("DELETE FROM forward_recipients")


if __name__ == "__main__":
    unittest.main()
