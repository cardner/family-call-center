from tests.helpers import extract_csrf, valid_settings


def _login(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True


def test_settings_post_without_csrf_rejected(make_app):
    app = make_app(csrf_enabled=True)
    client = app.test_client()
    _login(client)

    resp = client.post("/admin/settings", data=valid_settings())
    assert resp.status_code == 400


def test_settings_post_with_csrf_succeeds(make_app):
    app = make_app(csrf_enabled=True)
    client = app.test_client()
    _login(client)

    page = client.get("/admin/settings")
    token = extract_csrf(page.get_data(as_text=True))
    assert token

    data = valid_settings()
    data["csrf_token"] = token
    resp = client.post("/admin/settings", data=data)
    assert resp.status_code == 302
