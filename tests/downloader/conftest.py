"""Shared test fixtures.

ViewerLAB has no Jellyfin: accounts are created directly in the database so the
request queue and permission tests keep exercising the panel's own logic.
"""

import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from vistoflow_dl import db
from vistoflow_dl.auth import models, permissions, session as sessions


@pytest.fixture(autouse=True)
def _configured_domain(tmp_path, monkeypatch):
    """Give every test a configured source domain, in a throwaway file.

    This used to come for free from the ``data.json`` committed at the repo
    root, which is no longer shipped — the source domain rotates, so a
    baked-in value is stale by definition. Tests that hit a download or search
    endpoint need one, otherwise the route refuses with 409 before reaching
    what is under test.

    Patched on ``vistoflow_dl.config`` because ``configured_domain()`` reads the module
    constant at call time; the routers import the function, not the path. The
    ``source`` fixture separately points ``resolver.DATA_FILE`` at its own file
    for library paths — same split as before.
    """
    from vistoflow_dl import config

    data_file = tmp_path / "config-data.json"
    data_file.write_text(json.dumps({"domain": "example.test"}), encoding="utf-8")
    monkeypatch.setattr(config, "DATA_FILE", data_file)
    yield data_file


@pytest.fixture(autouse=True)
def _own_database(tmp_path):
    """Every test on a database of its own, even one that never asks for one.

    The library check reads the registry in panel.db (app/library.py), so a
    plain path test reaches the database too. Without this it read whatever
    the previous test had configured — or, run alone, the panel.db in the
    working directory. Same file the ``client`` fixture uses, which finds it
    already migrated.
    """
    db.configure(tmp_path / "test.db")
    db.run_migrations()


@pytest.fixture(autouse=True)
def _no_auto_retry(monkeypatch):
    """A failing job is retried a minute later in production. Tests that fail a
    job on purpose want the failure, not three more calls and three minutes;
    tests/test_job_retry.py turns it back on where it is the subject."""
    from vistoflow_dl import jobs

    monkeypatch.setattr(jobs, "AUTO_RETRIES", 0)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient on a throwaway database, with the app lifespan not started.

    The lifespan would start the download scheduler and re-hydrate the schedule
    store, neither of which belongs in a unit test, so migrations are run here
    instead.
    """
    db.configure(tmp_path / "test.db")
    db.run_migrations()

    from vistoflow_dl.main import app

    # Not entered as a context manager on purpose: that would run the lifespan,
    # which starts the download scheduler and re-hydrates the schedule store.
    yield TestClient(app)
    db.close_all()


@pytest.fixture
def stub_jobs(monkeypatch):
    """Stop download submissions from actually reaching the network.

    The call is bound against the *real* signature before being recorded, so a
    caller passing an argument JobManager does not accept fails here instead of
    passing the tests and raising in production — which is exactly what happened
    with strict_audio.
    """
    import inspect

    from vistoflow_dl.jobs import job_manager

    submitted: list[tuple] = []

    def fake_submit(name):
        signature = inspect.signature(getattr(job_manager, name))

        def _submit(*args, **kwargs):
            signature.bind(*args, **kwargs)  # raises TypeError on a bad call
            submitted.append((name, args, kwargs))
            return f"job-{len(submitted)}"

        return _submit

    for name in ("submit_film", "submit_episode", "submit_anime_episode"):
        monkeypatch.setattr(job_manager, name, fake_submit(name))
    return submitted


class FakeSource:
    """Stands in for StreamingCommunity / AnimeUnity during request tests."""

    def __init__(self):
        self.audio = ["ita", "eng"]
        self.subtitles = ["ita", "eng"]
        self.dead = False
        self.episodes = [{"id": 900 + n, "n": str(n), "name": f"Episodio {n}"} for n in (1, 2, 3)]
        self.anime_episodes = [{"id": 800 + n, "number": str(n)} for n in (1, 2, 3)]
        # The title page's props, read for tmdb_id at approval and for a
        # followed series' year. Empty unless a test says otherwise.
        self.props = {}

    @property
    def languages(self) -> dict:
        if self.dead:
            raise RuntimeError("HTTP 404")
        return {"audio": list(self.audio), "subtitles": list(self.subtitles)}


class InlineExecutor:
    """Runs approval work on the calling thread, so tests stay deterministic."""

    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


@pytest.fixture
def source(monkeypatch, tmp_path):
    """Fake external source plus a temporary library and configured domain."""
    from vistoflow_dl.core import animeunity, film, metadata, page, tv
    from vistoflow_dl.requests import resolver, service

    fake = FakeSource()

    data_file = tmp_path / "data.json"
    library = tmp_path / "library"
    library.mkdir()
    data_file.write_text(
        json.dumps({
            "domain": "example.test",
            "libraries": [
                {"type": "film", "path": str(library)},
                {"type": "tv", "path": str(library)},
                {"type": "anime", "path": str(library)},
            ],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(resolver, "DATA_FILE", data_file)
    fake.library = library

    monkeypatch.setattr(film, "get_film_languages", lambda *a, **k: fake.languages)
    monkeypatch.setattr(page, "get_domain_version", lambda *a, **k: "v1")
    monkeypatch.setattr(tv, "get_token", lambda *a, **k: "xsrf-token")
    monkeypatch.setattr(
        tv, "get_info_season",
        lambda *a, **k: ([] if fake.dead else list(fake.episodes)),
    )
    monkeypatch.setattr(tv, "get_episode_languages", lambda *a, **k: fake.languages)
    monkeypatch.setattr(tv, "get_title_props", lambda *a, **k: dict(fake.props))
    # Process-wide, so one test's props would otherwise answer the next's.
    metadata.clear_cache()
    monkeypatch.setattr(
        animeunity, "get_episodes",
        lambda *a, **k: ([] if fake.dead else list(fake.anime_episodes)),
    )
    monkeypatch.setattr(animeunity, "get_episode_languages", lambda *a, **k: fake.languages)

    # Approval resolution runs inline instead of on its worker pool.
    monkeypatch.setattr(service, "_resolution_pool", InlineExecutor())
    return fake


@pytest.fixture
def admin_credentials():
    return {"username": "admin"}


def do_setup(client, credentials) -> dict:
    """Create the panel administrator and sign ``client`` in as them."""
    models.set_setting(models.SETTING_AUTH_MODE, "accounts")
    user = models.get_user_by_jellyfin_id("admin-id") or models.create_user(
        jellyfin_user_id="admin-id",
        username=credentials["username"],
        permissions=int(permissions.ALL_PERMISSIONS),
        is_jellyfin_admin=True,
    )
    csrf_token = session_for(client, user.id)
    return {"user": user.to_public(), "csrf_token": csrf_token, "auth_enabled": True}


def enable_open_mode():
    """Put the panel in open mode, the way the wizard's "Continua senza
    Jellyfin" button does.

    The setting is the entire switch: there is no environment variable to
    unset and no import-time constant to rebind in three modules.
    """
    models.set_setting(models.SETTING_AUTH_MODE, "open")


def make_user(username: str, jellyfin_user_id: str, perms: int, enabled: bool = True):
    return models.create_user(
        jellyfin_user_id=jellyfin_user_id,
        username=username,
        permissions=perms,
        enabled=enabled,
    )


def session_for(client, user_id: int):
    """Attach a session cookie for ``user_id`` to ``client`` and return its CSRF token."""
    raw_token, csrf_token = sessions.create_session(user_id)
    # A login earlier in the test (do_setup) left the server's own cookie, set
    # for the test host; set() beside it makes a second one of the same name,
    # and which of the two is sent depends on the httpx version.
    client.cookies.delete(sessions.SESSION_COOKIE)
    client.cookies.set(sessions.SESSION_COOKIE, raw_token)
    return csrf_token


ALL = int(permissions.ALL_PERMISSIONS)
