import logging
from functools import wraps

from flask import Flask, Response, flash, redirect, render_template, request, url_for

from . import mailer
from .config import Settings, load
from .mailbox_directory import build_view
from .store import RecipientStore, store_from_env


def create_app(settings: Settings, store: RecipientStore) -> Flask:
    """Builds the Flask app from explicit inputs.

    The interface: pass loaded settings and a recipient store; the app
    wires routes, auth, and template selection around them. wsgi.py
    calls create_app(load(), store_from_env(settings)); tests call it
    with an InMemoryRecipientStore and no environment at all.
    """
    log_level = "DEBUG" if settings.debug_smtp else "INFO"
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
    log = logging.getLogger("relayer")
    log.setLevel(getattr(logging, log_level, logging.INFO))

    app = Flask(__name__)
    app.secret_key = settings.secret_key

    # ---- auth -------------------------------------------------------------

    def requires_basic_auth(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            auth = request.authorization
            if not settings.admin_pass:
                log.warning("ADMIN_PASS not set -- refusing all UI access until configured")
                return Response("Admin UI not configured", 503)
            if not auth or auth.username != settings.admin_user or auth.password != settings.admin_pass:
                return Response(
                    "Authentication required", 401,
                    {"WWW-Authenticate": 'Basic realm="Relayer"'},
                )
            return f(*args, **kwargs)
        return wrapped

    # ---- web UI -------------------------------------------------------------

    @app.route("/")
    @requires_basic_auth
    def index():
        view = build_view(store.list_recipients(), request.args.get("mailbox"))
        prototype_enabled = settings.ui_prototype
        prototype_variant = request.args.get("variant", "a") if prototype_enabled else "c"
        if prototype_enabled and prototype_variant not in {"a", "b", "c"}:
            prototype_variant = "a"
        template = "prototype.html" if prototype_enabled else "index.html"
        return render_template(
            template,
            grouped=view["grouped"],
            selected_mailbox=view["selected_mailbox"],
            selected_rows=view["selected_rows"],
            prototype_enabled=prototype_enabled,
            prototype_variant=prototype_variant,
        )

    @app.route("/recipients", methods=["POST"])
    @requires_basic_auth
    def add_recipient():
        mailbox = request.form.get("mailbox", "").strip()
        recipient = request.form.get("recipient", "").strip()
        label = request.form.get("label", "").strip()

        if not mailbox or not recipient:
            flash("Mailbox and recipient are both required.", "error")
            return redirect(url_for("index"))

        store.add_recipient(mailbox, recipient, label)
        flash(f"Added {recipient} to {mailbox}.", "success")
        return redirect(url_for("index", mailbox=mailbox.lower()))

    @app.route("/recipients/<int:row_id>/toggle", methods=["POST"])
    @requires_basic_auth
    def toggle_recipient(row_id):
        enabled = request.form.get("enabled") == "1"
        mailbox = request.form.get("mailbox", "").strip().lower()
        store.set_enabled(row_id, enabled)
        flash("Updated.", "success")
        return redirect(url_for("index", mailbox=mailbox or None))

    @app.route("/recipients/<int:row_id>/delete", methods=["POST"])
    @requires_basic_auth
    def delete_recipient(row_id):
        mailbox = request.form.get("mailbox", "").strip().lower()
        store.delete_recipient(row_id)
        flash("Removed.", "success")
        return redirect(url_for("index", mailbox=mailbox or None))

    # ---- ingest (called by the Dovecot-side pipe script) ---------------------

    def requires_ingest_token(f):
        """Bearer-token gate for the ingest route, mirroring
        requires_basic_auth: one place checks, logs, and rejects."""
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not settings.ingest_token:
                log.error("INGEST_TOKEN not configured; refusing ingest")
                return Response("not configured", 503)

            auth_header = request.headers.get("Authorization", "")
            expected = f"Bearer {settings.ingest_token}"

            log.debug(
                "ingest auth check: remote=%s got_header=%s got_len=%d expected_len=%d "
                "got_tail=%r expected_tail=%r match=%s",
                request.remote_addr,
                bool(auth_header),
                len(auth_header),
                len(expected),
                auth_header[-6:] if auth_header else "",
                expected[-6:],
                auth_header == expected,
            )

            if auth_header != expected:
                log.warning(
                    "ingest rejected: remote=%s content_length=%s reason=token_mismatch",
                    request.remote_addr, request.content_length,
                )
                return Response("unauthorized", 401)
            return f(*args, **kwargs)
        return wrapped

    @app.route("/ingest", methods=["POST"])
    @requires_ingest_token
    def ingest():
        raw = request.get_data()
        log.debug("ingest accepted: remote=%s bytes=%d", request.remote_addr, len(raw))

        result = mailer.process_raw_message(raw, store.get_active_recipients)
        log.info("ingest result: %s", result)
        return result, 200

    # ---- health ---------------------------------------------------------------

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    return app
