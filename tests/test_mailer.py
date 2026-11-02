"""Tests for the forward-composition module (app/mailer.py).

Pipeline tests run process_raw_message through a fake transport (a
callable that records messages); composition tests exercise the pure
functions directly. No network, no MailHog.
"""

import unittest
from email.message import EmailMessage

from app import mailer


def make_raw_message(
    *,
    delivered_to: str | None = "toyota@example.com",
    subject: str = "Your login code",
    body: str = "Your code is 482913.",
    from_addr: str = "noreply@service.example",
) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["Subject"] = subject
    msg.set_content(body)
    # Relayer resolves the target mailbox from delivery headers, not To.
    if delivered_to is not None:
        msg["Delivered-To"] = delivered_to
    return bytes(msg)


class FakeTransport:
    def __init__(self):
        self.sent: list[EmailMessage] = []
        self.fail_for: set[str] = set()

    def __call__(self, msg: EmailMessage) -> None:
        if msg["To"] in self.fail_for:
            raise RuntimeError("smtp refused")
        self.sent.append(msg)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.lookup = lambda mailbox: ["a@example.net", "b@example.net"]

    def test_happy_path_sends_one_forward_per_recipient(self):
        result = mailer.process_raw_message(
            make_raw_message(), self.lookup, self.transport
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mailbox"], "toyota@example.com")
        self.assertEqual(result["sent"], ["a@example.net", "b@example.net"])
        self.assertEqual(result["failed"], [])
        self.assertEqual(len(self.transport.sent), 2)
        self.assertEqual(
            [msg["To"] for msg in self.transport.sent],
            ["a@example.net", "b@example.net"],
        )

    def test_garbage_bytes_yield_no_mailbox(self):
        # Python's email parser is lenient: bytes without any headers
        # parse into an empty message rather than raising, so this path
        # surfaces as "no mailbox" rather than "parse error".
        result = mailer.process_raw_message(
            b"\x00\x01not-a-message", self.lookup, self.transport
        )

        self.assertEqual(result["status"], "no_mailbox")
        self.assertEqual(self.transport.sent, [])

    def test_missing_mailbox_headers_report_no_mailbox(self):
        result = mailer.process_raw_message(
            make_raw_message(delivered_to=None), self.lookup, self.transport
        )

        self.assertEqual(result["status"], "no_mailbox")
        self.assertEqual(self.transport.sent, [])

    def test_lookup_failure_reports_lookup_error(self):
        def broken_lookup(mailbox):
            raise RuntimeError("db down")

        result = mailer.process_raw_message(
            make_raw_message(), broken_lookup, self.transport
        )

        self.assertEqual(result["status"], "lookup_error")
        self.assertEqual(result["mailbox"], "toyota@example.com")
        self.assertEqual(self.transport.sent, [])

    def test_no_recipients_reports_no_recipients(self):
        result = mailer.process_raw_message(
            make_raw_message(), lambda mailbox: [], self.transport
        )

        self.assertEqual(result["status"], "no_recipients")
        self.assertEqual(self.transport.sent, [])

    def test_one_failing_recipient_does_not_block_the_rest(self):
        self.transport.fail_for.add("a@example.net")

        result = mailer.process_raw_message(
            make_raw_message(), self.lookup, self.transport
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["failed"], ["a@example.net"])
        self.assertEqual(result["sent"], ["b@example.net"])
        self.assertEqual(len(self.transport.sent), 1)


class CompositionTests(unittest.TestCase):
    def test_forward_carries_mailbox_as_sender_and_original_as_attachment(self):
        original = EmailMessage()
        original["From"] = "noreply@service.example"
        original["Subject"] = "Your login code"
        original.set_content("Your code is 482913.")

        forward = mailer.build_forward("toyota@example.com", original, "a@example.net")

        self.assertEqual(forward["From"], "toyota@example.com")
        self.assertEqual(forward["To"], "a@example.net")
        self.assertEqual(forward["Subject"], "[Code: 482913] Fwd: Your login code")
        attachments = [part for part in forward.walk() if part.get_filename()]
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "original.eml")

    def test_subject_without_code_gets_no_prefix(self):
        original = EmailMessage()
        original["From"] = "noreply@service.example"
        original["Subject"] = "Weekly newsletter"
        original.set_content("No codes in here at all.")

        forward = mailer.build_forward("toyota@example.com", original, "a@example.net")

        self.assertEqual(forward["Subject"], "Fwd: Weekly newsletter")

    def test_resolve_mailbox_prefers_delivered_to(self):
        original = EmailMessage()
        original["Delivered-To"] = "toyota@example.com"
        original["X-Original-To"] = "ignored@example.com"

        self.assertEqual(mailer.resolve_mailbox(original), "toyota@example.com")

    def test_resolve_mailbox_falls_back_to_x_original_to(self):
        original = EmailMessage()
        original["X-Original-To"] = "aidvantage@example.com"

        self.assertEqual(mailer.resolve_mailbox(original), "aidvantage@example.com")

    def test_resolve_mailbox_returns_none_without_address_headers(self):
        self.assertIsNone(mailer.resolve_mailbox(EmailMessage()))


if __name__ == "__main__":
    unittest.main()
