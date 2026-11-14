"""Guarda in streaming: risolve il flusso e lo consegna al player di VistoFlow."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from vistoflow_dl.auth.deps import require
from vistoflow_dl.auth.permissions import Permission
from vistoflow_dl.config import configured_domain
from vistoflow_dl.core import stream

logger = logging.getLogger(__name__)

# Guardare usa la stessa risoluzione di un download, quindi lo stesso permesso.
router = APIRouter(
    prefix="/api/stream",
    tags=["stream"],
    dependencies=[Depends(require(Permission.DOWNLOAD))],
)


class WatchBody(BaseModel):
    title: str = Field(default="", max_length=300)


def _domain() -> str:
    domain = configured_domain()
    if not domain:
        raise HTTPException(status_code=409, detail="Nessun dominio configurato")
    return domain


async def _watch(resolve, title: str, key: str) -> dict:
    play = stream.player()
    if play is None:
        raise HTTPException(status_code=503, detail="Nessun player disponibile: apri il pannello da VistoFlow")
    try:
        found = await asyncio.to_thread(resolve)
    except Exception as exc:
        logger.warning("Stream resolution failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Streaming non disponibile: {exc}")
    play(found["url"], found["referer"], title, key)
    return {"ok": True}


@router.post("/film/{film_id}")
async def watch_film(film_id: int, body: WatchBody):
    domain = _domain()
    return await _watch(lambda: stream.film_stream(film_id, domain), body.title, f"sc:film:{film_id}")


@router.post("/tv/{tv_id}/episode/{episode_id}")
async def watch_episode(tv_id: int, episode_id: int, body: WatchBody):
    domain = _domain()
    return await _watch(lambda: stream.episode_stream(tv_id, episode_id, domain), body.title,
                        f"sc:tv:{tv_id}:{episode_id}")


@router.post("/anime/episode/{episode_id}")
async def watch_anime_episode(episode_id: int, body: WatchBody):
    return await _watch(lambda: stream.anime_stream(episode_id), body.title, f"au:{episode_id}")
