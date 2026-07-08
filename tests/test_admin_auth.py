import time


def test_unauthenticated_dashboard_redirects_to_login(client):
    resp = client.get("/admin/")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_login_success_sets_session(client):
    resp = client.post(
        "/admin/login", data={"username": "admin", "password": "s3cret-pass"}
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("admin_logged_in") is True


def test_login_wrong_password_generic_error(client):
    resp = client.post(
        "/admin/login", data={"username": "admin", "password": "wrong"}
    )
    assert resp.status_code == 200
    assert b"Invalid credentials" in resp.data
    with client.session_transaction() as sess:
        assert not sess.get("admin_logged_in")


def test_logout_clears_session(auth_client):
    resp = auth_client.post("/admin/logout")
    assert resp.status_code == 302
    with auth_client.session_transaction() as sess:
        assert not sess.get("admin_logged_in")


def test_idle_timeout_forces_relogin(auth_client):
    from config import Config

    stale = time.time() - Config.SESSION_IDLE_TIMEOUT.total_seconds() - 60
    with auth_client.session_transaction() as sess:
        sess["_last_activity"] = stale

    resp = auth_client.get("/admin/")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]
    with auth_client.session_transaction() as sess:
        assert not sess.get("admin_logged_in")


def test_absolute_max_forces_relogin(auth_client):
    from config import Config

    old_login = time.time() - Config.SESSION_ABSOLUTE_MAX.total_seconds() - 60
    with auth_client.session_transaction() as sess:
        sess["_login_at"] = old_login
        # Keep activity recent so only the absolute cap triggers the logout.
        sess["_last_activity"] = time.time()

    resp = auth_client.get("/admin/")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]
    with auth_client.session_transaction() as sess:
        assert not sess.get("admin_logged_in")


def test_active_session_stays_valid(auth_client):
    with auth_client.session_transaction() as sess:
        sess["_last_activity"] = time.time() - 300

    resp = auth_client.get("/admin/")
    assert resp.status_code == 200


def test_legacy_session_without_timestamps_forces_relogin(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["admin_username"] = "admin"

    resp = client.get("/admin/")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_login_regenerates_session(client):
    with client.session_transaction() as sess:
        sess["stale_key"] = "leftover"

    resp = client.post(
        "/admin/login", data={"username": "admin", "password": "s3cret-pass"}
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("admin_logged_in") is True
        assert "stale_key" not in sess
