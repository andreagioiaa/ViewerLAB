"""Dove eri arrivato: posizione di riproduzione per contenuto, salvata su disco."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)

MIN_RESUME_S = 30.0  # prima di così si riparte dall'inizio
END_MARGIN_S = 90.0  # negli ultimi 90 s (titoli di coda) il contenuto è finito
MAX_ENTRIES = 500


class ResumeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._dirty = False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._items: dict[str, dict] = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self._items = {}

    def get(self, key: str) -> float | None:
        """Secondi da cui riprendere, o None per partire dall'inizio."""
        entry = self._items.get(key) if key else None
        if not entry:
            return None
        position = float(entry.get("position") or 0.0)
        return position if position >= MIN_RESUME_S else None

    def update(
        self, key: str, position: float, duration: float, title: str = "",
        url: str = "", referer: str = "",
    ) -> None:
        if not key or duration <= 0:
            return
        if position >= duration - END_MARGIN_S:
            self._dirty |= self._items.pop(key, None) is not None
            return
        self._items[key] = {
            "position": round(position, 1),
            "duration": round(duration, 1),
            "title": title,
            "url": url,
            "referer": referer,
            "updated": time.time(),
        }
        self._dirty = True

    def latest(self) -> tuple[str, dict] | None:
        """L'ultimo contenuto lasciato a metà che si può riaprire (ha un URL)."""
        playable = [(k, v) for k, v in self._items.items() if v.get("url")]
        return max(playable, key=lambda kv: kv[1].get("updated", 0), default=None)

    def save(self) -> None:
        if not self._dirty:
            return
        if len(self._items) > MAX_ENTRIES:  # tiene i più recenti
            newest = sorted(self._items.items(), key=lambda kv: kv[1].get("updated", 0))
            self._items = dict(newest[-MAX_ENTRIES:])
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self._items, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
            self._dirty = False
        except OSError:
            LOGGER.exception("Impossibile salvare le posizioni di riproduzione")
