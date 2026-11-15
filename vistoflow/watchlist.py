"""Watchlist: film importati dal CSV di Letterboxd o aggiunti dalle schede IMDb.

Salvata in ``watchlist.json`` nella cartella dati. Ogni import aggiunge solo i
film che non c'erano (stesso link Letterboxd, o stesso titolo e anno).
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import time
from pathlib import Path

from .imdb import normalize

LOGGER = logging.getLogger(__name__)

SORT_FIELDS = ("added", "runtime", "year", "rating")


def item_key(name: str, year) -> str:
    return f"{normalize(name)}|{str(year or '').strip()}"


def runtime_minutes(text: str) -> int | None:
    """«142 min», «2h 22min», «2 h» → minuti."""
    hours = re.search(r"(\d+)\s*h", text or "")
    minutes = re.search(r"(\d+)\s*m", text or "")
    if not hours and not minutes:
        return None
    return (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)


def _sort_value(item: dict, field: str):
    imdb = item.get("imdb") or {}
    try:
        if field == "runtime":
            return runtime_minutes(imdb.get("runtime", ""))
        if field == "year":
            return int(str(item.get("year") or "")[:4])
        if field == "rating":
            return float(imdb.get("rating") or "")
    except ValueError:
        return None
    return item.get("added") or ""


def read_letterboxd(path: str | Path) -> list[dict]:
    """Righe del CSV della watchlist di Letterboxd (Date, Name, Year, Letterboxd URI)."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if "Name" not in (reader.fieldnames or []):
            raise ValueError("Il file non è un CSV della watchlist di Letterboxd (manca la colonna Name).")
        return [
            {
                "name": row["Name"].strip(),
                "year": (row.get("Year") or "").strip(),
                "uri": (row.get("Letterboxd URI") or "").strip(),
                "added": (row.get("Date") or "").strip(),
            }
            for row in reader
            if (row.get("Name") or "").strip()
        ]


class Watchlist:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.items: list[dict] = [i for i in data if isinstance(i, dict)] if isinstance(data, list) else []
        except (OSError, ValueError):
            self.items = []

    def _known(self) -> tuple[set[str], set[str]]:
        return {i["key"] for i in self.items}, {i["uri"] for i in self.items if i.get("uri")}

    def contains(self, name: str, year) -> bool:
        return item_key(name, year) in self._known()[0]

    def add(self, name: str, year="", uri: str = "", added: str = "", imdb: dict | None = None) -> bool:
        keys, uris = self._known()
        key = item_key(name, year)
        if key in keys or (uri and uri in uris):
            return False
        self.items.append({
            "key": key, "name": name, "year": str(year or ""), "uri": uri,
            "added": added or time.strftime("%Y-%m-%d"), "imdb": imdb, "lookup_failed": False,
        })
        return True

    def import_letterboxd(self, path: str | Path) -> tuple[int, int]:
        """(film aggiunti, film già presenti). Salva su disco."""
        rows = read_letterboxd(path)
        added = sum(self.add(**row) for row in rows)
        self.save()
        return added, len(rows) - added

    def remove(self, key: str) -> None:
        self.items = [i for i in self.items if i["key"] != key]
        self.save()

    def set_imdb(self, key: str, imdb: dict | None) -> None:
        for item in self.items:
            if item["key"] == key:
                if imdb is not None:  # una ricerca fallita non cancella i dati già trovati
                    item["imdb"] = imdb
                item["lookup_failed"] = imdb is None

    def missing_imdb(self) -> list[dict]:
        # anche le schede salvate prima che esistesse tmdb_id: servono per aprire il film
        return [
            dict(i) for i in self.items
            if not i.get("lookup_failed") and "tmdb_id" not in (i.get("imdb") or {})
        ]

    def sorted(self, field: str = "added", descending: bool = True) -> list[dict]:
        """Ordinati per ``field``; chi non ha il dato (durata, voto) resta in fondo."""
        values = [(_sort_value(i, field), i) for i in self.items]
        present = [pair for pair in values if pair[0] is not None]
        present.sort(key=lambda pair: pair[0], reverse=descending)
        return [i for _v, i in present] + [i for v, i in values if v is None]

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            LOGGER.exception("Impossibile salvare la watchlist")
