"""Lingua dell'interfaccia (italiano predefinito, inglese opzionale).

Le stringhe nel codice sono in italiano e passano da ``_()``. Con lingua ``en``
vengono cercate nel dizionario ``EN``: prima la corrispondenza esatta, poi i
modelli con ``{}`` (le stringhe già formattate dagli f-string), traducendo anche
le parti variabili quando sono a loro volta messaggi noti.
La lingua si sceglie all'avvio dalle impostazioni e si applica al riavvio.
"""

from __future__ import annotations

import json
import re

LANGUAGES = {"it": "Italiano", "en": "English"}

EN: dict[str, str] = {
    # --- finestra unica / impostazioni
    "Ricarica": "Reload",
    "Ripreso da {time}": "Resumed from {time}",
    "Apri nel browser": "Open in browser",
    "Avvio del pannello di download…": "Starting the download panel…",
    "Il pannello di download non si è avviato: {error}. Dettagli in vistoflow.log.":
        "The download panel did not start: {error}. Details in vistoflow.log.",
    "errore sconosciuto": "unknown error",
    "Impostazioni": "Settings",
    "Lingua": "Language",
    "Lingua dell'interfaccia": "Interface language",
    "Riavvia ora": "Restart now",
    "Più tardi": "Later",
    "La nuova lingua verrà applicata al riavvio di VistoFlow.": "The new language will be applied when VistoFlow restarts.",
    "Libreria": "Library",
    "Indietro": "Back",
    "Tutte": "All",
    # --- ricerca IMDb
    "IMDb": "IMDb",
    "Cerca film e serie su IMDb e nelle tue fonti": "Search films and series on IMDb and in your sources",
    "Scrivi un titolo e premi Invio.": "Type a title and press Enter.",
    "Dalle tue fonti": "From your sources",
    "Ricerca su IMDb…": "Searching IMDb…",
    "{} titoli su IMDb": "{} titles on IMDb",
    "Nessun titolo trovato su IMDb": "No titles found on IMDb",
    "Riproduci dalla libreria": "Play from library",
    "Cerca nelle tue fonti": "Search your sources",
    "Apri su IMDb": "Open on IMDb",
    "Serie TV": "TV series",
    "Film": "Movie",
    "{} stagioni": "{} seasons",
    "Regia": "Director",
    "Cast": "Cast",
    "Disponibile nella tua libreria.": "Available in your library.",
    "Non è nella tua libreria: cercalo nelle tue fonti.": "Not in your library: search your sources.",
    "Nessuna fonte attiva: aggiungile dalla sezione «Fonti».": "No enabled source: add them in the “Sources” panel.",
    "IMDb non raggiungibile: {}": "IMDb unreachable: {}",
    # --- finestra online
    "Catalogo": "Catalog",
    "Link diretto": "Direct link",
    "API JSON": "JSON API",
    "Sito web": "Website",
    "Titolo": "Title",
    "Anno": "Year",
    "Tipo": "Type",
    "Fonte": "Source",
    "Stato": "Status",
    "VistoFlow — Media Center": "VistoFlow — Media Center",
    "Cerca un titolo nei cataloghi configurati (vuoto = mostra tutto)":
        "Search a title in the configured catalogs (empty = show all)",
    "Cerca": "Search",
    "Verifica flusso": "Check stream",
    "Riproduci": "Play",
    "Fonti…": "Sources…",
    "Nessuna ricerca": "No search yet",
    "Pronto": "Ready",
    "Fonti": "Sources",
    "Aggiungi": "Add",
    "Modifica": "Edit",
    "Rimuovi": "Remove",
    "Le fonti sono cataloghi JSON, API JSON, siti web o link diretti che hai il diritto di usare. I flussi vengono verificati prima della riproduzione.":
        "Sources are JSON catalogs, JSON APIs, websites or direct links you have the right to use. Streams are checked before playback.",
    "Fonte aggiunta: {}": "Source added: {}",
    "Sito aggiunto: {}": "Site added: {}",
    "Link aggiunto: {}": "Link added: {}",
    "Fonte aggiornata: {}": "Source updated: {}",
    "Rimuovere la fonte?": "Remove the source?",
    "Rimuovere «{}»?": "Remove “{}”?",
    "Ricerca in corso…": "Searching…",
    "Ricerca non riuscita": "Search failed",
    "{} risultati in {}s da {} fonti configurate": "{} results in {}s from {} configured sources",
    "Ricerca completata: {} risultati": "Search completed: {} results",
    "Verifica non riuscita: {}": "Check failed: {}",
    "mpv non è stato trovato.\n\nImposta la variabile d'ambiente MPV_PATH oppure copia mpv.exe nella cartella bin/ accanto all'applicazione.":
        "mpv was not found.\n\nSet the MPV_PATH environment variable or copy mpv.exe into the bin/ folder next to the application.",
    "Avvio del player…": "Starting player…",
    "Player avviato": "Player started",
    "Errore player: {}": "Player error: {}",
    "Caricamento del flusso…": "Loading stream…",
    "Apertura flusso: {}": "Opening stream: {}",
    "Fermato": "Stopped",
    "Attiva": "Enabled",
    "Nome": "Name",
    "Fonte duplicata": "Duplicate source",
    "Esiste già una fonte con lo stesso identificativo.": "A source with the same identifier already exists.",
    "Nessuna fonte": "No source",
    "Seleziona una fonte da modificare.": "Select a source to edit.",
    "Seleziona una fonte da rimuovere.": "Select a source to remove.",
    "Nessuna fonte attiva": "No enabled source",
    "Aggiungi o attiva almeno una fonte dalla sezione «Fonti».": "Add or enable at least one source in the “Sources” panel.",
    "Fonti con errori — {}": "Sources with errors — {}",
    "Nessun contenuto": "No content",
    "Esegui una ricerca e seleziona un risultato.": "Run a search and select a result.",
    "Verifica già in corso…": "Check already running…",
    "Risoluzione pagina…": "Resolving page…",
    "Verifica…": "Checking…",
    "Ricerca del flusso nella pagina…": "Looking for the stream in the page…",
    "Verifica del flusso…": "Checking stream…",
    " — flusso trovato nella pagina": " — stream found in the page",
    "Non disponibile: {}": "Unavailable: {}",
    "Flusso non disponibile: {}": "Stream unavailable: {}",
    "mpv non disponibile": "mpv unavailable",
    "Superficie video non pronta": "Video surface not ready",
    "Errore del player": "Player error",
    "In riproduzione": "Playing",
    "Flusso avviato: {} — {}s": "Stream started: {} — {}s",
    "Fonte del contenuto non disponibile": "Content source unavailable",
    "Nessun flusso video trovato nella pagina del contenuto": "No video stream found in the content page",
    "Salvataggio fallito": "Save failed",
    "Fonte {}: {} risultati": "Source {}: {} results",
    "Flusso non trovato": "Stream not found",
    "Flusso non disponibile": "Stream unavailable",
    "Il flusso non è raggiungibile o non è riproducibile.\n\n{}": "The stream is unreachable or not playable.\n\n{}",
    "mpv non trovato": "mpv not found",
    "Errore: {}": "Error: {}",
    "Comando non riuscito: {}": "Command failed: {}",
    "Seek non riuscito: {}": "Seek failed: {}",
    "Risoluzione fallita: {}": "Resolution failed: {}",
    "Errore di caricamento": "Loading error",
    # --- dialoghi fonti
    "Catalogo JSON": "JSON catalog",
    "API di ricerca JSON": "JSON search API",
    "Sito web (HTML)": "Website (HTML)",
    "Es. La mia mediateca": "E.g. My media library",
    "Titolo mostrato nei risultati": "Title shown in results",
    "https://... oppure percorso locale del catalogo": "https://... or local catalog path",
    "Opzionale: Referer da inviare al server": "Optional: Referer sent to the server",
    "Opzionale: User-Agent personalizzato": "Optional: custom User-Agent",
    "Intestazioni HTTP aggiuntive, una per riga:\nNome: valore": "Extra HTTP headers, one per line:\nName: value",
    "Fonte attiva": "Source enabled",
    "Es. .card, article, li.result": "E.g. .card, article, li.result",
    "Es. h3 a, .titolo": "E.g. h3 a, .title",
    "Es. a[href]": "E.g. a[href]",
    "Es. img": "E.g. img",
    "URL di ricerca": "Search URL",
    "Selettore risultati": "Results selector",
    "Selettore titolo": "Title selector",
    "Selettore link": "Link selector",
    "Selettore copertina": "Cover selector",
    "Intestazioni": "Headers",
    "Salva": "Save",
    "Annulla": "Cancel",
    "Aggiungi link diretto": "Add direct link",
    "Titolo del contenuto": "Content title",
    "https://host/video.mp4 oppure .../stream.m3u8": "https://host/video.mp4 or .../stream.m3u8",
    "Facoltativo: nome della fonte": "Optional: source name",
    "Facoltativo: Referer": "Optional: Referer",
    "URL del flusso": "Stream URL",
    "Etichetta fonte": "Source label",
    "Il flusso verrà verificato prima della riproduzione. Usa solo contenuti che hai il diritto di guardare.":
        "The stream will be checked before playback. Only use content you have the right to watch.",
    "Link diretti": "Direct links",
    "Intestazione non valida (manca ':'): {}": "Invalid header (missing ':'): {}",
    "Intestazione senza nome: {}": "Header without a name: {}",
    "Modifica fonte": "Edit source",
    "Aggiungi fonte": "Add source",
    "Il link diretto punta a un file o manifest che hai il diritto di riprodurre. Nessun DRM viene aggirato.":
        "The direct link points to a file or manifest you have the right to play. No DRM is bypassed.",
    "Dati non validi": "Invalid data",
    "Il titolo è obbligatorio.": "The title is required.",
    "Il link deve iniziare con http:// o https://.": "The link must start with http:// or https://.",
    "L'API deve restituire JSON con una lista 'items'. Usa {query} nell'URL per passare il testo cercato.":
        "The API must return JSON with an 'items' list. Use {query} in the URL to pass the search text.",
    "Opzionale: https://www.esempio.it/cerca?q={query}": "Optional: https://www.example.com/search?q={query}",
    "Inserisci la home del sito: VistoFlow cerca i contenuti e ricava il flusso dalla pagina del titolo. Se il sito non espone un modulo di ricerca, indica l'URL di ricerca con {query}. I selettori CSS sono opzionali. Nessun JavaScript viene eseguito e nessun DRM viene aggirato.":
        "Enter the site's home page: VistoFlow searches its content and extracts the stream from the title page. If the site has no search form, set the search URL with {query}. CSS selectors are optional. No JavaScript is executed and no DRM is bypassed.",
    "https://host/catalogo.json oppure C:\\percorso\\catalogo.json": "https://host/catalog.json or C:\\path\\catalog.json",
    "Il catalogo è un JSON con 'items'; ogni elemento ha 'title' e 'url' (o 'streams'). Sono supportati URL http/https e file locali.":
        "The catalog is a JSON with 'items'; each item has 'title' and 'url' (or 'streams'). http/https URLs and local files are supported.",
    # --- player
    "Nessun flusso in riproduzione": "Nothing playing",
    "Riproduci / pausa": "Play / pause",
    "Ferma": "Stop",
    "Indietro di 10 secondi": "Back 10 seconds",
    "Avanti di 10 secondi": "Forward 10 seconds",
    "Schermo intero (F11)": "Full screen (F11)",
    "Buffering…": "Buffering…",
    "Fine riproduzione": "Playback finished",
    "In pausa": "Paused",
    # --- messaggi del motore (probe, siti, cataloghi, mpv)
    "Anno non valido.": "Invalid year.",
    "Catalogo troppo grande": "Catalog too large",
    "Il catalogo deve contenere una lista 'items'": "The catalog must contain an 'items' list",
    "Il catalogo non è JSON valido": "The catalog is not valid JSON",
    "Il link diretto deve essere http:// o https://": "The direct link must be http:// or https://",
    "Il nome della fonte è obbligatorio.": "The source name is required.",
    "L'URL di ricerca deve contenere {query}.": "The search URL must contain {query}.",
    "L'URL di ricerca è obbligatorio.": "The search URL is required.",
    "L'URL è obbligatorio.": "The URL is required.",
    "Pagina troppo grande": "Page too large",
    "Percorso del catalogo non valido": "Invalid catalog path",
    "Catalogo non trovato: {}": "Catalog not found: {}",
    "Richiesta fallita: {}": "Request failed: {}",
    "Lettura fallita: {}": "Read failed: {}",
    "Il contenuto non è un manifest HLS valido": "The content is not a valid HLS manifest",
    "Il manifest usa DRM non supportato": "The manifest uses unsupported DRM",
    "La risposta è HTML": "The response is HTML",
    "La risposta è una pagina HTML, non un flusso video": "The response is an HTML page, not a video stream",
    "Manifest HLS non raggiungibile": "HLS manifest unreachable",
    "Playlist master senza varianti": "Master playlist without variants",
    "Sono supportati solo flussi http:// o https://": "Only http:// or https:// streams are supported",
    "Timeout durante la verifica": "Timeout while checking",
    "Troppi livelli di playlist HLS": "Too many HLS playlist levels",
    "HTTP {} o risposta vuota": "HTTP {} or empty response",
    "Errore HTTP: {}": "HTTP error: {}",
    "Variante non raggiungibile: {}": "Variant unreachable: {}",
    "Primo segmento non raggiungibile: {}": "First segment unreachable: {}",
    "Chiave AES-128 non raggiungibile: {}": "AES-128 key unreachable: {}",
    "Init segment non raggiungibile: {}": "Init segment unreachable: {}",
    "Impossibile connettersi a mpv: {}": "Unable to connect to mpv: {}",
    "Pagina dinamica: il player viene creato da JavaScript e non è leggibile senza browser":
        "Dynamic page: the player is built by JavaScript and cannot be read without a browser",
}

_lang = "it"
_templates: list[tuple[re.Pattern[str], str]] = []


def _compile() -> None:
    _templates.clear()
    for key, value in EN.items():
        if "{}" in key:
            pattern = "^" + "(.*?)".join(re.escape(part) for part in key.split("{}")) + "$"
            _templates.append((re.compile(pattern, re.DOTALL), value))


def _(text: str) -> str:
    """Traduce ``text`` nella lingua attiva (l'italiano è il testo sorgente)."""
    if _lang == "it" or not text:
        return text
    exact = EN.get(text)
    if exact is not None:
        return exact
    for pattern, value in _templates:
        match = pattern.match(text)
        if match:
            return value.format(*(_(group) for group in match.groups()))
    return text


def language() -> str:
    return _lang


def set_language(code: str) -> None:
    global _lang
    _lang = code if code in LANGUAGES else "it"
    if _lang != "it" and not _templates:
        _compile()


def _settings_path():
    from .config import data_dir

    return data_dir() / "settings.json"


def load_language() -> str:
    """Legge la lingua salvata (``settings.json`` nella cartella dati)."""
    try:
        code = json.loads(_settings_path().read_text(encoding="utf-8")).get("language", "it")
    except (OSError, ValueError, AttributeError):
        code = "it"
    set_language(code)
    return _lang


def save_language(code: str) -> None:
    path = _settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data["language"] = code if code in LANGUAGES else "it"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
