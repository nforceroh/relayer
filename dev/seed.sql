-- Seed data for local docker-compose testing only.
-- These are documentation addresses (RFC 2606 reserves example.com /
-- example.net), so nothing here points at a real mailbox.
-- Feel free to add/remove rows, or just use the web UI at
-- http://localhost:8080 once the stack is up.

INSERT INTO forward_recipients (mailbox, recipient, label) VALUES
  ('inbox@example.com', 'person@example.net', 'test recipient 1'),
  ('inbox@example.com', 'other@example.org', 'test recipient 2');
