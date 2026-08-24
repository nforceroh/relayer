#!/usr/bin/env python3
"""relayer-forward -- forwards the raw message to Relayer's /ingest endpoint.

Runs as a Dovecot Sieve `pipe :copy` target for every mailbox on the
server. Deliberately dumb: no MySQL knowledge, no mailbox-specific logic
here at all -- Relayer decides what (if anything) happens.

Always exits 0. A forwarding hiccup must never block or delay real
mailbox delivery.
"""
import sys
import urllib.request

TOKEN_PATH = "/data/secrets/relayer-token"
RELAYER_URL = "http://relayer.mail.svc.cluster.local:8080/ingest"
TIMEOUT_SECONDS = 5


def main() -> int:
    try:
        raw = sys.stdin.buffer.read()
        with open(TOKEN_PATH, "r") as f:
            token = f.read().strip()

        req = urllib.request.Request(
            RELAYER_URL,
            data=raw,
            method="POST",
            headers={"Authorization": f"Bearer {token}"},
        )
        urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS)
    except Exception:
        pass  # swallow everything -- see module docstring
    return 0


if __name__ == "__main__":
    sys.exit(main())
