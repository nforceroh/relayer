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


class RouteWiringTests(unittest.TestCase):
    def test_ingest_route_passes_a_transport_to_the_pipeline(self):
        # Regression: the config refactor left process_raw_message's
        # default transport calling the factory with no settings, which
        # 500'd every production ingest. The route must wire the
        # transport explicitly.
        from unittest import mock

        from app.config import Settings
        from app.main import create_app
        from app.store import InMemoryRecipientStore

        settings = Settings.for_tests()
        store = InMemoryRecipientStore([
            {"id": 1, "mailbox": "toyota@example.com", "recipient": "a@example.net",
             "label": None, "enabled": 1, "created_at": "2026-11-02 12:00:00"}])
        with mock.patch.object(mailer, "smtp_transport") as factory:
            factory.return_value = lambda msg: None
            app = create_app(settings, store)
            client = app.test_client()
            response = client.post(
                "/ingest", headers={"Authorization": "Bearer test-ingest-token"},
                data=b"From: x@y\nDelivered-To: toyota@example.com\nSubject: hi\n\nbody")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")
        factory.assert_called_once_with(settings)


class ExtractionTests(unittest.TestCase):
    """The message-extraction seam: how messy real-world mail becomes
    (plain_text, html_text) for forward composition."""

    @staticmethod
    def multipart_message(*parts):
        msg = EmailMessage()
        msg["From"] = "noreply@service.example"
        msg["Subject"] = "Your login code"
        msg.make_mixed()
        for content_type, content in parts:
            msg.add_attachment(content.encode(), maintype="text",
                               subtype=content_type.split("/")[1])
        return msg

    def test_multipart_with_both_parts_extracts_both(self):
        original = self.multipart_message(
            ("text/plain", "Your code is 482913."),
            ("text/html", "<p>Your code is <b>482913</b>.</p>"),
        )

        plain, html = mailer._extract_parts(original)

        self.assertIn("482913", plain)
        self.assertIn("<b>482913</b>", html)

    def test_html_only_message_returns_empty_plain(self):
        original = EmailMessage()
        original["From"] = "noreply@service.example"
        original["Subject"] = "Newsletter"
        original.set_content("<p>Hello <b>world</b></p>", subtype="html")

        plain, html = mailer._extract_parts(original)

        self.assertEqual(plain, "")
        self.assertIn("<b>world</b>", html)

    def test_plain_only_message_returns_empty_html(self):
        original = EmailMessage()
        original["From"] = "noreply@service.example"
        original["Subject"] = "Note"
        original.set_content("Just text.")

        plain, html = mailer._extract_parts(original)

        # The email library appends a trailing newline to text content.
        self.assertEqual(plain, "Just text.\n")
        self.assertEqual(html, "")

    def test_unreadable_part_is_skipped_not_fatal(self):
        # A part whose content cannot be decoded must not break extraction;
        # the other part still comes through.
        original = self.multipart_message(
            ("text/plain", "readable part"),
            ("text/html", "<p>fine</p>"),
        )
        for part in original.walk():
            if part.get_content_type() == "text/plain":
                part.set_payload(b"\xff\xfe\xfa")  # undecodable bytes
                break

        plain, html = mailer._extract_parts(original)

        self.assertIn("<p>fine</p>", html)

    def test_html_to_text_strips_tags_and_decodes_entities(self):
        result = mailer._html_to_text(
            "<p>Hello&nbsp;& welcome</p>\n  <b>bold</b>"
        )

        # &nbsp; decodes to a non-breaking space, which the whitespace
        # normalization keeps (it is not a plain space or tab).
        self.assertEqual(result, "Hello\xa0& welcome\nbold")

    def test_html_to_text_of_empty_string_is_empty(self):
        self.assertEqual(mailer._html_to_text(""), "")


class HtmlForwardTests(unittest.TestCase):
    """The HTML branch of build_forward: the path most real mail takes."""

    def html_original(self, body: str = "<p>Hello <b>world</b></p>") -> EmailMessage:
        original = EmailMessage()
        original["From"] = 'Sender Name <sender@example.net>'
        original["Subject"] = "Weekly update"
        original.set_content(body, subtype="html")
        return original

    def test_html_forward_has_both_plain_and_html_parts(self):
        forward = mailer.build_forward(
            "toyota@example.com", self.html_original(), "a@example.net")

        parts = {part.get_content_type() for part in forward.walk()}
        self.assertIn("text/plain", parts)
        self.assertIn("text/html", parts)
        self.assertIn("multipart/alternative", parts)

    def test_html_forward_escapes_sender_and_mailbox_in_preamble(self):
        original = self.html_original()
        original.replace_header("From", 'Evil <script>alert(1)</script> <x@y.z>')

        forward = mailer.build_forward(
            "toyota@example.com", original, "a@example.net")

        html_part = next(part for part in forward.walk()
                         if part.get_content_type() == "text/html")
        html_body = html_part.get_content()
        # The raw <script> must not appear in the HTML preamble; it is
        # escaped so it renders as text, never executes.
        self.assertNotIn("<script>", html_body)
        self.assertIn("&lt;script&gt;", html_body)

    def test_html_forward_derives_plain_fallback_from_html(self):
        original = self.html_original("<p>Hello <b>world</b></p>")

        forward = mailer.build_forward(
            "toyota@example.com", original, "a@example.net")

        plain_part = next(part for part in forward.walk()
                          if part.get_content_type() == "text/plain")
        plain_body = plain_part.get_content()
        self.assertIn("Hello world", plain_body)
        self.assertIn("Forwarded message, originally from:", plain_body)

    def test_html_forward_keeps_original_plain_when_present(self):
        original = EmailMessage()
        original["From"] = "sender@example.net"
        original["Subject"] = "Both parts"
        original.set_content("Plain truth.")
        original.add_alternative("<p>Html truth.</p>", subtype="html")

        forward = mailer.build_forward(
            "toyota@example.com", original, "a@example.net")

        plain_part = next(part for part in forward.walk()
                          if part.get_content_type() == "text/plain")
        self.assertIn("Plain truth.", plain_part.get_content())
