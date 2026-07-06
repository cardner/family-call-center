import pytest


def test_basecoat_css_served_when_vendored(client):
    resp = client.get("/static/vendor/basecoat/basecoat.css")
    if resp.status_code == 404:
        pytest.skip("Basecoat assets not vendored in this environment")
    assert resp.status_code == 200


def test_login_page_uses_basecoat_classes(client):
    resp = client.get("/admin/login")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'class="card"' in body
    assert 'class="btn"' in body or 'class="btn ' in body
