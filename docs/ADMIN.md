# Admin UI

The admin UI is a server-rendered Flask + Jinja interface (skinned with
[Basecoat](https://basecoatui.com/)) for reviewing voicemail, editing the IVR
prompts, and checking the Twilio connection. It lives under `/admin`.

## Access and login

- Visit `/admin/login`.
- Credentials come from environment variables, never the database:
  - `ADMIN_USERNAME` (default `admin`)
  - `ADMIN_PASSWORD` or, preferred, `ADMIN_PASSWORD_HASH` (a werkzeug hash). When
    the hash is set it takes precedence.
- Sessions are cookie-based. When `BASE_URL` is `https://…` the session cookie is
  marked `Secure`; it is always `HttpOnly` and `SameSite=Lax`, and expires after
  24 hours.

Generate a password hash:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
```

## Pages

| Page | Path | What it does |
|------|------|--------------|
| Dashboard | `/admin/` | Message count and last connection-test result |
| Messages | `/admin/messages` | Paginated inbox with optional caller-ID filter |
| Message detail | `/admin/messages/<id>` | Metadata, audio player, delete |
| Settings | `/admin/settings` | Edit IVR/voicemail prompts and max recording length |
| Connection | `/admin/connection` | Run Twilio ↔ NAS diagnostics; copy webhook URLs |

## Settings

Editable prompts (spoken by the IVR) and the recording length limit:

| Setting | Notes |
|---------|-------|
| Main menu greeting | ≤ 500 chars |
| Invalid input message | ≤ 500 chars |
| Voicemail prompt | ≤ 500 chars |
| Thank-you message | ≤ 500 chars |
| Max recording length | 10–600 seconds |

Twilio credentials, `BASE_URL`, and `DATA_DIR` are configuration, not settings —
they stay in the environment and are not editable from the UI.

## Connection diagnostics

The Connection page verifies the full path from Twilio to the app without placing
a call. Each check reports pass / warn / fail:

- Configuration present and `BASE_URL` well-formed (https, no trailing slash)
- Twilio API reachable with the configured credentials
- Configured phone number belongs to the account
- Public health URL reachable (a warn is expected when testing from your own LAN
  because of hairpin NAT — verify from cellular/off-network)
- Webhook signature validation round-trips for `BASE_URL/call`

It also shows copy-ready webhook URLs and a reminder to place a live test call.
The test endpoint is rate-limited and never displays secrets (the account SID is
masked).

## Security model

- Every `/admin/*` route except the login page requires an authenticated session.
- All mutating actions (login, logout, settings save, delete, run diagnostics) are
  POST with CSRF tokens (Flask-WTF).
- Login is rate-limited (5/min per IP); the connection test is rate-limited
  (3/min). Failed logins return a generic error and are logged at WARNING.
- Audio is streamed only via the authenticated route, resolving the file path from
  the database and confining it to the recordings directory (no traversal, no
  directory listing).
- All input (form fields, path/query params, Twilio webhook bodies) is validated
  and sanitized server-side; output is escaped by Jinja autoescaping and Twilio's
  XML serialization.
