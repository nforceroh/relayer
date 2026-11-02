"""Turns an inbound raw message into outbound forwards."""

import email
import email.policy
import email.utils
import html
import logging
import os
import re
import smtplib
from email.message import EmailMessage

log = logging.getLogger("relayer.mailer")

CODE_PATTERN = re.compile(r"\b(\d{4,8})\b")
TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"[ \t]*\n[ \t]*")


def resolve_mailbox(original: email.message.Message) -> str | None:
    for header_name in ("Delivered-To", "X-Original-To", "Envelope-To"):
        value = original.get(header_name)
        if value:
            match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", value)
            if match:
                return match.group(0).lower()
    return None


def _extract_parts(original: email.message.Message) -> tuple[str, str]:
    """Returns (plain_text, html_text) -- either may be empty, but not both
    unless the message genuinely has neither part."""
    plain_text = ""
    html_text = ""

    if original.is_multipart():
        for part in original.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain" and not plain_text:
                try:
                    plain_text = part.get_content()
                except Exception:
                    pass
            elif content_type == "text/html" and not html_text:
                try:
                    html_text = part.get_content()
                except Exception:
                    pass
        return plain_text, html_text

    content_type = original.get_content_type()
    try:
        content = original.get_content()
    except Exception:
        return "", ""
    if content_type == "text/html":
        return "", content
    return content, ""


def _html_to_text(html_text: str) -> str:
    """Rough HTML-to-text fallback for plain-text mail clients -- strips
    tags and decodes entities. Not meant to be pretty, just readable."""
    text = TAG_PATTERN.sub(" ", html_text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = WHITESPACE_PATTERN.sub("\n", text)
    return text.strip()


def _extract_code(subject: str, plain_text: str, html_text: str) -> str | None:
    for candidate in (subject, plain_text, html_text):
        match = CODE_PATTERN.search(candidate or "")
        if match:
            return match.group(1)
    return None


def build_forward(mailbox: str, original: email.message.Message, recipient: str) -> EmailMessage:
    original_from = original.get("From", "unknown sender")
    original_subject = original.get("Subject", "(no subject)")
    plain_text, html_text = _extract_parts(original)
    code = _extract_code(original_subject, plain_text, html_text)
    subject_prefix = f"[Code: {code}] " if code else ""

    preamble_plain = (
        f"Forwarded message, originally from: {original_from}\n"
        f"Originally sent to: {mailbox}\n\n"
        f"----- Original message -----\n\n"
    )

    msg = EmailMessage()
    msg["From"] = mailbox  # the mailbox's own (verified) domain -- no rewriting needed
    msg["To"] = recipient
    msg["Subject"] = f"{subject_prefix}Fwd: {original_subject}"
    msg["Message-ID"] = email.utils.make_msgid(domain=mailbox.split("@", 1)[-1])

    if html_text:
        # Plain-text part is a fallback for text-only clients -- prefer the
        # original's own plain-text part if it had one, otherwise derive a
        # rough readable version from the HTML rather than dumping raw markup.
        plain_body = preamble_plain + (plain_text or _html_to_text(html_text))
        msg.set_content(plain_body)

        preamble_html = (
            f"<p>Forwarded message, originally from: {html.escape(original_from)}<br>"
            f"Originally sent to: {html.escape(mailbox)}</p><hr>"
        )
        msg.add_alternative(preamble_html + html_text, subtype="html")
    else:
        msg.set_content(preamble_plain + plain_text)

    msg.add_attachment(
        original.as_bytes(),
        maintype="message",
        subtype="rfc822",
        filename="original.eml",
    )
    return msg


def smtp_send_message_from_env(settings=None) -> "callable[[EmailMessage], None]":
    """Builds the real SMTP transport from loaded settings (or from the
    environment directly when settings are not supplied).

    Reads configuration at call time (not import time) so tests never
    construct the real transport.
    """
    if settings is None:
        debug_smtp = os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"
        host = os.environ.get("POSTFIX_HOST", "postfix")
        port = int(os.environ.get("POSTFIX_PORT", "25"))
    else:
        debug_smtp = settings.debug_smtp
        host = settings.postfix_host
        port = settings.postfix_port

    def send_message(msg: EmailMessage) -> None:
        log.debug(
            "smtp connect: host=%s port=%s from=%s to=%s subject=%r",
            host, port, msg["From"], msg["To"], msg["Subject"],
        )
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if debug_smtp:
                # Prints the raw SMTP conversation (EHLO/MAIL FROM/RCPT TO/DATA
                # and the server's responses) to stderr, which shows up
                # alongside the rest of the container's logs.
                smtp.set_debuglevel(1)
            refused = smtp.send_message(msg)
            if refused:
                # send_message only raises if ALL recipients are refused; a
                # partial refusal (rare here, single-recipient sends) returns
                # a dict instead and would otherwise pass silently.
                log.warning("smtp partial refusal: %s", refused)
            else:
                log.debug("smtp accepted: to=%s", msg["To"])

    return send_message


def process_raw_message(raw: bytes, recipients_lookup, send_message=None) -> dict:
    """Parses raw bytes, looks up recipients (via the passed-in callable),
    sends forwards through the given transport, and returns a small
    summary dict for logging/response.

    send_message is the transport seam: a callable taking the composed
    EmailMessage. When omitted, the real SMTP transport is built from
    environment configuration; tests pass a fake instead.
    """
    if send_message is None:
        send_message = smtp_send_message_from_env()
    try:
        original = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception:
        log.exception("failed to parse incoming message")
        return {"status": "parse_error"}

    mailbox = resolve_mailbox(original)
    if not mailbox:
        log.warning("could not determine target mailbox; headers=%s", list(original.keys()))
        return {"status": "no_mailbox"}

    log.debug("resolved mailbox=%s subject=%r from=%r", mailbox, original.get("Subject"), original.get("From"))

    try:
        recipients = recipients_lookup(mailbox)
    except Exception:
        log.exception("recipient lookup failed for %s", mailbox)
        return {"status": "lookup_error", "mailbox": mailbox}

    log.debug("recipients for %s: %s", mailbox, recipients)

    if not recipients:
        log.info("no active recipients for %s", mailbox)
        return {"status": "no_recipients", "mailbox": mailbox}

    sent, failed = [], []
    for recipient in recipients:
        try:
            send_message(build_forward(mailbox, original, recipient))
            sent.append(recipient)
        except Exception:
            log.exception("failed to forward %s -> %s", mailbox, recipient)
            failed.append(recipient)

    return {"status": "ok", "mailbox": mailbox, "sent": sent, "failed": failed}
