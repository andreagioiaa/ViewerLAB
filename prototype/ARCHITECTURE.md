# Architettura di ViewerLAB (Python)

Questo documento descrive il prototipo Python, l'analisi REA del programma
originale e le scelte tecniche. Il prototipo è **clean-room**: non contiene
codice dell'app analizzata e non replica logiche di estrazione link o
aggiramento di protezioni.

---

## 1. Analisi REA di `Veezie.st.exe`

### Metodo

1. Analisi statica dell'eseguibile Windows `D:\PROGRAMMI\Veezie.st\Veezie.st.exe`
   con REA (hash, PE, stringhe, risorse).
2. Estrazione del pacchetto `resources\app.asar`.
3. Analisi del guscio Electron (main, preload, mpv-manager, hls-proxy,
   player-preload, overlay) con il tool di analisi JavaScript di REA.

### Artefatti

| Artefatto | SHA-256 |
|---|---|
| `Veezie.st.exe` | `28ab5100641c84f128dca4dcd051fa859156a909aba5832c0eda9736e8bb4f8f` |
| `app.asar` | `41e00ed1c94223adfb26d5e79f88bb73143b60328ba804ca2fbdd6b6f6ff3a11` |
| shell analizzata (directory) | `a5d965d4c205acae2a38245189a35226526756ae189d560f20ad00cd89e46857` |

Evidence REA:

- eseguibile: `ev_afaa978fd1e2096588ee4b26e4dc805844c79b420e14f50f8a5fa70b6ac81318`;
- shell JavaScript: `ev_e546671de2163b2e4a379a6dcb8c4597314e6a4e3eee7ff5e57f3df8d78ac43b`
  (parent `ev_5edec508f7e883191f8b8f9890f818e801e60e7d9964ec010f6c6f47d9c27ba6`).

### Risultati rilevanti

- Shell Electron con **6 file rilevanti**, **5 file JavaScript analizzati**,
  ~11.400 nodi AST, **0 errori di parsing**.
- **~100 operazioni IPC**, **35 handler nel main process**, **13 API esposte
  dal context bridge**, 63 membri esposti, 4 `BrowserWindow`, 2 preload.
- Il guscio gestisce finestre, download, overlay del player e un
  `mpv-manager` (avvio di mpv e IPC), oltre a un proxy HLS locale
  (`hls-proxy.js`).
- **La ricerca dei contenuti non è implementata nel guscio**: la UI web
  remota la fornisce al guscio. Non esistono nel main/preload selettori,
  cataloghi o endpoint di ricerca incorporati.
- Non sono presenti resolver di siti di terze parti né logica DRM nel guscio
  analizzato.

### Conseguenza per il prototipo

Non essendoci una ricerca locale da replicare, il prototipo implementa una
ricerca **generica e dichiarativa** su fonti configurate dall'utente. Questo
mantiene il comportamento utile (cerca → verifica → riproduci) senza copiare
endpoint o logiche dell'app originale.

---

## 2. Architettura del prototipo

```
┌─────────────────────────────── Qt (PySide6) ───────────────────────────────┐
│ MainWindow                                                                  │
│  ├─ barra ricerca + azioni (Cerca / Verifica / Riproduci / Fonti)           │
│  ├─ QTableWidget risultati (titolo, anno, tipo, fonte, stato)               │
│  ├─ dock Fonti (attiva, nome, tipo) + dialoghi                              │
│  └─ PlayerPanel (VideoSurface + controlli)                                  │
│         │ winId()                                                           │
│         ▼                                                                   │
│  MpvController ── JSON IPC (named pipe / unix socket) ──► mpv --wid=<HWND>  │
└──────────────────────────────────────────────────────────────────────────────┘
        │ QThread                      │ QThread
        ▼                              ▼
  SearchTask                     ProbeTask
  SourceRepository               resolve_site (site) + StreamProbe
  (catalog / json_api / direct / site)  (HTTP HEAD/GET, HLS)
```

### Moduli

| Modulo | Responsabilità |
|---|---|
| `models.py` | `Source`, `StreamCandidate`, `ProbeResult`, `SearchOutcome`; validazione e serializzazione. |
| `config.py` | Percorsi (`%LOCALAPPDATA%\ViewerLAB`), lettura/scrittura atomica di `sources.json`, risoluzione `@bundled/`, `file://`, percorsi locali. |
| `sources.py` | Caricamento cataloghi/API JSON, normalizzazione elementi, unione header, rilevamento HLS/MP4; inoltro delle fonti `site` a `html_site`. |
| `html_site.py` | Ricerca su siti HTML (form/OpenSearch/URL con `{query}`), estrazione risultati con selettori CSS o euristica, risoluzione del flusso dalla pagina del titolo. Nessun JavaScript. |
| `search.py` | Normalizzazione Unicode, punteggio, deduplica, ricerca parallela con isolamento errori per fonte. |
| `probe.py` | Verifica raggiungibilità: HEAD/Range per file, parsing manifest HLS master/media, varianti, init segment, AES-128, rifiuto DRM. |
| `player.py` | Avvio mpv, scoperta binario, IPC JSON (comandi, risposte, eventi, proprietà osservate), header HTTP. |
| `player_panel.py` | Superficie video nativa (`WA_NativeWindow`), slider/seek, volume, fullscreen, stato. |
| `dialogs.py` | Editor fonti (catalogo/API/sito/direct), selettori CSS opzionali, validazione, inserimento header `Nome: valore`. |
| `main_window.py` | Orchestrazione: thread di ricerca/probe/avvio player, cache verifiche, autoplay, smoke test. |
| `app.py`, `__main__.py`, `main.py` | CLI, tema, logging, avvio Qt. |
| `selftest.py` | Test end-to-end senza GUI. |

---

## 3. Flusso di ricerca

1. La GUI crea un `SearchTask` con le fonti attive (snapshot).
2. `SourceRepository` interroga ogni fonte in un pool di thread:
   - `catalog`: scarica il JSON (HTTP o file) e normalizza `items`;
   - `json_api`: sostituisce `{query}` con il testo codificato e scarica il JSON;
   - `site`: individua l'URL di ricerca (modulo HTML, OpenSearch, modello
     `{query}` o schemi comuni), scarica la pagina dei risultati e ne estrae le
     schede; senza query analizza la home;
   - `direct`: produce un solo candidato dal titolo/URL configurati.
3. `score_candidate` calcola il punteggio; i risultati senza corrispondenza
   vengono scartati (query non vuota).
4. Deduplica per `(titolo normalizzato, url)` e ordina per punteggio, titolo,
   anno, URL.
5. La tabella mostra i risultati; gli errori delle fonti vengono riassunti
   nella barra di stato senza interrompere la ricerca.

I candidati `site` puntano alla pagina del contenuto (`needs_resolution=True`):
il flusso viene ricavato in una fase successiva, prima della verifica. Per le
altre fonti il candidato contiene già l'URL del flusso.

---

## 4. Flusso di verifica e riproduzione

```
Riproduci ──► ProbeTask ──► pagina da risolvere? ──sì──► resolve_site
                              │no                            │
                              ▼                              ▼
                          StreamProbe ◄──────────── flusso trovato
                              │ ok?
                              │sì
                              ▼
                    PlayerStartTask (prima volta)
                    mpv.start(--wid=HWND)
                              │ ready
                              ▼
                    MpvController.load()
                    set http-header-fields
                    loadfile <url> replace
                              │ eventi property-change
                              ▼
                    QTimer 300 ms → PlayerPanel + barra stato
```

- La verifica viene memorizzata per `(source_id, url)`; il doppio clic su un
  risultato già verificato salta il probe.
- Il player viene avviato **solo dopo** una verifica positiva.
- `file-loaded` e `duration>0` sono usati come conferma di caricamento;
  lo smoke test attende anche `time-pos ≥ 0.8 s` per provare che la
  riproduzione avanza davvero.

### Dettagli IPC Windows

Su Windows mpv espone una named pipe. Aprire la pipe con `open(path, "r+b")`
e usare un thread di lettura bloccante causa un **deadlock**: un handle
sincrono Windows blocca le altre operazioni mentre una `ReadFile` è in attesa.

Soluzione adottata:

```python
fd = os.open(pipe_name, os.O_RDWR | os.O_BINARY)
os.set_blocking(fd, False)
```

Il thread lettore tratta `BlockingIOError` con una breve pausa; lo scrittore
ritenta in caso di buffer pieno. In alternativa, su Unix si usa un socket
`AF_UNIX`.

Altro dettaglio: i segnali Qt di un `QThread` non devono chiamarsi `started`
o `finished` se si vuole un evento applicativo, perché sono già segnali
nativi di `QThread`. Il task di avvio usa per questo `ready`.

---

## 5. Sicurezza e ambito legale

- Nessun download di contenuti protetti, nessun DRM circumvention.
- I manifest con marcatori DRM vengono **rifiutati** dal probe.
- Le fonti sono dichiarative e scelte dall'utente; il catalogo demo contiene
  solo open movie e stream di test pubblici.
- Gli header HTTP personalizzati sono validati (niente CR/LF, niente nomi con
  `:`), per evitare header injection.
- Le risposte HTML vengono rifiutate come flussi.
- Il supporto ai siti è generico e dichiarativo (URL fornito dall'utente +
  selettori opzionali): nessun JavaScript, nessun resolver per singoli host,
  nessuna credenziale o protezione aggirata.
- I cataloghi locali sono accettati; i link diretti e i siti devono essere `http(s)`.

---

## 6. Packaging

`build_exe.py` invoca PyInstaller con:

- `--windowed` (app desktop senza console);
- `--add-data "sources;sources"` per il catalogo demo;
- `--collect-submodules viewerlab`.

`config.resource_dir()` usa `sys._MEIPASS` quando `sys.frozen` è attivo, così
il catalogo incluso viene trovato. `resolve_mpv()` cerca `mpv.exe` nella
cartella `bin/` **accanto all'eseguibile** quando è frozen, oltre a `MPV_PATH`
e `PATH`.

In modalità `--windowed` `sys.stdout`/`sys.stderr` possono essere `None`:
`app.py` li reindirizza a `os.devnull` e lo smoke test chiude comunque l'app
con un `finally`, registrando l'esito nel log.

---

## 7. Verifiche eseguite

| Test | Esito |
|---|---|
| Analisi REA exe + asar + shell JS | completata (evidence sopra) |
| `--self-test sintel` | ricerca, probe HTTP 200, mpv caricato, seek 26 s, pausa |
| `--self-test mux` | HLS: 5 varianti, 64 segmenti, durata 634.6 s |
| Integrazione fonti (offscreen) | catalogo HTTP, API `{query}`, link diretto, persistenza, errore 404 isolato |
| Fonte `site` (sito locale) | modulo di ricerca scoperto, schede auto-rilevate, dettaglio `<video>`, iframe, selettori CSS, query vuota |
| GUI `--smoke-test sintel` | flusso incorporato 1280×720, posizione ≥ 0.8 s |
| GUI `--smoke-test "sintel diretto"` | riproduzione da fonte `direct` |
| GUI `--smoke-test "Sintel"` da fonte `site` | ricerca → risoluzione pagina → probe MP4 → mpv, posizione 1.0 s |
| GUI `--smoke-test "Bunny"` con selettori | ricerca con `search_url` + selettori CSS, posizione 0.9 s |
| Ridimensionamento/fullscreen | child window mpv segue il widget (822×343 → 1900×931) |
| Cattura frame incorporato | PrintWindow del widget video mostra il frame Sintel |
| Eseguibile PyInstaller | `ViewerLAB.exe --smoke-test sintel` → exit 0, log `SMOKE OK` |
| mpv assente | messaggio "mpv non trovato", exit 1 senza crash |

---

## 8. Scelte e limiti

- **Supporto HTML generico**: una fonte `site` viene analizzata con selettori
  opzionali o euristiche sui link; niente JavaScript e niente selettori
  specifici hardcoded.
- **Niente resolver specifici** per host di terze parti, nessun DRM/paywall.
- La ricerca lato server dipende dall'API configurata; l'app filtra e ordina
  localmente.
- Il player richiede mpv: non viene ridistribuito nel pacchetto.
- Il prototipo Electron precedente è conservato in `electron/` come riferimento
  storico e non è usato dall'app Python.
