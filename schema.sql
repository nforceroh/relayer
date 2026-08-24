-- Table to manage per-mailbox external forwarding destinations.
-- Add this to the same database Dovecot/vimbadmin already use (e.g. `mail`),
-- or a separate one -- either works, since Relayer connects with its own
-- dedicated DB user rather than reusing Dovecot's.

CREATE TABLE IF NOT EXISTS forward_recipients (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    mailbox     VARCHAR(255) NOT NULL,      -- e.g. toyota@martintwingles.com
    recipient   VARCHAR(255) NOT NULL,      -- e.g. sylvain@nforcer.com
    label       VARCHAR(255) NULL,          -- optional friendly note
    enabled     TINYINT(1) NOT NULL DEFAULT 1,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_mailbox_recipient (mailbox, recipient),
    KEY idx_mailbox_enabled (mailbox, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Relayer needs ONE user with SELECT/INSERT/UPDATE/DELETE on just this
-- table -- both the web UI and the /ingest lookup use it.
--
-- Note: your existing `mailro` user (used by Dovecot) is presumably
-- read-only, per its name -- don't reuse it here, since the web UI needs
-- to write. Create a dedicated user instead:
--
-- CREATE USER 'relayer'@'%' IDENTIFIED BY 'CHANGE_ME';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON mail.forward_recipients TO 'relayer'@'%';
-- FLUSH PRIVILEGES;
--
-- (adjust 'mail' above if your database name differs, and '%' to a
-- narrower host/CIDR if your MySQL setup restricts by source host)

-- Seed data matching your current aliases, as a starting point.
-- Note: "andi@martintwingles.com" is a *local* mailbox on your own domain,
-- not an external address -- that's fine, the forward script just sends
-- it as a normal SMTP message and Postfix delivers it locally like any
-- other mail, no special-casing needed.
INSERT INTO forward_recipients (mailbox, recipient, label) VALUES
  ('toyota@martintwingles.com', 'sylvain@nforcer.com', NULL),
  ('toyota@martintwingles.com', 'sylvainmartin73@gmail.com', NULL),
  ('toyota@martintwingles.com', 'faithmartin2006@gmail.com', NULL),
  ('aidvantage@martintwingles.com', 'sylvainmartin73@gmail.com', NULL),
  ('aidvantage@martintwingles.com', 'mercedesariel2000@gmail.com', NULL),
  ('aidvantage@martintwingles.com', 'sylvain@nforcer.com', NULL),
  ('aidvantage@martintwingles.com', 'andi@martintwingles.com', NULL);
