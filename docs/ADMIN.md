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
| Dashboard | `/admin/` | Message count, unread count, and last connection-test result |
| Messages | `/admin/messages` | Paginated inbox with search, transcript previews, and read/unread |
| Message detail | `/admin/messages/<id>` | Metadata, transcript, audio player, delete |
| Contacts | `/admin/contacts` | Manage the phone → name address book; CSV import |
| Settings | `/admin/settings` | Edit IVR/voicemail prompts, max recording length, transcription toggle |
| Connection | `/admin/connection` | Run Twilio ↔ NAS diagnostics; copy webhook URLs |

## Messages inbox

- **Search** matches the caller ID, the transcript text, and a linked contact's
  name, so you can find a message by content ("doctor", "pickup") or by who called.
- **Read / unread**: new messages are bold with a "New" badge; opening a message
  marks it read. The Messages nav item and the dashboard show the unread count,
  and "Mark all read" clears the badges. Use the "Unread only" filter to focus on
  new messages.
- **Transcript preview**: when transcription is on, each row shows a short preview
  of the transcript (or "Transcribing…" until Twilio's callback arrives).

## Contacts

The contacts address book maps phone numbers to friendly display names. Names
appear everywhere a caller ID is shown (inbox, dashboard, message detail).

- Add or edit contacts individually. Phone numbers are normalized to E.164 on
  save; a bare 10-digit number is treated as US (+1).
- **CSV import**: upload a file with `phone,display_name` columns (an optional
  header row is allowed). Existing numbers are updated; invalid rows are skipped
  and reported.

## Settings

Editable prompts (spoken by the IVR with neural TTS and optional SSML), voice
selection, and the recording length limit:

| Setting | Notes |
|---------|-------|
| IVR voice | Google Neural2 English voices (via Twilio), grouped by region (US/UK) and gender (male/female) |
| Main menu greeting | ≤ 500 chars; SSML tags for pauses/emphasis supported |
| Invalid input message | ≤ 500 chars; SSML tags supported |
| Voicemail prompt | ≤ 500 chars; SSML tags supported |
| Thank-you message | ≤ 500 chars; SSML tags supported |
| Max recording length | 10–600 seconds |
| Enable voicemail transcription | Off by default; see below |

The **IVR voice** dropdown lists the US and UK English Google Neural2 voices
Twilio supports, grouped by region and gender. The selected voice is used for
all spoken IVR prompts on live calls.

Each prompt field has a **Preview** button that plays the current text in your
browser using the Web Speech API. Preview is approximate: it matches the
selected voice's language and gender to a local browser voice and interprets the
SSML pauses/emphasis, so it is good for checking wording and pacing. It does not
use the exact Twilio Neural2 voice — call your IVR number after saving to hear
the exact result. No API key or extra configuration is required.

### Voicemail transcription

Turning on **Enable voicemail transcription** makes the app request Twilio's
built-in speech-to-text on each new voicemail. Transcripts appear in the inbox
preview and on the message detail page, and become searchable.

- Transcription is billed to your Twilio account (there is no separate provider
  or API key). See [docs/DEPLOYMENT.md](DEPLOYMENT.md) for the Twilio Console
  steps and cost notes.
- Twilio only transcribes recordings shorter than **120 seconds**, so while
  transcription is enabled the effective max recording length is capped at 120s
  regardless of the "Max recording length" setting.
- Transcription is asynchronous: Twilio posts the text to
  `/voicemail/transcribe` a few seconds after the recording is saved, so a new
  message may briefly show "Transcribing…".
| SMS notification recipients | Optional. E.164 numbers (one per line or comma-separated) that receive a text when a voicemail is saved. Leave blank to disable. Invalid numbers are rejected on save. |

Allowed SSML tags: `<break time="300ms"/>`, `<emphasis level="moderate">…</emphasis>`, `<prosody rate="slow">…</prosody>`. Unknown tags are stripped on save.

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

## SMS notifications

When a voicemail is saved, the app can text an alert with a link to the message to
one or more recipients. Recipient numbers are managed as a setting on the Settings
page (see above), so they can be changed without a redeploy. The Connection page
shows whether notifications are on or off, the number of recipients (masked to the
last four digits), and a rate-limited **Send test SMS** button to confirm delivery.
The dashboard shows an on/off badge with a shortcut to configure or test. Twilio
account setup for SMS is covered in [DEPLOYMENT.md](DEPLOYMENT.md).

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
