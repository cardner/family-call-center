def test_login_rate_limited_after_five_attempts(make_app):
    app = make_app(ratelimit_enabled=True)
    client = app.test_client()

    last = None
    for _ in range(6):
        last = client.post(
            "/admin/login", data={"username": "admin", "password": "wrong"}
        )
    assert last.status_code == 429
