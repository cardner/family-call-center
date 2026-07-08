# Testing

Automated tests use **pytest**. Manual checklists below cover each phase of
functionality and the UI.

## Running automated tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
./scripts/test.sh            # or: pytest -v
```

The suite is self-contained: it sets test environment variables and uses a
temporary data directory (no real Twilio calls, no network). One test checks that
the vendored Basecoat CSS is served; it is **skipped** unless the assets have been
vendored (`bash scripts/vendor-basecoat.sh`).

Optional coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

## Automated test map

| Area | File |
|------|------|
| Health | `tests/test_health.py` |
| Twilio signature auth | `tests/test_twilio_auth.py` |
| IVR menu/routing | `tests/test_ivr.py` |
| Call policy (blocklist + VIP) | `tests/test_call_policy.py` |
| Personalized greetings | `tests/test_greeting.py` |
| Voicemail callback | `tests/test_voicemail_callback.py` |
| Voicemail transcription (Twilio callbacks) | `tests/test_transcription.py` |
| Schema migrations | `tests/test_db_migrations.py` |
| Read / unread | `tests/test_read_unread.py` |
| Contacts + phone normalization | `tests/test_contacts.py` |
| Blocklist admin + CallShield import | `tests/test_admin_blocked.py`, `tests/test_blocklist_import.py` |
| Admin auth | `tests/test_admin_auth.py` |
| CSRF | `tests/test_admin_csrf.py` |
| Login rate limiting | `tests/test_admin_rate_limit.py` |
| Admin route security | `tests/test_admin_security.py` |
| Input validation/sanitization | `tests/test_input_validation.py` |
| Output encoding (XSS) | `tests/test_xss_output.py` |
| Admin messages CRUD | `tests/test_admin_messages.py` |
| Settings + IVR integration | `tests/test_settings.py`, `tests/test_voicemail_settings.py` |
| SSML sanitization | `tests/test_ssml.py` |
| IVR voice selection | `tests/test_voices.py` |
| Date/time display helpers | `tests/test_display.py` |
| Connection diagnostics | `tests/test_connection_diagnostics.py` |
| SMS notifications (unit) | `tests/test_notify.py` |
| SMS notifications (admin UI) | `tests/test_admin_notifications.py` |
| Legal pages | `tests/test_legal.py` |
| Static assets | `tests/test_static_basecoat.py` |

## Manual checkpoints by phase

Complete each phase's checks before moving on.

### Phase 1 — Infrastructure

- [ ] `pytest` passes
- [ ] `docker compose -f docker-compose.yml -f docker-compose.build.yml build` succeeds
- [ ] Container `GET http://localhost:8080/health` returns `{"status":"ok"}`
- [ ] `docker ps` shows the container `healthy`
- [ ] `data/` persists across `docker compose down` / `up`
- [ ] `op inject` produces a valid `.env` with all keys
- [ ] `publish.sh` builds/pushes an amd64 image (or dry-run build locally)

### Phase 2 — Admin auth + security

- [ ] Browsing `/admin/` while logged out redirects to login
- [ ] Wrong password shows a generic error (no stack trace)
- [ ] Correct password loads the dashboard
- [ ] Session cookie is `HttpOnly` (and `Secure` over HTTPS)
- [ ] Logout clears the session
- [ ] Login POST without a CSRF token (curl) is rejected
- [ ] `next=https://evil.com` does not redirect off-site after login
- [ ] `<script>alert(1)</script>` in a setting is stored safely; page source shows
      escaped text; TwiML has no raw HTML

### Phase 3 — Messages

- [ ] A received/seeded recording appears in `/admin/messages`
- [ ] The audio player streams the recording
- [ ] Delete (with confirmation) removes the row and the file
- [ ] `/admin/messages/999/audio` without login is blocked

### Phase 4 — Settings + IVR

- [ ] Changing the greeting is heard on a test call (or in `/call` TwiML)
- [ ] Changing max recording length is reflected in `/voicemail` TwiML
- [ ] Over-limit settings submitted via curl are rejected server-side
- [ ] Settings survive a container restart

### Phase 4a — SMS notifications

- [ ] Adding recipients on the Settings page saves; an invalid number is rejected
- [ ] Connection page shows ON with the correct masked recipient count
- [ ] "Send test SMS" delivers a message to each configured number
- [ ] Leaving a voicemail texts each recipient a link to `/admin/messages/<id>`
- [ ] With no recipients configured, voicemail still saves and the callback returns 204

### Phase 4b — Voicemail transcription

- [ ] With transcription off (default), `/voicemail` TwiML has no `transcribe` attribute
- [ ] Enabling transcription on Settings adds `transcribe="true"` and caps `maxLength` at 120
- [ ] Leaving a voicemail (>2s) produces a transcript on the message a few seconds later
- [ ] The transcript is searchable from the Messages search box
- [ ] Twilio Console → Monitor → Logs shows no `13257` transcribeCallback errors
- [ ] With transcription off, the recording is still deleted from Twilio immediately

### Phase 4c — Read / unread

- [ ] A new voicemail shows as unread (bold + "New" badge) with an unread count
- [ ] Opening a message clears its unread state
- [ ] "Mark all read" clears all badges; "Unread only" filters the list
- [ ] The dashboard and Messages nav show the correct unread count

### Phase 4d — Contacts

- [ ] Adding a contact makes its name appear wherever that caller ID is shown
- [ ] A bare 10-digit number is stored as +1 E.164; junk input is rejected
- [ ] CSV import adds/updates contacts and reports skipped invalid rows
- [ ] Deleting a contact reverts the caller ID back to the raw number
- [ ] VIP contact ("Skip menu") goes straight to voicemail on a test call

### Phase 4e — Personalized greetings

- [ ] Enabling personalized greetings on Settings saves correctly
- [ ] Known contact hears their name in the main menu greeting (auto-prefix or `{name}` token)
- [ ] Known contact hears their name in the voicemail prompt
- [ ] VIP contact hears personalized voicemail prompt without hearing the main menu
- [ ] Unknown caller hears the normal greeting with no awkward "Hi ." phrasing
- [ ] With the toggle off, greetings are unchanged even if `{name}` is in the text

### Phase 4f — Blocklist

- [ ] Adding a blocked number stops that caller from reaching the menu
- [ ] "Reject" setting gives a busy signal; "Play a message" speaks the prompt and hangs up
- [ ] Blocking a caller from a message detail page adds them to the blocklist
- [ ] VIP contact who is also blocked is still allowed through to voicemail
- [ ] Starter blocklist import adds numbers; bulk-remove only deletes imported entries

### Phase 5 — Basecoat UI

Check each page at desktop and mobile widths:

- [ ] Login: styled card/button; error alert styled
- [ ] Dashboard: nav visible; cards readable
- [ ] Messages: table and buttons styled; pagination works; unread rows bold
- [ ] Message detail: transcript, audio player, delete, and block action work
- [ ] Contacts: list, add/edit/delete, CSV import, and VIP toggle styled and working
- [ ] Blocklist: list, add/edit/delete, starter import styled and working
- [ ] Settings: inputs aligned; save shows a flash; HTML5 limits enforced
- [ ] Connection: run tests works; badges readable; URLs copy; no secrets shown
- [ ] Mobile (≤720px): hamburger menu toggles navigation; header stays sticky
- [ ] No 404s for static assets; no unescaped user content in page source
- [ ] Keyboard: tab order and visible focus on forms

### Phase 6 — End-to-end

- [ ] Full `pytest` suite green
- [ ] Connection page: Twilio API check passes with real creds
- [ ] Public health check passes from an external network
- [ ] Webhook URLs match the Twilio console configuration
- [ ] `GET /privacy-policy` and `GET /terms-and-conditions` return HTML
- [ ] Live call → record → admin play → delete on the production hostname

## Future CI (out of scope for v1)

A GitHub Actions workflow could run `pytest` on push plus an optional
`docker build` smoke test. For v1, local pytest plus these manual checklists are
the gate.
