"""Authentication routes: logout and current user.

VistoFlow runs the panel without Jellyfin: the lifespan pins ``auth_mode`` to
open, so there is no setup wizard and no login. The session-backed branch is
kept only because the request queue and its tests still model accounts.
"""

import logging

from fastapi import APIRouter, Request, Response

from vistoflow_dl import __version__
from vistoflow_dl.auth import models, session as sessions
from vistoflow_dl.auth.deps import current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _session_payload(user: models.User, csrf_token: str) -> dict:
    return {
        "user": user.to_public(),
        "csrf_token": csrf_token,
        "auth_enabled": not models.runtime_open_mode(),
        "version": __version__,
    }


@router.get("/status")
def auth_status():
    """Public: whether the panel needs a login (never, in VistoFlow)."""
    if models.runtime_open_mode():
        return {"setup_done": True, "jellyfin_url": None, "auth_enabled": False}
    return {"setup_done": models.setup_done(), "jellyfin_url": None, "auth_enabled": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    sessions.delete_session(request.cookies.get(sessions.SESSION_COOKIE, ""))
    response.delete_cookie(sessions.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    return _session_payload(user, request.state.csrf_token)
