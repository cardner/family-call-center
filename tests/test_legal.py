def test_privacy_policy_returns_html(client):
    resp = client.get("/privacy-policy")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    assert b"Privacy Policy" in resp.data
    assert b"Information We Collect" in resp.data


def test_terms_and_conditions_returns_html(client):
    resp = client.get("/terms-and-conditions")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    assert b"Terms and Conditions" in resp.data
    assert b"Acceptable Use" in resp.data


def test_legal_pages_cross_link(client):
    privacy = client.get("/privacy-policy")
    terms = client.get("/terms-and-conditions")
    assert b"/terms-and-conditions" in privacy.data
    assert b"/privacy-policy" in terms.data
