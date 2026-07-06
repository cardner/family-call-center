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
| Voicemail callback | `tests/test_voicemail_callback.py` |
| Admin auth | `tests/test_admin_auth.py` |
| CSRF | `tests/test_admin_csrf.py` |
| Login rate limiting | `tests/test_admin_rate_limit.py` |
| Admin route security | `tests/test_admin_security.py` |
| Input validation/sanitization | `tests/test_input_validation.py` |
| Output encoding (XSS) | `tests/test_xss_output.py` |
| Admin messages CRUD | `tests/test_admin_messages.py` |
| Settings + IVR integration | `tests/test_settings.py`, `tests/test_voicemail_settings.py` |
| Connection diagnostics | `tests/test_connection_diagnostics.py` |
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

### Phase 5 — Basecoat UI

Check each page at desktop and mobile widths:

- [ ] Login: styled card/button; error alert styled
- [ ] Dashboard: nav visible; cards readable
- [ ] Messages: table and buttons styled; pagination works
- [ ] Message detail: audio player and delete work
- [ ] Settings: inputs aligned; save shows a flash; HTML5 limits enforced
- [ ] Connection: run tests works; badges readable; URLs copy; no secrets shown
- [ ] No 404s for static assets; no unescaped user content in page source
- [ ] Keyboard: tab order and visible focus on forms

### Phase 6 — End-to-end

- [ ] Full `pytest` suite green
- [ ] Connection page: Twilio API check passes with real creds
- [ ] Public health check passes from an external network
- [ ] Webhook URLs match the Twilio console configuration
- [ ] Live call → record → admin play → delete on the production hostname

## Future CI (out of scope for v1)

A GitHub Actions workflow could run `pytest` on push plus an optional
`docker build` smoke test. For v1, local pytest plus these manual checklists are
the gate.
