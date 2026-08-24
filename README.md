# Relayer

Relayer manages "forward this mailbox to a list of external addresses"
rules for a Postfix/Dovecot mail stack, without needing per-mailbox
Postfix `Goto` aliases or IMAP passwords. You manage the recipient list
per mailbox through a small web UI backed by MySQL; a tiny script on the
Dovecot side hands every delivered message to Relayer, which decides
whether to forward it and to whom.

## Why this exists

Plain Postfix `virtual_alias` "Goto" forwarding rewrites the envelope
recipient but leaves the original `From:` header untouched. Relay
providers that verify sender domains (e.g. SMTP2GO) will bounce that mail
with `550 From header sender domain not verified`, since the header still
shows the *original* external sender's domain, not yours.

Relayer avoids this entirely: each forwarding mailbox is a real Dovecot
mailbox, so incoming mail is delivered once for real (you keep a copy),
and Relayer independently composes and sends a *new* message to each
configured recipient with `From:` set to the mailbox's own (already
verified) domain -- there is no header to reject.

## Architecture

```
                    Dovecot pod (existing image, unchanged)
                    -----------------------------------------
Inbound mail  --->  LMTP delivery into real mailbox
                        |
                        +--> global Sieve: pipe :copy relayer-forward.sh
                                                  |
                                                  | HTTP POST, bearer token
                                                  v
                    Relayer pod (this project)
                    -----------------------------------------
                    /ingest   parses message, looks up recipients,
                              composes + sends forwards
                    /         web UI (Basic Auth) to manage recipients
                        |
                        +--> MySQL: forward_recipients table
                        +--> Postfix (or MailHog locally) :25 for outbound
```

Key point: Sieve is unconditional and identical for every mailbox on the
server. It has zero awareness of which mailboxes forward anywhere --
Relayer is the single source of truth for that, via one MySQL table. Adding
a new forwarding mailbox is a pure database change (through the web UI);
no Dovecot/Sieve edits, ever.

## Try it locally (docker-compose)

No Kubernetes, no real mail server needed -- this spins up MariaDB
(pre-seeded from `schema.sql` + `local/seed.sql`), Relayer itself (built
from `Dockerfile.dev`, a lightweight `python:3.12-alpine` build meant only
for fast local iteration -- **not** what runs in production, see below),
and [MailHog](https://github.com/mailhog/MailHog) standing in for Postfix
so you can actually see forwarded messages land, in a browser.

```bash
docker compose up --build
```

Then:

1. Open **http://localhost:8080** -- log in with `admin` / `admin` (set
   in `docker-compose.yml`, change before using this anywhere real). You
   should see `toyota@martintwingles.com` already seeded with two
   recipients from `local/seed.sql`.

2. Simulate an inbound message hitting `/ingest` (this is exactly what
   the Dovecot pipe script does in production):

   ```bash
   curl -s -X POST \
     -H "Authorization: Bearer local-dev-token" \
     --data-binary @local/sample-message.eml \
     http://localhost:8080/ingest
   ```

   You should get back `{"status": "ok", "mailbox": "toyota@martintwingles.com", "sent": [...], "failed": []}`.

3. Open **http://localhost:8025** (MailHog's web UI) -- you should see
   two forwarded copies of the sample login-code email, one per seeded
   recipient, each with `From: toyota@martintwingles.com` and a
   `[Code: 482913]` prefix pulled out of the message automatically.

4. Try adding/removing a recipient in the web UI, then re-run the `curl`
   command above and check MailHog again to confirm it picked up the
   change immediately (no restart needed).

`docker compose down -v` tears it all down, including the database
volume, so you get a clean slate next time.

## Production install (Kubernetes)

### 1. Database

Run `schema.sql` against your existing mail database (the same one
Dovecot/vimbadmin use, e.g. `mail`, or a separate one if you'd rather
isolate it):

```bash
mysql -u root -p mail < schema.sql
```

Create Relayer's own dedicated MySQL user (do **not** reuse Dovecot's
`mailro` -- that's presumably read-only, per its name, and the web UI
needs to write):

```sql
CREATE USER 'relayer'@'%' IDENTIFIED BY 'CHANGE_ME';
GRANT SELECT, INSERT, UPDATE, DELETE ON mail.forward_recipients TO 'relayer'@'%';
FLUSH PRIVILEGES;
```

Narrow `'%'` to a specific host/CIDR if your MySQL setup restricts by
source host. `mailro` continues to be used by Dovecot exactly as it is
today -- Relayer never touches it.

### 2. Build and push the image

Production builds from `Dockerfile` (not `Dockerfile.dev`, which is
local-only) -- based on your shared `ghcr.io/nforceroh/k8s-alpine-baseimage:3.24`,
same s6-overlay pattern as your Dovecot and ViMbAdmin images. It runs
Gunicorn as an s6 longrun service (`content/etc/s6-overlay/s6-rc.d/relayer/`)
under a dedicated `relayer` user, rather than a Docker `CMD` -- matching
how `/init` starts services in your other images.

```bash
docker build -t ghcr.io/nforceroh/relayer:latest .
docker push ghcr.io/nforceroh/relayer:latest
```

### 3. Kubernetes manifests

Copy `k8s/secret.yaml.example` to `k8s/secret.yaml`, fill in real values
(keep this file out of git), then:

```bash
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/networkpolicy.yaml
```

Before applying `networkpolicy.yaml`, adjust the `podSelector` values to
match your actual Dovecot pod labels and ingress controller namespace --
the example values are placeholders.

Put the web UI behind whatever TLS/ingress you already use for other
internal tools. Basic Auth is a baseline here, not a substitute for TLS.

### 4. Dovecot side (ConfigMap + Secret -- no image rebuild required)

Your existing Dovecot image already ships `dovecot-pigeonhole-plugin` and
`python3` -- nothing new to install in the image itself, and nothing in
this step touches the Dockerfile.

Since your Dovecot deployment already uses Kustomize (with
`disableNameSuffixHash: true`, so generated ConfigMap names stay literal
-- important, since `k8s/dovecot-deployment.yaml` references
`relayer-dovecot-sieve` by exact name), add it as a `configMapGenerator`
rather than hand-running `kubectl create configmap`:

1. Copy the three canonical files into your Dovecot kustomize directory,
   under a `relayer/` subfolder:
   ```bash
   mkdir -p <your-dovecot-kustomize-dir>/relayer
   cp dovecot-side/91-relayer-sieve.conf \
      dovecot-side/global-before.sieve \
      dovecot-side/relayer-forward.sh \
      <your-dovecot-kustomize-dir>/relayer/
   ```

2. Add the generator to your `kustomization.yaml` (see
   `k8s/dovecot-kustomization.yaml` for the full merged file -- only the
   `relayer-dovecot-sieve` entry under `configMapGenerator` is new,
   everything else is your existing config untouched):
   ```yaml
   configMapGenerator:
     - name: dovecot-env
       envs:
         - maps/env.txt
     - name: relayer-dovecot-sieve
       files:
         - relayer/91-relayer-sieve.conf
         - relayer/global-before.sieve
         - relayer/relayer-forward.sh
   ```

3. Replace your `deployment.yaml` with `k8s/dovecot-deployment.yaml` (or
   merge the marked `relayer-*` volumes/volumeMounts in by hand) -- it
   adds two volumes (the generated ConfigMap above, and the
   `INGEST_TOKEN` key from the same `relayer-secrets` Secret Relayer
   itself uses, so the token only has to be set in one place) and mounts
   them via `subPath` into `/etc/dovecot/conf.d/` and
   `/configfiles/sieve/`.

Your existing sieve-init script (the one that copies `/configfiles/sieve`
into `/data/sieve`, runs `sievec` on every `.sieve` file, `chmod +x`'s
every `.sh` file, and `chown`'s the result to `vmail:mail`) picks up
`global-before.sieve` and `relayer-forward.sh` automatically -- no
changes needed to that script. This is also why the pipe script is `.sh`
rather than `.py`: your init script's chmod loop only matches `*.sh`, and
this piggybacks on it rather than asking you to extend it.

`subPath` is required for the `conf.d/` and `configfiles/sieve/` mounts
specifically because those directories already contain other files baked
into your image -- a normal (non-subPath) volume mount replaces a
directory's entire contents, which would hide everything else already
there.

Note: since `relayer-secrets` lives in the `mail` namespace (matching
your `namespace: mail` kustomize setting) and Relayer's own manifests
also target `mail`, the cross-reference just works -- no namespace
mismatch to worry about here.

Build and apply:

```bash
kubectl kustomize <your-dovecot-kustomize-dir> | kubectl apply -f -
kubectl rollout restart deployment/dovecot -n mail
```

Note: ConfigMap-backed volumes mounted via `subPath` don't live-update
when the ConfigMap changes (a known Kubernetes limitation) -- after
editing anything under `relayer/`, re-run `kubectl apply` and
`rollout restart` Dovecot again to pick it up. Given Sieve here is meant
to stay dumb and unconditional, this should rarely need to change.

### 5. Convert forwarding addresses from Alias to Mailbox

Sieve only runs on real local delivery. Each address you want Relayer to
manage (`toyota@martintwingles.com`, `aidvantage@martintwingles.com`,
etc.) needs to be a real ViMbAdmin **Mailbox**, not an Alias:

1. Create the Mailbox (a password is required by the form but never
   actually used, since nothing logs into it).
2. Delete the old Alias entry for the same address.
3. Add its recipients through Relayer's web UI (or `schema.sql`'s seed
   section as a starting point).

## Configuration reference

The image ships with generic placeholder defaults (see the `ENV` block in
`Dockerfile`) so it never carries any of your actual infrastructure
details. **Every real value is set in `k8s/deployment.yaml` and
`k8s/secret.yaml`** -- that's the single source of truth for this
deployment's configuration, matching how your Dovecot/ViMbAdmin images
are configured.

| Env var | Used by | Purpose | Image default (generic) |
|---|---|---|---|
| `DB_HOST` | Relayer | MySQL host (matches Dovecot's existing var name) | `mariadb` |
| `DB_PORT` | Relayer | MySQL port | `3306` |
| `DB_DATABASE` | Relayer | Database name | `mail` |
| `DB_USER` | Relayer | Dedicated Relayer MySQL user (**not** `mailro`) | `relayer` |
| `DB_PASSWORD` | Relayer | Password for `DB_USER` | *(none -- must be set via Secret)* |
| `POSTFIX_HOST` | Relayer | Where to send outbound forwards | `postfix` |
| `POSTFIX_PORT` | Relayer | SMTP port on that host | `25` |
| `ADMIN_USER` | Relayer | Web UI Basic Auth username | `admin` |
| `ADMIN_PASS` | Relayer | Web UI Basic Auth password | *(none -- must be set via Secret)* |
| `LOG_LEVEL` | Relayer | Set to `DEBUG` to log `/ingest` auth-check details (header lengths/tails, never the full token) and the raw SMTP conversation | `INFO` |
| `INGEST_TOKEN` | Relayer + Dovecot script | Shared bearer token authorizing `/ingest` calls | *(none -- must be set via Secret)* |
| `SECRET_KEY` | Relayer | Flask session/flash-message signing key | *(none -- must be set via Secret)* |

If `ADMIN_PASS` or `INGEST_TOKEN` are unset, Relayer refuses those routes
with `503` rather than falling back to an insecure default -- check pod
logs if either returns `503` unexpectedly.

## Day-to-day use

Add, disable, or remove recipients through the web UI at whatever
address you've exposed it (`http://localhost:8080` locally, your ingress
hostname in production). Changes take effect immediately -- no restart,
no redeploy, nothing to reload on the Dovecot side.

## Notes on failure behavior

Every layer here fails *open* toward normal mail delivery, never toward
blocking it:

- If Relayer is unreachable, slow, or erroring, the Dovecot-side script
  swallows the failure and exits `0` within its 5-second timeout -- the
  real mailbox delivery already happened independently and is never
  delayed or blocked.
- If `/ingest` can't determine the mailbox, finds no recipients, or a
  send to one particular recipient fails, it logs and moves on -- a
  failure for one recipient doesn't stop the others.
- None of this is surfaced to the original sender; forwarding failures
  are visible only in Relayer's own logs (`kubectl logs` on its pod, or
  compose logs locally).
