"""Twilio ↔ NAS connection diagnostics.

Pure functions that return structured results so the admin page can render
pass/warn/fail badges. No user-supplied input is used (the health check always
targets the fixed ``{BASE_URL}/health``), so there is no SSRF surface. Secrets
are never included in results (the account SID is masked if shown).
"""

import logging

from twilio.request_validator import RequestValidator

from config import Config

logger = logging.getLogger(__name__)

PASS = "pass"
WARN = "warn"
FAIL = "fail"
INFO = "info"


def _result(name, status, message, detail=None):
    return {"name": name, "status": status, "message": message, "detail": detail}


def mask_sid(sid):
    if not sid:
        return ""
    if len(sid) <= 6:
        return "AC…"
    return f"{sid[:2]}…{sid[-4:]}"


def webhook_urls():
    base = Config.BASE_URL
    return {
        "voice": f"{base}/call",
        "call_route": f"{base}/call/route",
        "voicemail": f"{base}/voicemail",
        "voicemail_done": f"{base}/voicemail/done",
        "voicemail_callback": f"{base}/voicemail/callback",
    }


def _default_client_factory():
    from twilio.rest import Client

    return Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)


def _default_http_get(url, timeout=10):
    import requests

    return requests.get(url, timeout=timeout)


def _check_config_present():
    missing = [
        key
        for key in (
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_PHONE_NUMBER",
            "BASE_URL",
        )
        if not getattr(Config, key, None)
    ]
    if missing:
        return _result(
            "Configuration present",
            FAIL,
            "Missing required configuration.",
            detail=", ".join(missing),
        )
    return _result(
        "Configuration present",
        PASS,
        "All required environment variables are set.",
    )


def _check_base_url_format():
    base = Config.BASE_URL or ""
    if not base.lower().startswith("https://"):
        return _result(
            "BASE_URL format",
            FAIL,
            "BASE_URL must start with https:// for Twilio webhooks.",
            detail=base,
        )
    if base.endswith("/"):
        return _result(
            "BASE_URL format",
            WARN,
            "BASE_URL should not have a trailing slash.",
            detail=base,
        )
    return _result("BASE_URL format", PASS, base)


def _check_twilio_api(client_factory):
    try:
        client = client_factory()
        client.api.accounts(Config.TWILIO_ACCOUNT_SID).fetch()
        return (
            _result(
                "Twilio API reachable",
                PASS,
                "Authenticated with Twilio.",
                detail=f"Account {mask_sid(Config.TWILIO_ACCOUNT_SID)}",
            ),
            client,
        )
    except Exception as exc:  # noqa: BLE001 - surface any Twilio/client error
        logger.warning("Twilio API check failed", exc_info=True)
        return (
            _result(
                "Twilio API reachable",
                FAIL,
                "Could not authenticate with Twilio. Check SID and auth token.",
                detail=str(exc),
            ),
            None,
        )


def _check_phone_number(client):
    if client is None:
        return _result(
            "Phone number on account",
            FAIL,
            "Skipped: Twilio API was not reachable.",
        )
    try:
        numbers = client.incoming_phone_numbers.list(
            phone_number=Config.TWILIO_PHONE_NUMBER, limit=20
        )
        for number in numbers:
            if getattr(number, "phone_number", None) == Config.TWILIO_PHONE_NUMBER:
                return _result(
                    "Phone number on account",
                    PASS,
                    f"{Config.TWILIO_PHONE_NUMBER} is configured on this account.",
                )
        return _result(
            "Phone number on account",
            FAIL,
            f"{Config.TWILIO_PHONE_NUMBER} was not found on this Twilio account.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Phone number check failed", exc_info=True)
        return _result(
            "Phone number on account",
            FAIL,
            "Could not look up the phone number.",
            detail=str(exc),
        )


def _check_public_health(http_get):
    url = f"{Config.BASE_URL}/health"
    try:
        response = http_get(url, timeout=10)
        status_code = getattr(response, "status_code", None)
        if status_code == 200:
            return _result(
                "Public health reachable",
                PASS,
                f"{url} responded 200.",
            )
        return _result(
            "Public health reachable",
            WARN,
            f"{url} responded {status_code}. If testing from your LAN this can be "
            "hairpin NAT; verify from an external network.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("Public health check failed for %s", url, exc_info=True)
        return _result(
            "Public health reachable",
            WARN,
            "Could not reach the public health URL. Check NPM proxy, DNS, and "
            "port 443. Testing from cellular/off-LAN is more reliable.",
            detail=str(exc),
        )


def _check_webhook_signature():
    try:
        validator = RequestValidator(Config.TWILIO_AUTH_TOKEN)
        url = f"{Config.BASE_URL}/call"
        params = {"CallSid": "CAtest0000000000000000000000000000", "From": "+10000000000"}
        signature = validator.compute_signature(url, params)
        if validator.validate(url, params, signature):
            return _result(
                "Webhook signature logic",
                PASS,
                "Signature validation round-trips for BASE_URL/call.",
            )
        return _result(
            "Webhook signature logic",
            FAIL,
            "Signature validation failed for BASE_URL/call.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook signature self-test failed", exc_info=True)
        return _result(
            "Webhook signature logic",
            FAIL,
            "Signature self-test raised an error.",
            detail=str(exc),
        )


def _overall(checks):
    statuses = {check["status"] for check in checks}
    if FAIL in statuses:
        return FAIL
    if WARN in statuses:
        return WARN
    return PASS


def run_all_checks(client_factory=None, http_get=None):
    """Run every diagnostic and return checks, webhook URLs, and overall status."""
    client_factory = client_factory or _default_client_factory
    http_get = http_get or _default_http_get

    checks = [
        _check_config_present(),
        _check_base_url_format(),
    ]

    api_result, client = _check_twilio_api(client_factory)
    checks.append(api_result)
    checks.append(_check_phone_number(client))
    checks.append(_check_public_health(http_get))
    checks.append(_check_webhook_signature())

    return {
        "checks": checks,
        "webhook_urls": webhook_urls(),
        "overall": _overall(checks),
    }
