"""Turns an inbound raw message into outbound forwards."""

import email
import email.policy
import logging
import os
import re
import smtplib
from email.message import EmailMessage

log = logging.getLogger("relayer.mailer")

POSTFIX_HOST = os.environ.get("POSTFIX_HOST", "postfix")
POSTFIX_PORT = int(os.environ.get("POSTFIX_PORT", "25"))

CODE_PATTERN = re.compile(r"\b(\d{4,8})\b")


def resolve_mailbox(original: email.message.Message) -> str | None:
    for header_name in ("Delivered-To", "X-Original-To", "Envelope-To"):
        value = original.get(header_name)
        if value:
            match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", value)
            if match:
                return match.group(0).lower()
    return None


def _extract_body_text(original: email.message.Message) -> str:
    if original.is_multipart():
        for part in original.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_content()
                except Exception:
                    return ""
        return ""
    try:
        return original.get_content()
    except Exception:
        return ""


def _extract_code(subject: str, body_text: str) -> str | None:
    match = CODE_PATTERN.search(subject) or CODE_PATTERN.search(body_text or "")
    return match.group(1) if match else None


def build_forward(mailbox: str, original: email.message.Message, recipient: str) -> EmailMessage:
    original_from = original.get("From", "unknown sender")
    original_subject = original.get("Subject", "(no subject)")
    body_text = _extract_body_text(original)
    code = _extract_code(original_subject, body_text)
    subject_prefix = f"[Code: {code}] " if code else ""

    msg = EmailMessage()
    msg["From"] = mailbox  # the mailbox's own (verified) domain -- no rewriting needed
    msg["To"] = recipient
    msg["Subject"] = f"{subject_prefix}Fwd: {original_subject}"
    msg.set_content(
        f"Forwarded message, originally from: {original_from}\n"
        f"Originally sent to: {mailbox}\n\n"
        f"----- Original message -----\n\n"
        f"{body_text}"
    )
    msg.add_attachment(
        original.as_bytes(),
        maintype="message",
        subtype="rfc822",
        filename="original.eml",
    )
    return msg


def send(msg: EmailMessage) -> None:
    with smtplib.SMTP(POSTFIX_HOST, POSTFIX_PORT, timeout=10) as smtp:
        smtp.send_message(msg)


def process_raw_message(raw: bytes, recipients_lookup) -> dict:
    """Parses raw bytes, looks up recipients (via the passed-in callable),
    sends forwards, and returns a small summary dict for logging/response."""
    try:
        original = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception:
        log.exception("failed to parse incoming message")
        return {"status": "parse_error"}

    mailbox = resolve_mailbox(original)
    if not mailbox:
        log.warning("could not determine target mailbox; headers=%s", list(original.keys()))
        return {"status": "no_mailbox"}

    try:
        recipients = recipients_lookup(mailbox)
    except Exception:
        log.exception("recipient lookup failed for %s", mailbox)
        return {"status": "lookup_error", "mailbox": mailbox}

    if not recipients:
        log.info("no active recipients for %s", mailbox)
        return {"status": "no_recipients", "mailbox": mailbox}

    sent, failed = [], []
    for recipient in recipients:
        try:
            send(build_forward(mailbox, original, recipient))
            sent.append(recipient)
        except Exception:
            log.exception("failed to forward %s -> %s", mailbox, recipient)
            failed.append(recipient)

    return {"status": "ok", "mailbox": mailbox, "sent": sent, "failed": failed}
