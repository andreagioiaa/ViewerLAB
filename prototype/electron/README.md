# ViewerLAB — prototipo

Scheletro **clean-room** di un guscio desktop per la riproduzione video:

- finestra Electron che ospita una UI web (demo inclusa oppure URL configurabile);
- riproduzione affidata a **mpv** esterno, pilotato via **JSON IPC** su named pipe;
- **overlay trasparente** a schermo intero con i controlli di trasporto;
- **proxy HLS locale** opzionale (solo loopback) con rewriting dei manifest,
  passthrough delle richieste `Range` e iniezione opzionale di header/token.

Il prototipo nasce dall'analisi statica di `Veezie.st.exe` e del suo `app.asar`,
ma **non contiene codice dell'applicazione analizzata** e non implementa logica
di scraping, estrazione link o aggiramento di protezioni. Vedi
[ARCHITECTURE.md](ARCHITECTURE.md) per la mappatura osservato → prototipo.

## Requisiti

- Node.js 20+ (testato con Node 24)
- `npm install` per Electron
- un eseguibile **mpv** recente

mpv non è incluso: installalo separatamente oppure punta `MPV_PATH` a un
binario esistente. Su Windows, ad esempio:

```powershell
$env:MPV_PATH = "C:\Program Files\mpv\mpv.exe"
```

## Avvio

```powershell
cd prototype
npm install
npm start
```

La demo si apre in locale. Senza mpv la UI parte comunque e segnala che il
player non è disponibile.

Se PowerShell blocca `npm.ps1` per execution policy, usa `npm.cmd`:

```powershell
npm.cmd install
npm.cmd start
```

### Verifica rapida

```powershell
npm run check   # controllo sintattico di tutti i file JS
npm run smoke   # proxy HLS contro uno stream pubblico di test
```

Per caricare una web app compatibile al posto della demo:

```powershell
$env:VIEWERLAB_URL = "https://example.com/"
npm start
```

## Variabili d'ambiente

| Variabile | Default | Significato |
| --- | --- | --- |
| `VIEWERLAB_URL` | *(vuota)* | Se impostata, la finestra principale carica questo URL invece della demo locale. |
| `MPV_PATH` | `bin/mpv(.exe)` o `mpv` nel `PATH` | Percorso dell'eseguibile mpv. |
| `VIEWERLAB_ALLOW_PRIVATE` | `0` | `1` consente al proxy di raggiungere host loopback/privati (solo per test locali). |
| `VIEWERLAB_INSECURE_TLS` | `0` | `1` disabilita la verifica dei certificati TLS del proxy (sconsigliato). |
| `VIEWERLAB_DEBUG` | `0` | `1` abilita i log del proxy HLS. |

## Struttura

```
prototype/
├─ main.js                 # finestra principale, IPC, overlay, ciclo di vita
├─ mpv-manager.js          # spawn mpv + client JSON IPC su named pipe
├─ hls-proxy.js            # server HTTP loopback per manifest e segmenti
├─ preload.js              # API window.ViewerLAB (+ shim ExoPlayer opzionale)
├─ player-preload.js       # API window.Player per l'overlay
├─ player-overlay.html     # overlay trasparente
├─ player-overlay.css
├─ player-overlay.js
├─ www/                    # pagina demo
│  ├─ index.html
│  ├─ app.js
│  └─ style.css
├─ README.md
└─ ARCHITECTURE.md
```

## API renderer

```js
await window.ViewerLAB.info();

await window.ViewerLAB.player.show({
  url: "https://…/stream.m3u8",
  title: "Titolo",
  referer: "https://example.com/",   // opzionale
  userAgent: "…",                    // opzionale
  headers: { "X-Custom": "…" },      // opzionale
  startPosition: 0,                  // secondi, opzionale
});

window.ViewerLAB.player.seekTo(120);
window.ViewerLAB.player.seekBy(-10);
window.ViewerLAB.player.togglePlay();
window.ViewerLAB.player.getState();
window.ViewerLAB.player.close();

const baseUrl = await window.ViewerLAB.proxy.start({ headers: {} });
const proxied = await window.ViewerLAB.proxy.quote(remoteUrl);
window.ViewerLAB.proxy.setToken("?t=…", ["cdn.example"]);   // opzionale
await window.ViewerLAB.proxy.stop();
```

Per compatibilità è disponibile anche `window.stats` con i metodi
`proxy`, `stopProxy`, `setHlsToken`, `startNativeHlsRefresh` e
`stopNativeHlsRefresh`: sono soltanto alias del proxy qui sopra. Il refresh
richiede un endpoint JSON fornito dal chiamante e restituisce `url`/`hls` più
un eventuale `expire`.

Eventi: `player.onState`, `player.onEvent`, `player.onError`, `player.onClosed`.

## Cosa è volutamente escluso

- Scraper o parser specifici di provider/siti.
- Estrazione di link da pagine terze e bypass di token/endpoint protetti.
- Qualsiasi forma di DRM circumvention.
- URL, chiavi, token o identificativi dell'app analizzata.
- Copia di codice, asset o stringhe dal pacchetto `app.asar`.

## Nota d'uso

Usa il prototipo solo con contenuti di cui hai i diritti o che sono
esplicitamente pubblici. Gli stream di test nella demo sono forniti da terzi
(Mux, Google) e servono unicamente a verificare il funzionamento del guscio.
