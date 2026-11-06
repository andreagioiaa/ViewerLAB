# ViewerLAB — media center Python

Prototipo **clean-room** in Python di un media center desktop:

- fonti di contenuti **configurabili dall'utente** (cataloghi JSON, API di ricerca
  JSON, siti web HTML, link diretti);
- **ricerca** su tutte le fonti attive, con punteggio e deduplica;
- **verifica reale** del flusso prima della riproduzione (MP4 / HLS, varianti,
  segmenti, chiavi AES-128);
- riproduzione **dentro l'applicazione** tramite `mpv` incorporato (`--wid`) e
  controlli Qt (play/pausa, stop, seek, volume, schermo intero);
- interfaccia **PySide6**, eseguibile con **PyInstaller**.

Il prototipo nasce dall'analisi statica di `Veezie.st.exe` e del suo `app.asar`
(vedi [ARCHITECTURE.md](ARCHITECTURE.md)), ma **non contiene codice
dell'applicazione analizzata** e non implementa resolver specifici per singoli
siti, estrazione di link protetti, aggiramento di DRM, paywall o autenticazioni.

> **Uso legale**: configura solo fonti e contenuti che hai il diritto di usare.
> Il catalogo demo include esclusivamente open movie e stream di test pubblici.

---

## Requisiti

- Python 3.11+ (testato con 3.14).
- `PySide6` e `httpx` (vedi `requirements.txt`).
- Un eseguibile **mpv** recente (testato con mpv 0.41). mpv **non è incluso**.

### Dove mettere mpv

In ordine di priorità, `viewerlab` cerca mpv in:

1. `--mpv PATH`;
2. variabile d'ambiente `MPV_PATH`;
3. cartella `bin/` accanto all'app (per l'exe: `dist/ViewerLAB/bin/mpv.exe`);
4. `PATH` di sistema.

```powershell
$env:MPV_PATH = "C:\Program Files\mpv\mpv.exe"
```

## Installazione e avvio

```powershell
cd prototype
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m viewerlab
```

oppure:

```powershell
.\run.bat
# oppure
.\run.ps1
```

## Uso

1. Apri **Fonti…** (o il pannello a sinistra) e aggiungi una fonte:
   **Aggiungi** per un catalogo JSON, **Sito web** per un sito HTML,
   **Link diretto** per un singolo flusso.
   Le voci *API di ricerca JSON* e *Sito web* si selezionano anche dal campo
   **Tipo** del dialogo.
2. Scrivi un titolo nella barra di ricerca e premi **Cerca** (campo vuoto =
   mostra tutti gli elementi delle fonti attive).
3. Seleziona un risultato:
   - **Verifica flusso** controlla la raggiungibilità senza riprodurre;
   - **Riproduci** (o doppio clic) verifica e poi avvia il flusso nel player.
4. I controlli in basso gestiscono pausa, stop, ±10 s, seek, volume e
   schermo intero (`F11`, `Esc` per uscire). Spazio = play/pausa.

La configurazione viene salvata automaticamente in:

```
%LOCALAPPDATA%\ViewerLAB\sources.json
```

I log finiscono in `%LOCALAPPDATA%\ViewerLAB\viewerlab.log`.
Usa `--data-dir DIR` per isolare configurazione e log (utile nei test).

### Riga di comando

| Opzione | Descrizione |
|---|---|
| `--self-test [QUERY]` | Test senza GUI: ricerca → verifica → mpv → seek → pausa. |
| `--autoplay QUERY` | Apre la GUI e riproduce il primo risultato. |
| `--smoke-test [QUERY]` | Come autoplay, ma esce con codice 0/1 (usato per la CI). |
| `--mpv PATH` | Percorso esplicito di mpv. |
| `--data-dir DIR` | Cartella per `sources.json` e `viewerlab.log`. |
| `--list-sources` | Stampa le fonti configurate. |
| `--log-level LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `--version` | Versione. |

Esempi:

```powershell
python -m viewerlab --self-test sintel
python -m viewerlab --self-test mux          # HLS con varianti e segmenti
python -m viewerlab --autoplay "big buck bunny"
python -m viewerlab --smoke-test sintel      # esce da solo con esito
```

## Formato delle fonti

### 1. Catalogo JSON (`catalog`)

URL `http(s)` o percorso locale. Struttura:

```json
{
  "items": [
    {
      "title": "Sintel",
      "year": 2010,
      "kind": "mp4",
      "url": "https://download.blender.org/durian/trailer/sintel_trailer-720p.mp4",
      "page": "https://durian.blender.org/",
      "poster": "https://.../poster.jpg",
      "description": "Open movie della Blender Foundation.",
      "headers": { "Referer": "https://durian.blender.org/" },
      "user_agent": "Mozilla/5.0 ..."
    }
  ]
}
```

Campi principali:

| Campo | Obbligatorio | Note |
|---|---|---|
| `title` / `name` | sì | Titolo mostrato e usato per la ricerca. |
| `url` / `stream` / `stream_url` / `link` | sì | URL del flusso. |
| `streams` | no | Lista di URL o oggetti `{ "url": ... }`. |
| `year` | no | Anno. |
| `kind` | no | `hls`, `mp4`; dedotto dall'estensione se assente. |
| `page`, `poster`, `description` | no | Metadati aggiuntivi. |
| `headers`, `referer`, `user_agent` | no | Intestazioni HTTP per la richiesta. |

Le fonti possono dichiarare `headers`, `referer` e `user_agent` anche a livello
di fonte: vengono uniti a quelli dell'elemento.

### 2. API di ricerca JSON (`json_api`)

L'URL deve contenere `{query}`:

```
https://host/api/search?q={query}
```

La risposta deve essere JSON con una lista `items` (o direttamente una lista)
nello stesso formato del catalogo. La ricerca lato server è quindi delegata
all'API configurata; ViewerLAB filtra e ordina localmente i risultati.

### 3. Link diretto (`direct`)

Un titolo e un URL `http(s)` di un file `.mp4`, `.webm`, `.mkv` o manifest
`.m3u8`. Il campo *Etichetta fonte* serve solo a raggruppare i risultati.

### 4. Sito web (`site`)

Inserisci la **home** del sito, non il flusso:

```
https://www.esempio.it
```

ViewerLAB cerca i contenuti sul sito e ricava il flusso dalla pagina del titolo.
La ricerca usa il modulo HTML della home oppure, se il sito non ne espone uno,
l'**URL di ricerca** opzionale con `{query}`:

```
https://www.esempio.it/cerca?q={query}
```

I risultati vengono individuati automaticamente dai link ripetuti delle schede.
Se la pagina ha una struttura particolare puoi indicare selettori CSS
opzionali: *risultati*, *titolo*, *link*, *copertina* (ad esempio
`article.card`, `h3`, `a.cover`, `img`). Con il campo di ricerca vuoto viene
mostrato l'elenco della home.

Dalla pagina del titolo vengono riconosciuti `<video>`/`<source>`, `og:video`,
JSON-LD, link diretti `.mp4/.webm/.mkv/.m3u8` e iframe. Il flusso trovato viene
comunque verificato prima della riproduzione.

Limiti: **nessun JavaScript viene eseguito**, quindi i siti che costruiscono il
player solo lato client o usano DRM non sono supportati. Non esistono resolver
specifici per singoli siti e nessuna protezione viene aggirata.

## Verifica del flusso

Per le fonti `site` la verifica avviene in due fasi: la pagina del contenuto
viene aperta e analizzata per estrarre il flusso, poi il flusso trovato viene
verificato come gli altri. Se non viene trovato alcun flusso riproducibile, il
risultato viene marcato come non disponibile.

`viewerlab/probe.py` non si limita a un `HEAD`:

- **MP4/diretto**: `HEAD`; se non basta, `GET` con `Range: bytes=0-2047`.
  Le risposte HTML vengono rifiutate.
- **HLS master**: scarica il manifest, segue la prima variante, verifica i
  segmenti, il segmento di inizializzazione (`#EXT-X-MAP`) e la chiave
  `AES-128` (`#EXT-X-KEY`).
- I manifest con marcatori DRM (`Widevine`, `PlayReady`, `SAMPLE-AES`,
  `StreamingKeyDelivery`) vengono rifiutati: nessun aggiramento.

Il risultato viene mostrato nella colonna **Stato** e nella barra inferiore.

## Ricerca

- Le fonti attive vengono interrogate **in parallelo** (`ThreadPoolExecutor`).
- Il punteggio premia corrispondenza esatta, prefisso, parola iniziale,
  sottostringa e tutti i token; l'anno nella query aggiunge un bonus.
- Deduplica per titolo normalizzato + URL.
- Una fonte che fallisce non blocca le altre: l'errore viene mostrato nella
  barra di stato.

## Player

- mpv parte alla prima riproduzione con `--wid=<HWND>` del widget video,
  quindi il video è **dentro** la finestra Qt, ridimensionabile e fullscreen.
- Comunicazione JSON IPC su named pipe (Windows) o socket Unix.
- Stato osservato: `time-pos`, `duration`, `pause`, `idle-active`,
  `eof-reached`, dimensioni video, bitrate, buffering, titolo.
- Header HTTP della fonte (Referer, User-Agent, extra) vengono passati a mpv.

## Creare l'eseguibile

```powershell
cd prototype
..\.venv\Scripts\python.exe -m pip install pyinstaller
..\.venv\Scripts\python.exe build_exe.py --clean          # cartella dist/ViewerLAB
..\.venv\Scripts\python.exe build_exe.py --clean --onefile # singolo .exe
```

Il catalogo demo (`sources/`) viene incluso automaticamente. mpv **non** viene
incluso: per distribuire l'app metti `mpv.exe` in `dist/ViewerLAB/bin/` oppure
documenta `MPV_PATH`.

Test dell'eseguibile:

```powershell
$env:MPV_PATH = "D:\percorso\mpv.exe"
Start-Process .\dist\ViewerLAB\ViewerLAB.exe `
  -ArgumentList "--smoke-test","sintel" -Wait -PassThru
```

## Test rapidi

```powershell
# ricerca + verifica + mpv headless (MP4)
..\.venv\Scripts\python.exe -m viewerlab --self-test sintel

# HLS: varianti, segmenti, seek
..\.venv\Scripts\python.exe -m viewerlab --self-test mux

# GUI: ricerca, verifica, riproduzione incorporata, uscita con esito
..\.venv\Scripts\python.exe -m viewerlab --smoke-test sintel
```

## Struttura

```
prototype/
├─ viewerlab/
│  ├─ app.py           # entry point Qt + CLI
│  ├─ main_window.py   # UI, ricerca/probe in thread, orchestrazione player
│  ├─ dialogs.py       # editor fonti e link diretto
│  ├─ html_site.py     # ricerca/risoluzione flussi da siti HTML
│  ├─ player_panel.py  # superficie video + controlli
│  ├─ player.py        # processo mpv e IPC JSON
│  ├─ probe.py         # verifica MP4/HLS
│  ├─ search.py        # punteggio, deduplica, ricerca parallela
│  ├─ sources.py       # cataloghi/API/siti → candidati
│  ├─ models.py        # dataclass condivise
│  ├─ config.py        # percorsi e persistenza fonti
│  └─ selftest.py      # autotest end-to-end
├─ sources/demo_catalog.json
├─ main.py             # launcher
├─ build_exe.py
└─ electron/           # prototipo Electron precedente (legacy)
```

## Limiti noti

- Il supporto ai siti HTML è **generico**: nessun JavaScript, nessun resolver
  specifico, nessun DRM/paywall. I siti che generano il player lato client
  possono non essere supportati.
- I cataloghi in `file://`/percorso locale sono supportati; API e siti devono
  essere raggiungibili via HTTP(S).
- mpv deve essere fornito separatamente.

Per i dettagli su analisi REA, flusso dati e scelte tecniche vedi
[ARCHITECTURE.md](ARCHITECTURE.md).
