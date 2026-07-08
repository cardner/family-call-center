# Family Call Center (Public)

> **Note:** This repository is unmaintained, unsupported, and shared as-is as untested example code.

A voicemail-focused Flask + Twilio app with a session-authenticated admin UI. When a
caller reaches `/call`, they hear a main menu and press a digit to choose whose
mailbox to leave a message in (Family, Cody, Ryan, or Cory). The app records audio,
stores it under `data/recordings/YYYY/MM/DD/` tagged with the chosen box, logs
metadata in `data/ivr.db`, and deletes the recording from Twilio after download.

It ships with a Docker image for self-hosting (built for a Ugreen NAS behind Nginx
Proxy Manager), 1Password-based secret management, an admin UI for managing
messages and IVR prompts, and an automated test suite.

## Features

### Call handling (Twilio IVR)

- **Voicemail IVR** — Twilio voice webhooks with request-signature verification.
- **Per-recipient voicemail boxes** — a single menu routes callers to one of four
  mailboxes (Family, Cody, Ryan, Cory) by keypad digit, each with its own optional
  prompt, thank-you message, and SMS recipients, and its own inbox filter.
- **Configurable prompts** — main menu greeting, invalid-input message, and default
  voicemail prompt/thank-you message stored in SQLite and editable from the admin UI
  (no redeploy needed). The menu's "press N" options are generated from your boxes.
- **Neural TTS + SSML** — Google Neural2 voices (via Twilio) with optional SSML
  tags for pauses, emphasis, and prosody.
- **Personalized greetings** — optional toggle looks up the caller in your contacts
  and speaks their name in the main menu greeting and voicemail prompt. Supports a
  `{name}` placeholder or automatic salutation prefixes (`Hi {name}` / `Thanks for
  calling {name}`).
- **VIP contacts** — per-contact flag that lets a caller bypass the blocklist (VIP
  always wins over the blocklist); VIPs still pick a mailbox from the menu.
- **Blocklist** — reject or play a message to blocked callers before they reach
  the menu or voicemail. Manage numbers manually, block from a message detail
  page, or import a starter list from the community [CallShield](https://github.com/SysAdminDoc/CallShield)
  database.

### Admin UI (`/admin`)

- Session login with idle and absolute session timeouts.
- **Dashboard** — message count, unread count, SMS notification status, last
  connection-test result.
- **Messages inbox** — paginated list with search (caller ID, transcript, contact
  name), per-box filtering, audio playback, delete, and read/unread tracking.
- **Voicemail boxes** — edit each mailbox's prompt, thank-you message, menu digit,
  and SMS recipients.
- **Contacts** — phone → display name address book with CSV import.
- **Blocklist** — manage blocked numbers and optional CallShield starter import.
- **Settings** — edit prompts, IVR voice, max recording length, transcription,
  personalized greetings, blocked-caller handling, and SMS recipients.
- **Connection diagnostics** — Twilio ↔ app health checks, webhook URL list,
  test SMS, and copy-ready configuration.
- **Responsive layout** — collapsible hamburger navigation on mobile.

### Notifications and transcription

- **SMS notifications** — optional text alert with a link to the message when a
  voicemail is saved. Recipients are managed from Settings (no redeploy).
- **Voicemail transcription** — Twilio built-in speech-to-text (billed to your
  Twilio account). Transcripts are searchable and shown in the inbox.

### Security and operations

- CSRF protection on all admin mutations.
- Login and connection-test rate limiting.
- Hardened session cookies (`HttpOnly`, `SameSite=Lax`, `Secure` over HTTPS).
- Path-safe audio streaming (no directory traversal).
- Server-side input validation and sanitization.
- Containerized deployment — multi-stage Docker build, gunicorn, health check,
  `docker-compose` on an external NPM network, publish/deploy scripts.
- Secret management via the 1Password CLI (`op inject` / `op run`).
- Public **privacy policy** and **terms and conditions** pages.

### Tests

A pytest suite covering IVR, voicemail, auth, CSRF, rate limiting, validation,
output encoding, messages, transcription, read/unread, contacts, blocklist,
personalized greetings, call policy, settings, connection diagnostics, SMS
notifications, legal pages, and SSML/voice handling.

## Integrations

| Integration | Role |
|-------------|------|
| [Twilio Voice](https://www.twilio.com/voice) | Incoming calls, IVR TwiML, voicemail recording, neural TTS |
| [Twilio SMS](https://www.twilio.com/messaging) | Outbound voicemail alerts to configured recipients |
| [Twilio Transcription](https://www.twilio.com/docs/voice/twiml/record#attributes-transcribe) | Optional speech-to-text on recordings (`<Record transcribe>`) |
| [Nginx Proxy Manager](https://nginxproxymanager.com/) | HTTPS termination and reverse proxy to the container |
| [1Password CLI](https://developer.1password.com/docs/cli/) | Secret injection for Docker deployments (`op inject` / `op run`) |
| [Basecoat](https://basecoatui.com/) | Admin UI component styling (vendored at build time) |
| [CallShield](https://github.com/SysAdminDoc/CallShield) | Optional starter blocklist import (MIT, FCC/FTC-sourced numbers) |

Twilio is the only runtime external API the app calls. Everything else is
self-hosted infrastructure or vendored assets.

## Dependencies

### Python (runtime)

| Package | Purpose |
|---------|---------|
| Flask 3.1 | Web framework |
| Twilio 9.x | REST client, request signature validation, TwiML |
| python-dotenv | Load `.env` at startup |
| requests | Download recordings from Twilio |
| gunicorn | Production WSGI server (Docker) |
| Flask-WTF | CSRF protection and form handling |
| Flask-Limiter | Login and diagnostics rate limiting |

See [`requirements.txt`](requirements.txt). Dev/test extras in
[`requirements-dev.txt`](requirements-dev.txt) (pytest, pytest-cov).

### Build / assets

| Tool | Purpose |
|------|---------|
| Node 20 + `basecoat-css` | Vendor Basecoat CSS/JS into `app/static/` (Docker stage 1; optional locally via `npm run vendor`) |
| Docker + buildx | Multi-stage `linux/amd64` image for NAS deployment |

### Data storage

- **SQLite** (`data/ivr.db`) — recordings metadata, contacts, blocklist, settings.
- **Filesystem** (`data/recordings/`) — voicemail audio files (WAV).

No Redis, Postgres, or other external database is required.

## Why this repo exists

This repo is a lightweight public wrapper around my personal project so people can
see the rough implementation. I'll add a link to the full write-up here once it's
published.

## Project status and disclaimers

- This project is shared as an **example/sketch**, not production-ready software.
- I am **not providing support** for this repository.
- The code is **lightly tested / untested in many environments**.
- Reuse or adapt it at your own risk.
- Treat this as a starting point for experimentation, not a maintained package.

## Local setup

1. Copy the environment template and fill in values (including `ADMIN_USERNAME`
   and `ADMIN_PASSWORD`):

```bash
cp .env.template .env
```

2. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. (Optional) Vendor the Basecoat CSS/JS so the admin UI is styled locally:

```bash
bash scripts/vendor-basecoat.sh
# or: npm install && npm run vendor
```

4. Run the app:

```bash
python run.py
```

## Environment variables

Configured via `.env` (see [`.env.template`](.env.template), or
[`.env.op.template`](.env.op.template) for 1Password references).

| Variable | Required | Description |
|----------|----------|-------------|
| `TWILIO_ACCOUNT_SID` | yes | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | yes | Twilio auth token (also used to verify webhook signatures) |
| `TWILIO_PHONE_NUMBER` | yes | The Twilio number, e.g. `+15550001111` |
| `BASE_URL` | yes | Public HTTPS URL Twilio/admin reach (no trailing slash) |
| `FLASK_SECRET_KEY` | yes | Session signing key |
| `ADMIN_USERNAME` | no (default `admin`) | Admin login username |
| `ADMIN_PASSWORD` | yes* | Admin password (plaintext) |
| `ADMIN_PASSWORD_HASH` | yes* | Werkzeug password hash; takes precedence over `ADMIN_PASSWORD` |
| `DATA_DIR` | no | Data directory (`/data` in Docker) |
| `SESSION_IDLE_TIMEOUT_MINUTES` | no (default `30`) | Log out inactive admin sessions |
| `SESSION_ABSOLUTE_MAX_HOURS` | no (default `8`) | Hard cap on session lifetime from login |
| `HOST` / `PORT` | no | Local dev bind for `run.py` (Docker uses gunicorn on `0.0.0.0:8080`) |

\* Provide either `ADMIN_PASSWORD` or `ADMIN_PASSWORD_HASH` (hash preferred in
production).

Docker-only variables (`IMAGE`, `NPM_NETWORK`) are documented in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Docker deployment (Ugreen NAS + NPM + 1Password)

The app is containerized for 24/7 operation behind an existing Nginx Proxy
Manager, with secrets managed by the 1Password CLI. Build on your dev machine,
push to a registry, and pull on the NAS:

```bash
REGISTRY=ghcr.io/youruser/family-call-center TAG=v1.0.0 ./scripts/publish.sh   # dev machine
./scripts/deploy.sh                                                            # on the NAS
```

Full instructions: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Testing

```bash
pip install -r requirements-dev.txt
./scripts/test.sh
```

Automated (pytest) and manual checklists: [docs/TESTING.md](docs/TESTING.md).

## Twilio webhook

In Twilio phone number settings:

- Voice webhook URL: `https://your-public-hostname.example.com/call`
- Method: `POST`

The app generates TwiML that chains the other endpoints (`/call/route`,
`/voicemail`, `/voicemail/done`, `/voicemail/callback`, `/voicemail/transcribe`).
You only configure `/call` in the Twilio Console.

To enable SMS notifications for new voicemails, follow the Twilio Console steps in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) (SMS capability, trial verification, and
US A2P 10DLC), then add recipient numbers on the admin Settings page.

## Endpoints

### Twilio webhooks (POST, signature-verified)

| Endpoint | Purpose |
|----------|---------|
| `/call` | Main menu — VIP blocklist bypass, blocklist check, personalized greeting |
| `/call/route` | Keypad routing (1–4 → the chosen voicemail box) |
| `/voicemail` | Voicemail prompt + start recording (per `?box=` slug) |
| `/voicemail/done` | Thank caller and hang up |
| `/voicemail/callback` | Save recording (tagged with its box) locally, notify via SMS |
| `/voicemail/transcribe` | Store transcript (when transcription enabled) |

### Public

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Health check (`{"status":"ok",...}`) |
| `GET /privacy-policy` | Privacy policy |
| `GET /terms-and-conditions` | Terms and conditions |

### Admin (`/admin/*`, session auth)

See [docs/ADMIN.md](docs/ADMIN.md) for the full page list and security model.

## Project structure

```
app/
  __init__.py            # app factory: blueprints, CSRF, rate limiter, sessions
  extensions.py          # shared CSRF + limiter instances
  routes/
    ivr.py               # /call, /call/route
    voicemail.py         # recording, callback, transcription
    admin.py             # admin UI
    legal.py             # privacy policy, terms
  forms/admin_forms.py   # WTForms (login, settings, contacts, blocklist, etc.)
  utils/
    auth.py              # session login/logout, timeouts
    db.py                # SQLite schema and CRUD
    settings.py          # editable IVR settings
    boxes.py             # per-recipient voicemail boxes
    greeting.py          # personalized greeting/voicemail prompt formatting
    call_policy.py       # blocklist + VIP logic
    contacts.py          # caller ID → display name resolution
    blocklist_import.py  # CallShield starter import
    twiml.py             # TwiML builders
    twilio_validator.py  # webhook signature decorator
    ssml.py / voices.py  # SSML sanitization and voice selection
    connection_test.py   # Twilio ↔ app diagnostics
    notify.py            # SMS alerts
    validation.py        # input sanitization
  templates/admin/       # Basecoat-skinned admin pages
  templates/legal/       # public legal pages
  static/                # admin JS + vendored Basecoat assets
config.py                # environment-driven configuration
run.py                   # entry point (gunicorn target: run:app)
Dockerfile               # multi-stage build (Basecoat vendoring + gunicorn)
docker-compose.yml       # registry image, external NPM network, data volume
scripts/                 # vendor-basecoat, publish, deploy, test
docs/                    # DEPLOYMENT.md, ADMIN.md, TESTING.md
tests/                   # pytest suite + fixtures
```

## Documentation

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Ugreen NAS, NPM, 1Password, Twilio setup
- [docs/ADMIN.md](docs/ADMIN.md) — admin UI usage and security model
- [docs/TESTING.md](docs/TESTING.md) — automated tests and manual checklists

## Optional macOS service files

Template files are included:

- `com.family.ivr.plist`
- `family-ivr.newsyslog.conf`

Replace placeholder paths before using them. For the Docker/NAS deployment these
are not used (gunicorn runs in the container).
