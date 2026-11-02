# Glossary

Domain terms used across the code, tests, and docs. Use these names in
code, comments, and conversation.

**Forward**
The outbound message Relayer composes and sends: a new email from the
mailbox's own (verified) domain to one recipient, with the original
message attached as `original.eml`. Distinct from the original inbound
message, which is never re-sent itself.

**Mailbox**
A real Dovecot mailbox that receives inbound mail and forwards it
onward — e.g. `toyota@martintwingles.com`. Not a database entity: a
mailbox exists once its first recipient row does. The target of every
inbound delivery and the `From:` of every forward.

**Recipient**
An external address a mailbox forwards to — one row in
`forward_recipients`, with an optional label and an enabled flag.
Relayer sends one forward per active recipient.
