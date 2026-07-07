# Family Call Center (Public)
> **Note:** This repository is unmaintained, unsupported, and shared as-is as untested example code.
This is a voicemail-focused Flask + Twilio app with a session-authenticated admin UI.
When a caller reaches `/call`, they hear one option:
- Press **1** to leave a voicemail.

The app records voicemail audio, stores it under `data/recordings/YYYY/MM/DD/`, logs metadata in `data/ivr.db`, and then deletes the recording from Twilio.

It ships with a Docker image for self-hosting (built for a Ugreen NAS behind
Nginx Proxy Manager), 1Password-based secret management, an admin UI for managing
messages and IVR prompts, and an automated test suite.

## Features
- **Voicemail IVR** over Twilio with signature-verified webhooks.
- **SMS notifications** — when a voicemail is saved, an optional text alert with a
  link to the message is sent to one or more recipients. Numbers are managed from
  the admin UI (no redeploy), and delivery can be tested from the Connection page.
- **Admin UI** (`/admin`) — session login, message inbox with audio playback and
  delete, editable IVR/voicemail prompts, and Twilio ↔ NAS connection diagnostics.
- **Voicemail transcription** using Twilio's built-in speech-to-text (single
  vendor, billed to your Twilio account). Transcripts are searchable and shown in
  the inbox and on the message detail page. Toggle it on from the Settings page.
- **Read / unread tracking** — unread messages are bolded and badged, the
  dashboard and Messages nav show an unread count, and there is a "mark all read"
  action.
- **Contacts address book** — map phone numbers to friendly names ("Mom",
  "Dr. Smith's office") shown wherever a caller ID appears, editable in the admin
  UI with optional CSV import.
- **Configurable prompts** stored in SQLite and editable from the UI (no code
  change or redeploy needed to change greetings or the max recording length).
- **Security controls** — CSRF protection, login rate limiting, hardened session
  cookies, path-safe audio streaming, and server-side input validation/sanitization.
- **Containerized deployment** — multi-stage Docker build, gunicorn, health check,
  `docker-compose` on an external NPM network, and publish/deploy scripts.
- **Secret management** via the 1Password CLI (`op inject` / `op run`).
- **Tests** — a pytest suite covering IVR, auth, CSRF, rate limiting, validation,
  output encoding, messages, transcription, read/unread, contacts, settings, and
  connection diagnostics.

## Why this repo exists
This repo is a lightweight public wrapper around my personal project so people can see the rough implementation.
I’ll add a link to the full write-up here once it’s published.

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
| `HOST` / `PORT` | no | Local dev bind for `run.py` (Docker uses gunicorn on `0.0.0.0:8080`) |

\* Provide either `ADMIN_PASSWORD` or `ADMIN_PASSWORD_HASH` (hash preferred in
production).

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

To enable SMS notifications for new voicemails, follow the Twilio Console steps in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) (SMS capability, trial verification, and
US A2P 10DLC), then add recipient numbers on the admin Settings page.

## Endpoints
- `POST /call` — main menu (Press 1 for voicemail)
- `POST /call/route` — routes keypad selection
- `POST /voicemail` — starts recording
- `POST /voicemail/done` — thanks caller and hangs up
- `POST /voicemail/callback` — receives recording callback and saves audio
- `POST /voicemail/transcribe` — receives Twilio transcription (when enabled)
- `GET /health` — basic health check
- `GET /privacy-policy` — public privacy policy
- `GET /terms-and-conditions` — public terms and conditions
- `/admin/*` — admin UI (session auth; see [docs/ADMIN.md](docs/ADMIN.md))

## Project structure
```
app/
  __init__.py            # app factory: blueprints, CSRF, rate limiter, sessions
  extensions.py          # shared CSRF + limiter instances
  routes/                # ivr.py, voicemail.py (Twilio), admin.py (admin UI)
  forms/admin_forms.py   # WTForms (login, settings, delete, contacts, etc.)
  utils/                 # auth, db, settings, validation, twiml, connection_test,
                         #   phone, contacts, transcription-aware voicemail flow
  templates/admin/       # Basecoat-skinned admin pages
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