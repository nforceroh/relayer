import unittest
from unittest import mock

from tests import _bootstrap  # noqa: F401  (sets required env before app.main loads)

from app import main
from app.store import InMemoryRecipientStore


def seed_store(*rows):
    return InMemoryRecipientStore([
        {
            "id": row_id,
            "mailbox": mailbox,
            "recipient": recipient,
            "label": label,
            "enabled": enabled,
            "created_at": "2026-11-02 12:00:00",
        }
        for row_id, (mailbox, recipient, label, enabled) in enumerate(rows, start=1)
    ])


class ProductionSidebarTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()
        self.auth = ("admin", "test-password")
        patcher = mock.patch.object(main, "ADMIN_PASS", "test-password")
        patcher.start()
        self.addCleanup(patcher.stop)

    def use_store(self, store):
        old_store = main.store
        main.store = store
        self.addCleanup(setattr, main, "store", old_store)

    def test_default_page_renders_persistent_sidebar(self):
        self.use_store(seed_store(("old@example.com", "person@example.net", "Personal", 1)))
        with mock.patch.dict(main.os.environ, {"UI_PROTOTYPE": "0"}):
            response = self.client.get("/", auth=self.auth)

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('data-theme="dark"', page)
        self.assertIn('class="prototype-shell variant-c"', page)
        self.assertIn('aria-label="Forwarding mailboxes"', page)
        self.assertIn("Create mailbox", page)
        self.assertIn('method="post" action="/recipients"', page)
        self.assertIn('type="hidden" name="mailbox" value="old@example.com"', page)
        self.assertIn('data-persistent-toggle', page)
        self.assertIn('action="/recipients/1/delete"', page)
        self.assertNotIn("UI prototype:", page)

    def test_creating_mailbox_saves_first_recipient_and_selects_it(self):
        self.use_store(InMemoryRecipientStore())
        with mock.patch.dict(main.os.environ, {"UI_PROTOTYPE": "0"}):
            response = self.client.post(
                "/recipients",
                data={
                    "mailbox": "new@example.com",
                    "recipient": "first@example.net",
                    "label": "Personal",
                },
                auth=self.auth,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/?mailbox=new@example.com")
        self.assertEqual(
            main.store.list_recipients("new@example.com"),
            [{
                "id": 1,
                "mailbox": "new@example.com",
                "recipient": "first@example.net",
                "label": "Personal",
                "enabled": 1,
                "created_at": "1970-01-01 00:00:00",
            }],
        )

    def test_prototype_mode_keeps_preview_only_controls(self):
        self.use_store(seed_store(("old@example.com", "person@example.net", "Personal", 1)))
        with mock.patch.dict(main.os.environ, {"UI_PROTOTYPE": "1"}):
            response = self.client.get("/", auth=self.auth)

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("UI prototype:", page)
        self.assertIn("data-prototype-add-mailbox", page)
        self.assertIn("data-prototype-toggle", page)
        self.assertIn("data-prototype-remove", page)
        self.assertIn('aria-label="Prototype variations"', page)

    def test_recipient_actions_keep_current_mailbox_selected(self):
        self.use_store(seed_store(("old@example.com", "person@example.net", "Personal", 1)))
        with mock.patch.dict(main.os.environ, {"UI_PROTOTYPE": "0"}):
            toggle_response = self.client.post(
                "/recipients/1/toggle",
                data={"mailbox": "old@example.com", "enabled": "0"},
                auth=self.auth,
            )
            delete_response = self.client.post(
                "/recipients/1/delete",
                data={"mailbox": "old@example.com"},
                auth=self.auth,
            )

        self.assertEqual(toggle_response.headers["Location"], "/?mailbox=old@example.com")
        self.assertEqual(delete_response.headers["Location"], "/?mailbox=old@example.com")
        self.assertEqual(main.store.list_recipients(), [])


if __name__ == "__main__":
    unittest.main()
