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
