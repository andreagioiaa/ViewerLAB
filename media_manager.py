"""Gestione dati di VistoFlow Pro.

Il file di configurazione contiene:
    library_paths  -> cartelle / file aggiunti alla libreria
    media_history  -> avanzamento di riproduzione (per percorso, con fallback sul nome)
    file_meta      -> classificazione manuale (film/serie, titolo, TAG, ...) per percorso
    online         -> configurazione della ricerca online (TMDB, lingua, canali)
"""

import hashlib
import json
import os
import re
import shutil
import sys

VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".ts", ".flv", ".wmv", ".mpg", ".mpeg"
)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

# Parole tipiche dei nomi "di scena" che non fanno parte del titolo.
_JUNK_RE = re.compile(
    r"\b(?:2160p|1080p|1080i|720p|576p|480p|4k|uhd|hdr10|hdr|dolby\s?vision|"
    r"web[-_. ]?dl|webrip|bluray|blu[-_. ]?ray|brrip|bdrip|dvdrip|hdrip|"
    r"x264|x265|h264|h265|hevc|avc|aac|ac3|eac3|dts|truehd|atmos|"
    r"remux|multi)\b",
    re.IGNORECASE,
)
_BRACKETS_RE = re.compile(r"[\[\]\(\)\{\}]")

_EP_PATTERNS = [
    # Serie_S01E02_Titolo / Serie.S1.E2.Titolo
    re.compile(
        r"^(?P<series>.+?)[\s._-]+S(?P<season>\d{1,2})[\s._-]*E(?P<episode>\d{1,3})"
        r"(?:[\s._-]+(?P<title>.*))?$",
        re.IGNORECASE,
    ),
    # Serie 1x02 Titolo
    re.compile(
        r"^(?P<series>.+?)[\s._-]+(?P<season>\d{1,2})x(?P<episode>\d{1,3})"
        r"(?:[\s._-]+(?P<title>.*))?$",
        re.IGNORECASE,
    ),
    # Serie S01 02 / Serie S01 EP02 / Serie S01 - 02
    re.compile(
        r"^(?P<series>.+?)[\s._-]+S(?P<season>\d{1,2})[\s._-]+"
        r"(?:E|EP|EPISODIO)?[\s._-]*(?P<episode>\d{1,3})"
        r"(?:[\s._-]+(?P<title>.*))?$",
        re.IGNORECASE,
    ),
    # Serie Stagione 1 Episodio 2
    re.compile(
        r"^(?P<series>.+?)[\s._-]+(?:stagione|season)[\s._-]*(?P<season>\d{1,2})"
        r"[\s._-]+(?:episodio|episode|ep|e)[\s._-]*(?P<episode>\d{1,3})"
        r"(?:[\s._-]+(?P<title>.*))?$",
        re.IGNORECASE,
    ),
]

# Nomi che contengono solo stagione/episodio: la serie si ricava dalla cartella.
_EP_ONLY_PATTERNS = [
    re.compile(
        r"^S(?P<season>\d{1,2})[\s._-]*(?:E|EP|EPISODIO)?[\s._-]*"
        r"(?P<episode>\d{1,3})(?:[\s._-]+(?P<title>.*))?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<season>\d{1,2})x(?P<episode>\d{1,3})"
        r"(?:[\s._-]+(?P<title>.*))?$",
        re.IGNORECASE,
    ),
]

_GENERIC_FOLDERS = re.compile(
    r"^(?:stagione|season|series?|serie(?:\s*tv)?|tv|film|movies?|video|media|"
    r"multimedia|downloads?|desktop|documents?|documenti|users?|utenti?|onedrive|"
    r"libreria|library)$",
    re.IGNORECASE,
)

DEFAULT_DATA = {
    "library_paths": [],
    "media_history": {},
    "file_meta": {},
    "covers": {},
    # Configurazione della ricerca online integrata (TMDB, canali, lingua).
    "online": {},
}
KINDS = ("film", "serie")


def _clean_text(text):
    """Trasforma punti/underscore in spazi e uniforma le parentesi."""
    if not text:
        return ""
    text = _BRACKETS_RE.sub(" ", text)
    text = re.sub(r"[._]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_\t")


def _clean_title(text):
    base = _clean_text(text)
    cleaned = _JUNK_RE.sub(" ", base)
    return re.sub(r"\s+", " ", cleaned).strip(" -_.")


def _to_int_str(value, default=1):
    try:
        return str(int(str(value).strip()))
    except (TypeError, ValueError):
        return str(default)


def _app_dir():
    """Cartella dei dati: accanto all'exe quando l'app è compilata."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


class MediaManager:
    def __init__(self, config_path="visto_settings.json"):
        if not os.path.isabs(config_path):
            config_path = os.path.join(_app_dir(), config_path)
        self.config_path = config_path
        self.data = self._load_config()

    # ------------------------------------------------------------------ config
    def _load_config(self):
        data = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, ValueError):
                data = {}

        for key, value in DEFAULT_DATA.items():
            data.setdefault(key, json.loads(json.dumps(value)))

        if not isinstance(data.get("library_paths"), list):
            data["library_paths"] = []
        if not isinstance(data.get("media_history"), dict):
            data["media_history"] = {}
        if not isinstance(data.get("file_meta"), dict):
            data["file_meta"] = {}
        if not isinstance(data.get("covers"), dict):
            data["covers"] = {}
        if not isinstance(data.get("online"), dict):
            data["online"] = {}

        # Rimuove duplicati e percorsi vuoti mantenendo l'ordine.
        seen = set()
        paths = []
        for path in data["library_paths"]:
            if not isinstance(path, str):
                continue
            path = os.path.normpath(path)
            key = os.path.normcase(path)
            if path and key not in seen:
                seen.add(key)
                paths.append(path)
        data["library_paths"] = paths
        return data

    def save_config(self):
        folder = os.path.dirname(self.config_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp_path = self.config_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, self.config_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    # --------------------------------------------------------------- libreria
    def add_library_path(self, path):
        path = os.path.normpath(path)
        current = {os.path.normcase(p) for p in self.data["library_paths"]}
        if os.path.normcase(path) in current:
            return False
        self.data["library_paths"].append(path)
        self.save_config()
        return True

    def remove_library_path(self, path):
        target = os.path.normcase(os.path.normpath(path))
        before = len(self.data["library_paths"])
        self.data["library_paths"] = [
            p for p in self.data["library_paths"] if os.path.normcase(p) != target
        ]
        if len(self.data["library_paths"]) != before:
            self.save_config()
            return True
        return False

    def scan_libraries(self):
        found = []
        seen = set()
        extensions = VIDEO_EXTENSIONS
        for path in self.data.get("library_paths", []):
            if not os.path.exists(path):
                continue
            if os.path.isfile(path):
                if path.lower().endswith(extensions):
                    key = os.path.normcase(path)
                    if key not in seen:
                        seen.add(key)
                        found.append(path)
                continue

            for root, dirs, files in os.walk(path):
                # Evita cartelle di sistema / nascoste.
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".")
                    and d.lower() not in ("$recycle.bin", "system volume information")
                ]
                for name in files:
                    if name.lower().endswith(extensions):
                        full = os.path.join(root, name)
                        key = os.path.normcase(full)
                        if key not in seen:
                            seen.add(key)
                            found.append(full)
        return found

    # ------------------------------------------------------------- nomi/metadati
    @staticmethod
    def get_clean_name(filename):
        """Rimuove il prefisso VISTO__ usato per i confronti nel JSON."""
        return os.path.basename(filename).replace("VISTO__", "")

    def get_display_name(self, filename):
        base = self.get_clean_name(filename)
        base = os.path.splitext(base)[0]
        name = _clean_title(base)
        return name or base

    def _infer_series_from_path(self, filepath):
        """Ricava il nome della serie dalla cartella che contiene l'episodio."""
        folder = os.path.dirname(os.path.abspath(filepath))
        for _ in range(8):
            name = os.path.basename(folder)
            if not name or re.fullmatch(r"[A-Za-z]:", name):
                break
            if (
                not _GENERIC_FOLDERS.match(name)
                and not re.match(r"^(?:stagione|season)\s*\d+$", name, re.IGNORECASE)
                and not re.match(r"^s\d{1,2}$", name, re.IGNORECASE)
            ):
                cleaned = _clean_title(name)
                if cleaned:
                    return cleaned
            parent = os.path.dirname(folder)
            if parent == folder:
                break
            folder = parent
        return ""

    def parse_filename(self, filename, filepath=None):
        """Riconosce i pattern più comuni dei nomi di episodi.

        Ritorna None se il nome non sembra un episodio (quindi è un film).
        Se il nome contiene solo stagione/episodio (es. "S04 01"), la serie
        viene ricavata dalle cartelle del percorso.
        """
        clean = os.path.splitext(self.get_clean_name(filename))[0]
        clean = _clean_text(clean)

        match = None
        for pattern in _EP_PATTERNS:
            match = pattern.match(clean)
            if match:
                series = _clean_title(match.group("series")) or "Sconosciuto"
                break

        if match is None:
            for pattern in _EP_ONLY_PATTERNS:
                match = pattern.match(clean)
                if match:
                    path = filepath or filename
                    series = self._infer_series_from_path(path) or "Sconosciuto"
                    break

        if match is None:
            return None

        season = _to_int_str(match.group("season"))
        episode = _to_int_str(match.group("episode"))
        title = _clean_title(match.group("title") or "")
        if not title:
            title = f"Episodio {episode}"
        return {
            "serie": series,
            "stagione": season,
            "episodio": episode,
            "titolo": title,
            "original_name": filename,
        }

    @staticmethod
    def _path_key(filepath):
        """Chiave univoca per percorso: evita collisioni tra file omonimi."""
        return os.path.normcase(os.path.normpath(os.path.abspath(filepath)))

    def get_meta(self, filepath):
        if not isinstance(self.data.get("file_meta"), dict):
            return {}
        key = self._path_key(filepath)
        if key in self.data["file_meta"]:
            return self.data["file_meta"][key] or {}
        # Compatibilità con eventuali metadati salvati per solo nome file.
        return self.data["file_meta"].get(self.get_clean_name(filepath), {}) or {}

    def _meta_for_write(self, filepath):
        if not isinstance(self.data.get("file_meta"), dict):
            self.data["file_meta"] = {}
        key = self._path_key(filepath)
        return self.data["file_meta"].setdefault(key, {})

    def update_meta(self, filepath, **fields):
        """Aggiorna i metadati manuali. Valori None/vuoti rimuovono la chiave."""
        meta = self._meta_for_write(filepath)
        for key, value in fields.items():
            if value is None or value == "" or value == []:
                meta.pop(key, None)
            elif key in ("tags",):
                meta[key] = self._normalize_tags(value)
            else:
                meta[key] = value
        if not meta:
            self.data["file_meta"].pop(self._path_key(filepath), None)
        self.save_config()

    def get_kind(self, filepath):
        kind = self.get_meta(filepath).get("kind")
        if kind in KINDS:
            return kind
        return "serie" if self.parse_filename(os.path.basename(filepath), filepath) else "film"

    def set_kind(self, filepath, kind):
        if kind not in KINDS:
            return
        self.update_meta(filepath, kind=kind)

    @staticmethod
    def _normalize_tags(tags):
        if isinstance(tags, str):
            tags = re.split(r"[,;]", tags)
        result = []
        seen = set()
        for tag in tags or []:
            tag = str(tag).strip()
            if not tag:
                continue
            key = tag.casefold()
            if key not in seen:
                seen.add(key)
                result.append(tag)
        return result

    def get_tags(self, filepath):
        return self._normalize_tags(self.get_meta(filepath).get("tags", []))

    def set_tags(self, filepath, tags):
        self.update_meta(filepath, tags=tags)

    def add_tags(self, filepath, tags):
        current = self.get_tags(filepath)
        self.set_tags(filepath, current + list(tags))

    def remove_tag(self, filepath, tag):
        key = str(tag).casefold()
        self.set_tags(filepath, [t for t in self.get_tags(filepath) if t.casefold() != key])

    def all_tags(self):
        tags = {}
        for meta in self.data.get("file_meta", {}).values():
            if not isinstance(meta, dict):
                continue
            for tag in self._normalize_tags(meta.get("tags", [])):
                tags.setdefault(tag.casefold(), tag)
        return sorted(tags.values(), key=str.casefold)

    # --------------------------------------------------------------- copertine
    @staticmethod
    def cover_key(kind, name):
        """Chiave della copertina: una per film o per intera serie TV."""
        return f"{kind}|{(name or '').strip().casefold()}"

    @property
    def covers_dir(self):
        """Cartella locale in cui vengono copiate le copertine importate."""
        return os.path.join(os.path.dirname(self.config_path), "covers")

    def _covers(self):
        if not isinstance(self.data.get("covers"), dict):
            self.data["covers"] = {}
        return self.data["covers"]

    def get_cover(self, kind, name):
        """Percorso della copertina associata, oppure None se manca."""
        path = self._covers().get(self.cover_key(kind, name))
        if path and os.path.isfile(path):
            return path
        return None

    def set_cover(self, kind, name, source_path):
        """Copia l'immagine nella cartella locale e la associa a film/serie.

        Ritorna il percorso della copia salvata, oppure None se il file non
        è un'immagine valida. La copia evita copertine mancanti se l'originale
        viene spostato o cancellato.
        """
        if kind not in KINDS or not (name or "").strip():
            return None
        source = os.path.abspath(source_path)
        if not os.path.isfile(source):
            return None
        extension = os.path.splitext(source)[1].lower()
        if extension not in IMAGE_EXTENSIONS:
            return None

        slug = re.sub(r"[^0-9a-z]+", "-", name.casefold()).strip("-")[:40] or "copertina"
        digest = hashlib.sha1(self.cover_key(kind, name).encode("utf-8")).hexdigest()[:8]
        os.makedirs(self.covers_dir, exist_ok=True)
        target = os.path.join(self.covers_dir, f"{kind}-{slug}-{digest}{extension}")

        old_path = self.get_cover(kind, name)
        if os.path.normcase(source) != os.path.normcase(target):
            try:
                shutil.copyfile(source, target)
            except OSError:
                return None

        self._covers()[self.cover_key(kind, name)] = target
        if old_path and os.path.normcase(old_path) != os.path.normcase(target):
            self._delete_local_cover(old_path)
        self.save_config()
        return target

    def remove_cover(self, kind, name):
        key = self.cover_key(kind, name)
        path = self._covers().pop(key, None)
        if path is None:
            return False
        self._delete_local_cover(path)
        self.save_config()
        return True

    def move_cover(self, kind, old_name, new_name, old_kind=None):
        """Mantiene la copertina quando si rinomina film o serie."""
        old_key = self.cover_key(old_kind or kind, old_name)
        new_key = self.cover_key(kind, new_name)
        if old_key == new_key:
            return False
        covers = self._covers()
        if old_key not in covers or new_key in covers:
            return False
        covers[new_key] = covers.pop(old_key)
        self.save_config()
        return True

    def _delete_local_cover(self, path):
        """Elimina solo le copie gestite dall'app, mai l'originale dell'utente."""
        try:
            folder = os.path.normcase(os.path.abspath(self.covers_dir))
            target = os.path.normcase(os.path.abspath(path))
            if os.path.commonpath([folder, target]) == folder and os.path.isfile(target):
                os.remove(target)
        except (OSError, ValueError):
            pass

    # ---------------------------------------------------------------- lettura
    def _get_history(self, filepath):
        history = self.data.get("media_history", {}) or {}
        entry = history.get(self._path_key(filepath))
        if entry is None:
            # Compatibilità con lo storico salvato per solo nome file.
            entry = history.get(self.get_clean_name(filepath))
        return entry or {}

    def describe(self, filepath):
        """Restituisce un dizionario pronto per la UI."""
        filename = os.path.basename(filepath)
        parsed = self.parse_filename(filename, filepath) or {}
        meta = self.get_meta(filepath)
        kind = meta.get("kind") if meta.get("kind") in KINDS else None
        if kind is None:
            kind = "serie" if parsed else "film"

        display_name = self.get_display_name(filename)
        title = _clean_title(meta.get("title") or "") or parsed.get("titolo") or display_name

        if kind == "serie":
            series = _clean_title(meta.get("series") or "") or parsed.get("serie") or display_name
            season = _to_int_str(meta.get("season") or parsed.get("stagione") or 1)
            episode = _to_int_str(meta.get("episode") or parsed.get("episodio") or 1)
        else:
            series = title
            season = ""
            episode = ""

        history = self._get_history(filepath)
        status = self.get_status(filepath)
        duration = history.get("total_duration", 0) or 0
        position = history.get("last_timestamp", 0) or 0
        progress = 0.0
        if duration > 0:
            progress = max(0.0, min(1.0, position / duration))
        elif history.get("status"):
            progress = 1.0

        return {
            "path": filepath,
            "filename": filename,
            "kind": kind,
            "series": series,
            "season": season,
            "episode": episode,
            "title": title,
            "tags": self.get_tags(filepath),
            "cover": self.get_cover(kind, series),
            "status": status,
            "progress": progress,
            "position": position,
            "duration": duration,
        }

    def get_status(self, filepath):
        history = self._get_history(filepath)
        if history.get("status"):
            return "visto"
        if history.get("last_timestamp", 0) > 5000:
            return "iniziato"
        return "nuovo"

    def get_start_time(self, filepath):
        history = self._get_history(filepath)
        position = history.get("last_timestamp", 0) or 0
        duration = history.get("total_duration", 0) or 0
        if history.get("status"):
            return 0
        if duration and position >= duration - 5000:
            return 0
        return position

    # -------------------------------------------------------------- avanzamento
    def update_history(self, filepath, timestamp, duration, finished=False, save=True):
        key = self._path_key(filepath)
        previous = self._get_history(filepath)
        self.data.setdefault("media_history", {})[key] = {
            "last_timestamp": timestamp,
            "total_duration": duration,
            # Un film già segnato come visto resta visto anche se viene riavviato.
            "status": bool(previous.get("status")) or bool(finished),
        }
        if save:
            self.save_config()

    def force_mark_as_seen(self, filepath):
        key = self._path_key(filepath)
        history = self._get_history(filepath)
        duration = history.get("total_duration", 1000) or 1000
        self.data.setdefault("media_history", {})[key] = {
            "last_timestamp": duration,
            "total_duration": duration,
            "status": True,
        }
        self.save_config()

    def mark_unseen(self, filepath):
        key = self._path_key(filepath)
        history = self._get_history(filepath)
        duration = history.get("total_duration", 0) or 0
        self.data.setdefault("media_history", {})[key] = {
            "last_timestamp": 0,
            "total_duration": duration,
            "status": False,
        }
        self.save_config()
