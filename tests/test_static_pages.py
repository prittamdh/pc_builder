"""WEB-05: About/Disclaimer and Privacy pages, footer links, contact placeholder."""
from starlette.testclient import TestClient

from configs import settings
from api.main import app

client = TestClient(app)


def test_home_footer_links_to_about_and_privacy():
    html = client.get("/").text
    assert 'href="/about"' in html
    assert 'href="/privacy"' in html


def test_about_page_contains_required_disclosures():
    html = client.get("/about").text
    assert client.get("/about").status_code == 200
    for phrase in ("collected automatically", "may lag", "not affiliated", "verify", "retailer"):
        assert phrase in html


def test_about_contact_coming_soon_when_email_empty(monkeypatch):
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "")
    html = client.get("/about").text
    assert "coming soon" in html
    assert "@" not in html
    assert "{{CONTACT}}" not in html


def test_about_contact_mailto_when_email_set(monkeypatch):
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "hello@test.invalid")
    html = client.get("/about").text
    assert "mailto:hello@test.invalid" in html


def test_about_contact_is_html_escaped(monkeypatch):
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "<b>hello@test.invalid</b>")
    html = client.get("/about").text
    assert "<b>hello@test.invalid</b>" not in html
    assert "&lt;b&gt;" in html


def test_privacy_page_mentions_saved_builds_and_google_fonts():
    resp = client.get("/privacy")
    assert resp.status_code == 200
    html = resp.text
    assert "saved build" in html.lower()
    assert "Google Fonts" in html


def test_about_and_privacy_link_back_and_to_each_other():
    about = client.get("/about").text
    privacy = client.get("/privacy").text
    assert 'href="/"' in about
    assert 'href="/privacy"' in about
    assert 'href="/"' in privacy
    assert 'href="/about"' in privacy
