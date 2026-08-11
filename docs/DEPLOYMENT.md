# Deployment guide (Ugreen DXP2800 + NPM + 1Password)

This guide covers running the Family Call Center app 24/7 in Docker on a Ugreen
NASync DXP2800, exposed through an existing Nginx Proxy Manager (NPM) instance,
with secrets managed by the 1Password CLI.

## Overview

```
Twilio / Admin browser  ──HTTPS──▶  Nginx Proxy Manager  ──HTTP──▶  family-call-center:8080
                                        (public 443)                 (shared Docker network)
```

The container publishes no host ports. NPM reaches it by container name on a
shared Docker network. Twilio webhooks and the admin UI share one hostname
(optionally split the admin UI onto its own subdomain — see below).

### External services

| Service | Required | Purpose |
|---------|----------|---------|
| Twilio Voice | yes | Incoming calls, IVR, voicemail recording, neural TTS |
| Fastmail SMTP | optional | Voicemail alert emails to configured recipients |
| Twilio Transcription | optional | Speech-to-text on recordings (Settings toggle) |
| Nginx Proxy Manager | yes (this guide) | HTTPS reverse proxy |
| 1Password CLI | optional | Secret injection on the NAS (`op inject` / `op run`) |
| CallShield | optional | Starter blocklist import from the admin UI (no API key) |

The app stores all data locally (SQLite + filesystem). No cloud database or
third-party AI API is required beyond Twilio.

## Target hardware

| Spec | Implication |
|------|-------------|
| Intel N100 (x86_64) | Build images for `linux/amd64` |
| 8 GB DDR5 | gunicorn (2 workers) + SQLite is comfortable |
| UGOS Pro Docker app | Deploy via Project/Stack or SSH `docker compose` |
| Volume storage | Mount `./data:/data` under `/volume1/docker/family-call-center/` |

## 1. Build and publish the image (dev machine)

The DXP2800 pulls a prebuilt image from a registry (Docker Hub or GHCR). Build on
your Mac and push. On Apple Silicon this must target `linux/amd64`.

```bash
docker login                                   # or: docker login ghcr.io
REGISTRY=ghcr.io/youruser/family-call-center TAG=v1.0.0 ./scripts/publish.sh
```

`publish.sh` uses `docker buildx --platform linux/amd64` and pushes the tag. Note
the resulting reference (for example `ghcr.io/youruser/family-call-center:v1.0.0`).

## 2. Prepare secrets in 1Password

Create items in a vault (the template assumes a vault named `Family-Call-Center`)
holding the Twilio credentials, a Flask secret key, the admin password, and (for
email notifications) a settings encryption key. Then edit
[`.env.op.template`](../.env.op.template) so each `op://` reference points at your
actual vault, item, and field names.

Generate a strong Flask secret key, an admin password hash, and a settings
encryption key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                        # FLASK_SECRET_KEY
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-admin-password'))"  # ADMIN_PASSWORD_HASH
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # SETTINGS_ENCRYPTION_KEY
```

Prefer storing `ADMIN_PASSWORD_HASH` over a plaintext `ADMIN_PASSWORD` in
production; when present the hash takes precedence.

## 3. Copy deploy files to the NAS

On the NAS, create `/volume1/docker/family-call-center/` and copy:

- `docker-compose.yml`
- `.env.op.template`
- `scripts/deploy.sh`

Set the image reference and NPM network. These can go in the shell environment or
directly in `.env` after injection:

- `IMAGE=ghcr.io/youruser/family-call-center:v1.0.0`
- `NPM_NETWORK=<your NPM network>` (find it with `docker network ls`, often
  `npm_default` or `nginx-proxy-manager_default`)

## 4. Materialize `.env` and start

With the 1Password CLI signed in on the NAS:

```bash
./scripts/deploy.sh
```

This runs `op inject -i .env.op.template -o .env`, `chmod 600 .env`, then
`docker compose pull && docker compose up -d`. If you prefer not to write secrets
to disk:

```bash
op run --env-file=.env.op.template -- docker compose up -d
```

To build on the NAS instead of pulling a registry image:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

## 5. Connect the container to NPM

The compose file joins an external network named by `NPM_NETWORK`. Confirm both
NPM and this container are on it:

```bash
docker network inspect "$NPM_NETWORK" | grep -A3 Containers
```

In NPM, add a Proxy Host:

- Domain: `voicemail.yourdomain.com`
- Forward hostname: `family-call-center`
- Forward port: `8080`
- Scheme: `http`
- Enable Block Common Exploits, Websockets as needed
- SSL tab: request a Let's Encrypt cert, Force SSL, and enable HTTP/2 + HSTS

## 6. Point Twilio at the app

In the Twilio Console, set the phone number's Voice webhook:

- A call comes in: `https://voicemail.yourdomain.com/call`
- Method: `POST`

The other endpoints (`/voicemail`, `/voicemail/done`, `/voicemail/callback`,
`/voicemail/transcribe`) are driven by TwiML the app returns; you only configure
`/call`. The single menu routes callers to per-recipient voicemail boxes
(Family, Cody, Ryan, Cory) by keypad digit — no extra Twilio numbers or webhooks
are needed.

## 6a. Configure email notifications (Fastmail SMTP)

Email alerts are optional. When a voicemail is saved, the app emails a link to
the message to each configured recipient through Fastmail SMTP. Alerts are
**outbound only** — no inbound mail, webhooks, or Twilio SMS is involved.
Recipients are derived from Contacts (admins get Family messages; each personal
box notifies its linked contact), and the SMTP credentials are entered in the
admin UI, not in `.env`.

1. **Set the encryption key.** SMTP credentials are encrypted at rest with a
   Fernet key that lives only in the environment. Generate one:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Set it as `SETTINGS_ENCRYPTION_KEY` in `.env` (or store it in 1Password and
   reference it from `.env.op.template`). Restart the container so the app picks
   it up. Without this key the Settings page cannot save SMTP details and email
   stays disabled.
2. **Create a Fastmail app password.** In Fastmail, go to **Settings → Privacy &
   Security → App passwords** and create a new
   [app password](https://www.fastmail.help/hc/en-us/articles/360058752854-App-passwords)
   scoped to **Mail (SMTP)** only. Copy the generated password — you cannot view
   it again later.
3. **Enter SMTP settings in the admin UI.** Log in at
   `https://voicemail.yourdomain.com/admin/settings` and fill in the **Email
   notifications** section:
   - **SMTP host:** `smtp.fastmail.com`
   - **Security:** SSL (port 465) — or STARTTLS (port 587)
   - **SMTP username:** your full Fastmail address (e.g. `you@yourdomain.com`)
   - **SMTP password:** the app password from step 2
   - **From address:** optional; leave blank to send from the username

   Save. No container restart is needed; the credentials are encrypted before
   they are written to the database.
4. **Choose recipients on the Contacts page.** Open `/admin/contacts` and give
   each recipient an **email address**. Mark family members who should receive
   shared **Family** mailbox alerts as **admins**, and link a contact to a
   personal box (Cody, Ryan, Cory) to route that box's alerts to them.
5. **Test delivery.** Open the Connection page and click **Send test email**;
   each configured recipient should receive a message within seconds.

Fastmail is a personal mailbox provider, not a bulk sender — family-scale volume
is fine, but its normal sending limits apply. Rotating `SETTINGS_ENCRYPTION_KEY`
invalidates the stored SMTP settings; re-enter them on the Settings page after a
key change.

## 6b. Enable voicemail transcription (Twilio Console)

Transcription is optional and off by default. When on, the app asks Twilio to
transcribe each voicemail and posts the text back to `/voicemail/transcribe`,
where it is stored and shown in the inbox. Speech-to-text is billed to your
existing Twilio account — there is no separate provider or API key.

1. **Confirm billing is active.** In the [Twilio Console](https://console.twilio.com),
   go to **Billing → Overview**. Transcription is a paid add-on on top of voice
   minutes. Trial credit can be used, but once it runs out the account must accept
   paid usage. Expect a **Voice → Transcriptions** line item (about **$0.05/min**
   for the `<Record transcribe>` path on US accounts; verify on the
   [Voice pricing page](https://www.twilio.com/en-us/voice/pricing/us)).
2. **No separate Console toggle is required.** Transcription is turned on by the
   app's TwiML (the `transcribe` attribute on `<Record>`), which is controlled by
   the admin Settings switch — not by a Console setting. Do **not** create a V3
   "batch transcription" configuration under **Voice → Transcriptions**; that is a
   different architecture this app does not use.
3. **Deploy this version of the app** so the `/voicemail/transcribe` endpoint
   exists and is publicly reachable over HTTPS (same requirements as the other
   webhooks). It appears on the admin **Connection** page alongside the other
   webhook URLs.
4. **Enable it in the app** (not the Console): log in at
   `https://voicemail.yourdomain.com/admin/settings`, turn on **Enable voicemail
   transcription**, and save.
5. **Note the 120-second limit.** Twilio only transcribes recordings longer than
   2 seconds and shorter than 120 seconds. While transcription is on, the app
   caps the recording length at 120s automatically.
6. **Place a test call** (leave a message longer than 2 seconds). In
   **Monitor → Logs → Errors**, confirm there is no `13257` (invalid
   transcribeCallback URL) or signature error. The transcript should appear on the
   message a few seconds after the recording is saved.
7. **Monitor usage.** Review charges under **Billing → Usage** (the
   **Transcriptions** line item).

**Account restrictions:** `<Record transcribe>` is not available on **PCI Mode**
or **HIPAA** accounts. If either is enabled, transcription will not work; leave
the Settings toggle off.

## 7. Verify

- `curl https://voicemail.yourdomain.com/health` → `{"status":"ok",...}`
- Log in at `https://voicemail.yourdomain.com/admin/login`
- Open the Connection page and run diagnostics (the email notifications check reports
  whether SMTP and recipients are configured)
- Place a test call, then confirm the recording appears in the inbox — and, if email
  is configured, that each recipient receives an alert with a link to the message
- Optional: confirm `https://voicemail.yourdomain.com/privacy-policy` and
  `/terms-and-conditions` load (useful if Twilio or carriers ask for policy URLs)

## Hardening the admin surface (optional)

- Put the admin UI on its own subdomain (`admin.voicemail.yourdomain.com`) and add
  an NPM Access List restricting it to your home IP.
- Add NPM-layer rate limiting on `/admin/login` as defense in depth.
- Keep Force SSL + HSTS enabled on all proxy hosts.

## Data and updates

- Voicemail audio lives under `./data/recordings/YYYY/MM/DD/`; metadata (tagged
  with its voicemail box), contacts, blocklist, voicemail boxes, and settings in
  `./data/ivr.db`. Both persist across container restarts and image updates
  because they are on the `./data` volume.
- To update: publish a new tag, update `IMAGE`, then re-run `./scripts/deploy.sh`.
- `chmod 600 .env` and never commit it.
