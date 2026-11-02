# Test bootstrap: app.config.load() validates required variables at
# import time, so tests provide minimal values before app.main loads.
import os

os.environ.setdefault("DB_USER", "test-relayer")
os.environ.setdefault("INGEST_TOKEN", "test-ingest-token")
