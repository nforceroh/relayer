import logging
import os
from functools import wraps

from flask import Flask, Response, flash, redirect, render_template, request, url_for

from . import db, mailer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("relayer")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

INGEST_TOKEN = os.environ.get("INGEST_TOKEN")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS")


# ---- auth -------------------------------------------------------------

def requires_basic_auth(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not ADMIN_PASS:
            log.warning("ADMIN_PASS not set -- refusing all UI access until configured")
            return Response("Admin UI not configured", 503)
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
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
    rows = db.list_recipients()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["mailbox"], []).append(row)
    return render_template("index.html", grouped=grouped)


@app.route("/recipients", methods=["POST"])
@requires_basic_auth
def add_recipient():
    mailbox = request.form.get("mailbox", "").strip()
    recipient = request.form.get("recipient", "").strip()
    label = request.form.get("label", "").strip()

    if not mailbox or not recipient:
        flash("Mailbox and recipient are both required.", "error")
        return redirect(url_for("index"))

    db.add_recipient(mailbox, recipient, label)
    flash(f"Added {recipient} to {mailbox}.", "success")
    return redirect(url_for("index"))


@app.route("/recipients/<int:row_id>/toggle", methods=["POST"])
@requires_basic_auth
def toggle_recipient(row_id):
    enabled = request.form.get("enabled") == "1"
    db.set_enabled(row_id, enabled)
    flash("Updated.", "success")
    return redirect(url_for("index"))


@app.route("/recipients/<int:row_id>/delete", methods=["POST"])
@requires_basic_auth
def delete_recipient(row_id):
    db.delete_recipient(row_id)
    flash("Removed.", "success")
    return redirect(url_for("index"))


# ---- ingest (called by the Dovecot-side pipe script) ---------------------

@app.route("/ingest", methods=["POST"])
def ingest():
    if not INGEST_TOKEN:
        log.error("INGEST_TOKEN not configured; refusing ingest")
        return Response("not configured", 503)

    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {INGEST_TOKEN}":
        return Response("unauthorized", 401)

    raw = request.get_data()
    result = mailer.process_raw_message(raw, db.get_active_recipients)
    log.info("ingest result: %s", result)
    return result, 200


# ---- health ---------------------------------------------------------------

@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200
