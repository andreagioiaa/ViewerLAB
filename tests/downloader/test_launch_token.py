"""The per-run secret ViewerLAB uses to keep other local pages out of the panel."""

from tests.downloader.conftest import enable_open_mode
from vistoflow_dl.auth import deps


def test_without_the_token_the_panel_refuses(client, monkeypatch):
    enable_open_mode()
    monkeypatch.setenv(deps.LAUNCH_TOKEN_ENV, "secret")
    assert client.get("/api/domain/settings").status_code == 403
    client.cookies.set(deps.LAUNCH_COOKIE, "wrong")
    assert client.get("/api/domain/settings").status_code == 403
    assert client.get("/api/auth/status").status_code == 200  # public stays public


def test_the_launch_url_sets_the_cookie_once(client, monkeypatch):
    enable_open_mode()
    monkeypatch.setenv(deps.LAUNCH_TOKEN_ENV, "secret")
    response = client.get("/?vf_token=secret", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert client.get("/api/domain/settings").status_code == 200
    assert client.get("/?vf_token=nope", follow_redirects=False).status_code == 200
