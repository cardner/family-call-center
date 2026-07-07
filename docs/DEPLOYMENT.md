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
holding the Twilio credentials, a Flask secret key, and the admin password. Then
edit [`.env.op.template`](../.env.op.template) so each `op://` reference points at
your actual vault, item, and field names.

Generate a strong Flask secret key and an admin password hash:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                        # FLASK_SECRET_KEY
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-admin-password'))"  # ADMIN_PASSWORD_HASH
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
`/call`.

## 6a. Configure SMS notifications (Twilio Console)

SMS alerts are optional. When a voicemail is saved, the app texts a link to the
message to each recipient you configure. Alerts are **outbound only** — no new
Twilio webhook URLs are required, and the existing Twilio credentials are reused
as the sender. Recipient numbers are set in the admin UI, not in `.env`.

1. **Confirm the number can send SMS.** In the [Twilio Console](https://console.twilio.com),
   go to **Phone Numbers → Manage → Active numbers**, open the number that matches
   `TWILIO_PHONE_NUMBER`, and check that both **Voice** and **SMS** capabilities are
   enabled. Recipients will see texts coming from this number.
2. **Trial accounts: verify each recipient.** On a trial account Twilio only
   delivers SMS to [verified caller IDs](https://www.twilio.com/docs/messaging/guides/how-to-use-your-free-trial-account).
   Add every family member's number under **Phone Numbers → Manage → Verified
   Caller IDs** and complete verification on each device. Skip this once the
   account is upgraded to paid.
3. **Enable geographic permissions.** Under **Messaging → Settings → Geo
   permissions**, enable SMS for the countries where recipients live (e.g. United
   States). Twilio rejects sends to disabled regions.
4. **US numbers: register A2P 10DLC.** For US local numbers texting US mobiles,
   complete [A2P 10DLC registration](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc):
   register a Brand, register a Campaign (transactional notifications), and link
   your phone number. Approval can take 1–15 business days; unregistered traffic is
   often filtered. Toll-free numbers use **Toll-Free Verification** instead.
5. **Add recipients in the admin UI.** Log in at
   `https://voicemail.yourdomain.com/admin/settings`, enter numbers in the **SMS
   notification recipients** field (E.164 format, one per line or comma-separated),
   and save. No container restart is needed.
6. **Test delivery.** Open the Connection page and click **Send test SMS**; each
   recipient should receive a message within seconds.

You do **not** need a Messaging Service, an inbound SMS webhook, a status callback
URL, or new API keys for this. Outbound SMS is billed per
[Twilio SMS pricing](https://www.twilio.com/en-us/pricing) segment, one message per
recipient per voicemail.

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
- Open the Connection page and run diagnostics (the SMS notifications check reports
  whether recipients are configured)
- Place a test call, then confirm the recording appears in the inbox — and, if SMS
  is configured, that each recipient receives an alert with a link to the message

## Hardening the admin surface (optional)

- Put the admin UI on its own subdomain (`admin.voicemail.yourdomain.com`) and add
  an NPM Access List restricting it to your home IP.
- Add NPM-layer rate limiting on `/admin/login` as defense in depth.
- Keep Force SSL + HSTS enabled on all proxy hosts.

## Data and updates

- Voicemail audio lives under `./data/recordings/YYYY/MM/DD/`; metadata and
  settings in `./data/ivr.db`. Both persist across container restarts and image
  updates because they are on the `./data` volume.
- To update: publish a new tag, update `IMAGE`, then re-run `./scripts/deploy.sh`.
- `chmod 600 .env` and never commit it.
