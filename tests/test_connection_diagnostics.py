import app.routes.admin as admin_mod
from app.utils import connection_test as ct
from config import Config


class _FakeAccount:
    def __init__(self, ok):
        self._ok = ok

    def fetch(self):
        if not self._ok:
            raise RuntimeError("auth failed")
        return object()


class _FakeApi:
    def __init__(self, ok):
        self._ok = ok

    def accounts(self, sid):
        return _FakeAccount(self._ok)


class _FakeNumber:
    def __init__(self, number):
        self.phone_number = number


class _FakeIncoming:
    def __init__(self, number):
        self._number = number

    def list(self, phone_number=None, limit=20):
        return [_FakeNumber(self._number)]


class _FakeClient:
    def __init__(self, ok=True, number=None):
        self.api = _FakeApi(ok)
        self.incoming_phone_numbers = _FakeIncoming(number or Config.TWILIO_PHONE_NUMBER)


class _FakeHttp:
    def __init__(self, status=200, raise_error=False):
        self._status = status
        self._raise = raise_error

    def __call__(self, url, timeout=10):
        if self._raise:
            raise RuntimeError("timed out")

        class _Resp:
            status_code = self._status

        return _Resp()


def _statuses(results):
    return {check["name"]: check["status"] for check in results["checks"]}


def test_all_checks_pass_with_valid_config():
    results = ct.run_all_checks(
        client_factory=lambda: _FakeClient(ok=True), http_get=_FakeHttp(200)
    )
    assert results["overall"] == "pass"
    assert all(check["status"] == "pass" for check in results["checks"])


def test_twilio_api_failure_marks_fail():
    results = ct.run_all_checks(
        client_factory=lambda: _FakeClient(ok=False), http_get=_FakeHttp(200)
    )
    statuses = _statuses(results)
    assert statuses["Twilio API reachable"] == "fail"
    assert statuses["Phone number on account"] == "fail"
    assert results["overall"] == "fail"


def test_health_timeout_warns():
    results = ct.run_all_checks(
        client_factory=lambda: _FakeClient(ok=True),
        http_get=_FakeHttp(raise_error=True),
    )
    assert _statuses(results)["Public health reachable"] == "warn"


def test_signature_self_test_passes():
    results = ct.run_all_checks(
        client_factory=lambda: _FakeClient(ok=True), http_get=_FakeHttp(200)
    )
    assert _statuses(results)["Webhook signature logic"] == "pass"


def test_bad_base_url_fails(monkeypatch):
    monkeypatch.setattr(Config, "BASE_URL", "http://insecure.test")
    results = ct.run_all_checks(
        client_factory=lambda: _FakeClient(ok=True), http_get=_FakeHttp(200)
    )
    assert _statuses(results)["BASE_URL format"] == "fail"
    assert results["overall"] == "fail"


def test_connection_test_requires_auth(client):
    resp = client.post("/admin/connection/test")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_connection_test_rate_limited(make_app, monkeypatch):
    monkeypatch.setattr(
        admin_mod,
        "run_all_checks",
        lambda *a, **k: {"checks": [], "webhook_urls": {}, "overall": "pass"},
    )
    app = make_app(ratelimit_enabled=True)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    last = None
    for _ in range(4):
        last = client.post("/admin/connection/test")
    assert last.status_code == 429
