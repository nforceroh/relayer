# Agent guidelines

## Project map

- `app/main.py` exposes `create_app(settings, store)`: the Flask app is built from loaded settings and a recipient store; `wsgi.py` wires production, tests construct their own app with an `InMemoryRecipientStore`. `app/store.py` defines the recipient store interface with `app/db.py` as its MySQL adapter and `InMemoryRecipientStore` for tests; `app/mailbox_directory.py` groups rows into the mailbox view; `app/mailer.py` handles forwarding (transport is injectable: `process_raw_message(raw, recipients_lookup, send_message=None)`; tests pass a fake).
- The UI is server-rendered Jinja in `app/templates/` and uses Pico CSS. There is no frontend build system.
- `forward_recipients` is the source of truth. Mailboxes are derived by grouping recipient rows; a mailbox starts existing when its first recipient is added.
- `dovecot-side/` contains the production delivery hook. `k8s/` and `Dockerfile` describe production; `docker-compose.yml` and `Dockerfile.dev` are for local development.

## Change conventions

- Follow the existing Flask, Jinja, and parameterized PyMySQL patterns. Normalize mailbox and recipient addresses consistently with the store adapters in `app/store.py` and `app/db.py`. Use the domain terms in `GLOSSARY.md` (forward, mailbox, recipient) in code and conversation.
- Keep the UI server-rendered in `app/templates/index.html`; shared structure lives in `app/templates/_macros.html`. There is no prototype mode.
- Preserve the documented fail-open behavior of inbound delivery and forwarding. See `README.md` for architecture and operational details.
- Keep Python dependencies pinned in `requirements.txt`; avoid adding frontend tooling for server-rendered UI changes.

## Validation

- Run `python -m unittest discover -s tests -v` for all tests; `python -m unittest tests.test_mailer -v` covers the forward pipeline and composition.
- The recipient store contract lives in `tests/store_contract.py` and runs against the in-memory adapter always. To check the MySQL adapter for drift, point it at a database (the local Compose stack works):
  `TEST_DB_HOST=127.0.0.1 TEST_DB_USER=relayer TEST_DB_PASSWORD=relayerpass TEST_DB_DATABASE=mail python -m unittest tests.test_store_mysql -v`
  These tests truncate `forward_recipients`, so only run them against a database you are willing to lose data from.
- Run `docker compose config --quiet` after Compose changes; use the local stack for database integration as described in `README.md`.
- MariaDB init scripts run only for a fresh data directory. After changing `schema.sql` or seed scripts, account for the existing volume; `docker compose down -v` deletes local database data and should only be used when a reset is intended.

## Reports

- Save architecture-review HTML reports under `docs/` (e.g. `docs/architecture-review-YYYYMMDD.html`) instead of the OS temp directory, so they stay with the repo.
