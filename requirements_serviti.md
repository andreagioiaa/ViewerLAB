# Requisiti e diagnosi dei link — modalità Online

Questo file riassume come funziona Veezie.st (analisi REA), perché i link della
modalità **Online** di ViewerLAB davano errore, cosa è stato corretto e cosa
resta da fare.

## 1. Come funziona Veezie.st (evidenze REA)

Analisi statica di `D:\PROGRAMMI\Veezie.st\resources\app.asar`
(SHA-256 `41e00ed1c94223adfb26f9e79f88bb73143b60328ba804ca2fbdd6b6f6ff3a11`).

| Evidence | Contenuto |
|---|---|
| `ev_c1feaf30c9327875b537f0b51b60f927dc21b120028033513eb8f2d4d74b96c8` | analisi di `main.js`, `preload.js`, `hls-proxy.js`, `mpv-manager.js` (4 file, 0 errori di parsing) |
| `ev_e546671de2163b2e4a379a6dcb8c4597314e6a4e3eee7ff5e57f3df8d78ac43b` | analisi completa precedente del guscio (vedi `docs/ARCHITECTURE.md`) |

**Cosa si vede nel codice (osservato):**

- È un guscio **Electron** con 4 `BrowserWindow`, 2 preload, 12 API esposte
  tramite context bridge e 35 handler IPC nel main process.
- `mpv-manager.js` avvia **mpv come processo figlio** (`resources\bin\mpv.exe`
  è incluso nell'installazione) e lo pilota via IPC JSON. ViewerLAB fa la stessa
  cosa in `vistoflow/player.py`.
- `hls-proxy.js` è un **proxy HLS locale**: inoltra manifest e segmenti a mpv
  aggiungendo gli header richiesti (Referer, User-Agent).

**Cosa si deduce (inferenza):**

- La ricerca e l'estrazione dei link **non stanno nel guscio**: nei 4 file non ci
  sono selettori, cataloghi o endpoint di ricerca. Le fa l'interfaccia web
  remota, che gira in Chromium ed esegue JavaScript. Il guscio riceve solo l'URL
  finale del flusso e i relativi header, poi lo passa a mpv o al proxy.

**Cosa resta sconosciuto:** i restanti 352 file dell'asar non sono stati
analizzati in questo passaggio. Il codice della UI remota non è nel pacchetto,
quindi non è analizzabile staticamente.

## 2. Perché i link di ViewerLAB davano errore

| Sintomo | Causa | Stato |
|---|---|---|
| `HTTP 404` su `…/manifest.webm` | L'espressione regolare che cerca i flussi nella pagina riconosceva `/manifest.webmanifest` (il manifest PWA del sito) come video `manifest.webm`. | **Corretto** in `vistoflow/html_site.py` + test `tests/test_html_site.py` |
| Gli URL `https://…` con `\/` dentro il JSON venivano tagliati | Stessa espressione regolare: scartava le barre con escape. | **Corretto** |
| «La risposta è una pagina HTML, non un flusso video» | Le fonti *Link diretto* configurate puntano a pagine (`/it/titles/…`, `/it/watch/…`), non a file `.m3u8`/`.mp4`. Un link diretto deve essere il flusso. | Uso: configurazione |
| «Nessun flusso video trovato nella pagina» | La pagina del titolo crea il player con JavaScript, dentro un iframe di un altro host, con token firmati e a scadenza. `html_site.py` legge solo l'HTML e non esegue JavaScript. | Ora il messaggio lo dice esplicitamente |
| `Richiesta fallita: [Errno 11001] getaddrinfo failed` (verificato il 14/11/2026) | Il dominio configurato `streamingcommunityz.boo` non risolve più. | Il dominio non esiste più |

## 3. Cosa non è stato implementato e perché

La fonte configurata (StreamingCommunity) distribuisce film e serie senza
licenza. Non ho scritto un estrattore specifico per quel sito o per i suoi host
video (token, playlist firmate, proxy con header). ViewerLAB resta **generico**:
riproduce flussi da fonti che l'utente ha il diritto di usare e non aggira
protezioni.

## 4. Soluzione implementabile (generica, per fonti autorizzate)

1. **Fonti già supportate, senza modifiche:** cataloghi JSON, API di ricerca JSON
   e link diretti `.m3u8`/`.mp4` (vedi `docs/ONLINE.md`). Sono la strada più
   affidabile per servizi che pubblicano i propri flussi.
2. **Pagine dinamiche di siti autorizzati — riuso del browser integrato.** Il
   progetto ha già `vistoflow/browser_engine.py` (processo QtWebEngine separato).
   Intercetta le richieste `.m3u8` della pagina e le invia al padre con URL e
   Referer. Per collegarlo alla modalità Online:
   - in `vistoflow/main_window.py`, quando `resolve_site` restituisce una lista
     vuota, offrire «Apri nel browser integrato» (riusare `WebBrowserDialog`);
   - sul segnale `stream_detected`, creare uno `StreamCandidate` con
     `url`, `referer` e `user_agent` e passarlo a `StreamProbe` e poi a mpv,
     come già avviene per le altre fonti;
   - mantenere i controlli attuali: rifiuto dei manifest DRM in `probe.py`,
     nessun aggiramento di login, CAPTCHA o paywall.
3. **Header verso mpv:** per i flussi che richiedono Referer/User-Agent bastano
   `--http-header-fields`, `--referrer` e `--user-agent`, già impostati da
   `vistoflow/player.py`. Il proxy HLS di Veezie serve solo se le richieste
   successive (segmenti, chiavi) richiedono header diversi per host. In quel caso
   si può aggiungere un piccolo proxy locale `http.server` che riscrive le URL del
   manifest.

## 5. Requisiti di esecuzione

- Python 3.11+ e `pip install -r requirements.txt` (PySide6 6.12, httpx, …).
- **mpv** per la modalità Online: `MPV_PATH`, `bin\mpv.exe` o `PATH`. Per i
  test funziona anche l'mpv incluso in Veezie.st:
  `D:\PROGRAMMI\Veezie.st\resources\bin\mpv.exe`.
- **VLC** installato per la modalità Locale (python-vlc).
- Verifica rapida: `python main.py --self-test sintel` (catalogo demo pubblico).
