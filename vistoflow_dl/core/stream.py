"""Guardare senza scaricare: il playlist HLS e il referer che servono a un player.

Stessa strada del download (iframe della fonte → embed vixcloud → /playlist),
ma si ferma all'indirizzo: segmenti, chiave AES e tracce audio li gestisce il
player, che riceve il playlist master con il Referer giusto.
"""

from __future__ import annotations

import logging
from typing import Callable

import requests

from vistoflow_dl.core._shared import _parse_content, _get_m3u8_url
from vistoflow_dl.core.headers import get_headers

logger = logging.getLogger(__name__)

# (url, referer, title, key) → None; key identifica il contenuto, per riprendere
# da dove eri. Registrato da VistoFlow (vistoflow/main_window.py); None quando il
# pannello gira senza un player a cui consegnare il flusso.
_player: Callable[[str, str, str, str], None] | None = None


def set_player(player: Callable[[str, str, str, str], None] | None) -> None:
    global _player
    _player = player


def player() -> Callable[[str, str, str, str], None] | None:
    return _player


def _playable(video: dict, param: dict, referer: str) -> str:
    """Il playlist master che risponde. Alcuni episodi danno 403 senza ``b=1``,
    come per il download (m3u8._fetch_text_with_b1_fallback): il player non
    saprebbe ritentare da solo."""
    url = _get_m3u8_url(video, param)
    headers = {"user-agent": get_headers(), "referer": referer}
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 403:
        url = _get_m3u8_url(video, param, add_b1=True)
        response = requests.get(url, headers=headers, timeout=15)
    if not response.ok:
        raise RuntimeError(f"Playlist non disponibile: HTTP {response.status_code}")
    return url


def _from_embed(embed_content: str, url_embed: str) -> dict:
    video, param = _parse_content(embed_content, url_embed)
    return {"url": _playable(video, param, url_embed), "referer": url_embed}


def film_stream(film_id: int, domain: str) -> dict:
    from vistoflow_dl.core import film

    return _from_embed(*film._get_iframe(film_id, domain))


def episode_stream(tv_id: int, episode_id: int, domain: str) -> dict:
    from vistoflow_dl.core import tv

    token = tv.get_token(tv_id, domain)
    return _from_embed(*tv._get_iframe(tv_id, episode_id, domain, token))


def anime_stream(episode_id: int) -> dict:
    from vistoflow_dl.core import animeunity

    return _from_embed(*animeunity._get_embed_content(episode_id))
