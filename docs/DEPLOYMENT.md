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

The other endpoints (`/voicemail`, `/voicemail/done`, `/voicemail/callback`) are
driven by TwiML the app returns; you only configure `/call`.

## 7. Verify

- `curl https://voicemail.yourdomain.com/health` → `{"status":"ok",...}`
- Log in at `https://voicemail.yourdomain.com/admin/login`
- Open the Connection page and run diagnostics
- Place a test call, then confirm the recording appears in the inbox

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
