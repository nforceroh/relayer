-- Seed data for local docker-compose testing only.
-- Feel free to add/remove rows here, or just use the web UI at
-- http://localhost:8080 once the stack is up.

INSERT INTO forward_recipients (mailbox, recipient, label) VALUES
  ('toyota@martintwingles.com', 'sylvain@nforcer.com', 'test recipient 1'),
  ('toyota@martintwingles.com', 'faithmartin2006@gmail.com', 'test recipient 2');
