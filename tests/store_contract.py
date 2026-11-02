"""The recipient store's behavioural contract, written once and run
against every adapter.

The interface is the test surface: these assertions describe what a
caller may rely on, independent of whether rows live in memory or in
MySQL. Subclasses supply make_store() and, if the adapter persists
state, reset() between tests.

What the contract pins: required keys, address normalization on write,
upsert-on-duplicate, ordering, the active-recipient lookup, toggling,
deletion, and no-ops for unknown ids. It deliberately does not pin
Python types for driver-shaped values (e.g. created_at), since those
differ legitimately between a database driver and an in-memory fake.
"""

import datetime
import unittest

REQUIRED_KEYS = {"id", "mailbox", "recipient", "label", "enabled", "created_at"}


class StoreContractTests:
    """Mixin: subclass with unittest.TestCase and implement make_store()."""

    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.store = self.make_store()

    # ---- shape ---------------------------------------------------------

    def test_new_store_is_empty(self):
        self.assertEqual(self.store.list_recipients(), [])

    def test_rows_carry_the_required_keys(self):
        self.store.add_recipient("toyota@example.com", "a@example.net", "Personal")

        rows = self.store.list_recipients()

        self.assertEqual(len(rows), 1)
        self.assertTrue(REQUIRED_KEYS.issubset(rows[0].keys()))
        self.assertEqual(rows[0]["mailbox"], "toyota@example.com")
        self.assertEqual(rows[0]["recipient"], "a@example.net")
        self.assertEqual(rows[0]["label"], "Personal")
        self.assertTrue(rows[0]["enabled"])

    def test_created_at_is_a_temporal_value(self):
        self.store.add_recipient("toyota@example.com", "a@example.net", None)

        created_at = self.store.list_recipients()[0]["created_at"]

        self.assertIsInstance(created_at, (str, datetime.datetime))

    # ---- writing -------------------------------------------------------

    def test_addresses_are_normalized_on_write(self):
        self.store.add_recipient("  Toyota@Example.COM ", " A@Example.NET ", "  Personal  ")

        row = self.store.list_recipients()[0]

        self.assertEqual(row["mailbox"], "toyota@example.com")
        self.assertEqual(row["recipient"], "a@example.net")
        self.assertEqual(row["label"], "Personal")

    def test_blank_label_is_stored_as_none(self):
        self.store.add_recipient("toyota@example.com", "a@example.net", "   ")

        self.assertIsNone(self.store.list_recipients()[0]["label"])

    def test_duplicate_add_updates_label_and_reenables(self):
        self.store.add_recipient("toyota@example.com", "a@example.net", "Old")
        row_id = self.store.list_recipients()[0]["id"]
        self.store.set_enabled(row_id, False)

        self.store.add_recipient("toyota@example.com", "a@example.net", "New")

        rows = self.store.list_recipients()
        self.assertEqual(len(rows), 1, "duplicate add must not create a second row")
        self.assertEqual(rows[0]["id"], row_id)
        self.assertEqual(rows[0]["label"], "New")
        self.assertTrue(rows[0]["enabled"])

    # ---- reading -------------------------------------------------------

    def test_list_recipients_orders_by_mailbox_then_recipient(self):
        self.store.add_recipient("b@example.com", "z@example.net", None)
        self.store.add_recipient("a@example.com", "m@example.net", None)
        self.store.add_recipient("a@example.com", "a@example.net", None)

        rows = self.store.list_recipients()

        self.assertEqual(
            [(row["mailbox"], row["recipient"]) for row in rows],
            [
                ("a@example.com", "a@example.net"),
                ("a@example.com", "m@example.net"),
                ("b@example.com", "z@example.net"),
            ],
        )

    def test_list_recipients_for_one_mailbox_orders_by_recipient(self):
        self.store.add_recipient("a@example.com", "z@example.net", None)
        self.store.add_recipient("a@example.com", "a@example.net", None)
        self.store.add_recipient("b@example.com", "m@example.net", None)

        rows = self.store.list_recipients("a@example.com")

        self.assertEqual(
            [row["recipient"] for row in rows],
            ["a@example.net", "z@example.net"],
        )

    def test_active_recipients_excludes_disabled_ones(self):
        self.store.add_recipient("a@example.com", "on@example.net", None)
        self.store.add_recipient("a@example.com", "off@example.net", None)
        self.store.add_recipient("b@example.com", "other@example.net", None)
        off_id = next(
            row["id"] for row in self.store.list_recipients()
            if row["recipient"] == "off@example.net"
        )
        self.store.set_enabled(off_id, False)

        self.assertEqual(
            sorted(self.store.get_active_recipients("a@example.com")),
            ["on@example.net"],
        )
        self.assertEqual(self.store.get_active_recipients("missing@example.com"), [])

    # ---- updating and deleting -----------------------------------------

    def test_toggle_changes_enabled_flag(self):
        self.store.add_recipient("a@example.com", "a@example.net", None)
        row_id = self.store.list_recipients()[0]["id"]

        self.store.set_enabled(row_id, False)
        self.assertFalse(self.store.list_recipients()[0]["enabled"])

        self.store.set_enabled(row_id, True)
        self.assertTrue(self.store.list_recipients()[0]["enabled"])

    def test_delete_removes_only_the_named_row(self):
        self.store.add_recipient("a@example.com", "keep@example.net", None)
        self.store.add_recipient("a@example.com", "drop@example.net", None)
        drop_id = next(
            row["id"] for row in self.store.list_recipients()
            if row["recipient"] == "drop@example.net"
        )

        self.store.delete_recipient(drop_id)

        self.assertEqual(
            [row["recipient"] for row in self.store.list_recipients()],
            ["keep@example.net"],
        )

    def test_unknown_ids_are_no_ops(self):
        self.store.add_recipient("a@example.com", "a@example.net", None)

        self.store.set_enabled(999_999, False)
        self.store.delete_recipient(999_999)

        rows = self.store.list_recipients()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["enabled"])