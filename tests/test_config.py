"""Tests for app/config.py: env is read and validated once, at startup."""

import unittest
from unittest import mock

from app import config


class ConfigTests(unittest.TestCase):
    def test_missing_required_db_user_raises_at_startup(self):
        env = {"DB_HOST": "mariadb", "DB_PASSWORD": "pw"}
        with mock.patch.dict(config.os.environ, env, clear=True):
            with self.assertRaises(config.ConfigError) as ctx:
                config.load()

        self.assertIn("DB_USER", str(ctx.exception))

    def test_missing_required_ingest_token_raises_at_startup(self):
        env = {"DB_USER": "relayer"}
        with mock.patch.dict(config.os.environ, env, clear=True):
            with self.assertRaises(config.ConfigError) as ctx:
                config.load()

        self.assertIn("INGEST_TOKEN", str(ctx.exception))

    def test_defaults_applied_for_optional_values(self):
        env = {"DB_USER": "relayer", "INGEST_TOKEN": "tok"}
        with mock.patch.dict(config.os.environ, env, clear=True):
            settings = config.load()

        self.assertEqual(settings.db_host, "mariadb")
        self.assertEqual(settings.db_port, 3306)
        self.assertEqual(settings.db_database, "mail")
        self.assertEqual(settings.postfix_host, "postfix")
        self.assertEqual(settings.postfix_port, 25)
        self.assertEqual(settings.admin_user, "admin")
        self.assertIsNone(settings.admin_pass)
        self.assertEqual(settings.secret_key, "change-me-in-production")
        self.assertFalse(settings.ui_prototype)
        self.assertFalse(settings.debug_smtp)

    def test_values_read_from_env(self):
        env = {
            "DB_USER": "relayer",
            "DB_PASSWORD": "pw",
            "DB_HOST": "db.internal",
            "DB_PORT": "3307",
            "DB_DATABASE": "maildb",
            "INGEST_TOKEN": "tok",
            "ADMIN_USER": "boss",
            "ADMIN_PASS": "secret",
            "SECRET_KEY": "real-secret",
            "POSTFIX_HOST": "relay.internal",
            "POSTFIX_PORT": "587",
            "LOG_LEVEL": "DEBUG",
            "UI_PROTOTYPE": "1",
        }
        with mock.patch.dict(config.os.environ, env, clear=True):
            settings = config.load()

        self.assertEqual(settings.db_host, "db.internal")
        self.assertEqual(settings.db_port, 3307)
        self.assertEqual(settings.db_database, "maildb")
        self.assertEqual(settings.postfix_host, "relay.internal")
        self.assertEqual(settings.postfix_port, 587)
        self.assertEqual(settings.admin_user, "boss")
        self.assertEqual(settings.admin_pass, "secret")
        self.assertEqual(settings.secret_key, "real-secret")
        self.assertTrue(settings.ui_prototype)
        self.assertTrue(settings.debug_smtp)

    def test_invalid_db_port_raises_at_startup(self):
        env = {"DB_USER": "relayer", "INGEST_TOKEN": "tok", "DB_PORT": "not-a-number"}
        with mock.patch.dict(config.os.environ, env, clear=True):
            with self.assertRaises(config.ConfigError):
                config.load()


if __name__ == "__main__":
    unittest.main()


class FactoryWiringTests(unittest.TestCase):
    def test_store_factory_builds_mysql_adapter_from_settings(self):
        from app.db import MySQLRecipientStore
        from app.store import store_from_env

        settings = config.Settings(
            db_host="db.internal", db_port=3307, db_user="relayer", db_password="pw",
            db_database="maildb", ingest_token="tok", admin_user="admin",
            admin_pass=None, secret_key="s", ui_prototype=False,
            postfix_host="postfix", postfix_port=25, debug_smtp=False)
        store = store_from_env(settings)
        self.assertIsInstance(store, MySQLRecipientStore)

    def test_mailer_transport_builds_callable_from_settings(self):
        from app import mailer

        settings = config.Settings(
            db_host="mariadb", db_port=3306, db_user="relayer", db_password="pw",
            db_database="mail", ingest_token="tok", admin_user="admin",
            admin_pass=None, secret_key="s", ui_prototype=False,
            postfix_host="relay.internal", postfix_port=587, debug_smtp=False)
        transport = mailer.smtp_transport(settings)
        self.assertTrue(callable(transport))
