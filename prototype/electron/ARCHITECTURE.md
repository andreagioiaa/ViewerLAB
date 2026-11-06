# Architettura e provenienza delle osservazioni

Questo documento separa in modo esplicito:

1. ciò che è stato **osservato** nell'artefatto analizzato;
2. ciò che è stato **inferito** dai dati statici;
3. ciò che è stato **scelto** nel prototipo;
4. ciò che resta **non noto**.

L'analisi è stata svolta con REA in sola modalità statica. Il binario non è
stato eseguito.

## 1. Identità degli artefatti

### Eseguibile

| Campo | Valore |
| --- | --- |
| Percorso | `D:\PROGRAMMI\Veezie.st\Veezie.st.exe` |
| SHA-256 | `28ab5100641c84f128dca4dcd051fa859156a909aba5832c0eda9736e8bb4f8f` |
| Dimensione | 201.566.720 byte |
| Formato | PE32+ (`pe32-plus`) |
| Macchina | `34404` (x86_64) |
| Risorse | 54 risorse, 115 voci esaminate |
| Risorse notevoli | `INTEGRITY/ELECTRONASAR` |
| Versione file | `1.0.18` |
| Nome prodotto | `Veezie.st` |
| Descrizione | `Veezie.st Desktop` |
| Copyright | `Copyright © 2026 Veezie` |

Evidence REA: `ev_afaa978fd1e2096588ee4b26e4dc805844c79b420e14f50f8a5fa70b6ac81318`
(`inspect_pe_resources`, copertura dichiarata `complete` sulle risorse).

### Payload applicativo

Il bootstrap Electron carica `resources/app.asar`.

| Campo | Valore |
| --- | --- |
| SHA-256 `app.asar` | `41e00ed1c94223adfb26d5e79f88bb73143b60328ba804ca2fbdd6b6f6ff3a11` |
| Analisi | `analyze_javascript_application`, 269 file JS analizzati |
| Package | `veezie-st-desktop` |
| Versione | `1.0.18` |
| Runtime | Electron |

Evidence REA: `ev_7bb7f7a47866c91c239622532e2f8bbc47036b3364dc72d1cfc4d793388845f6`.

## 2. Comportamento osservato nel pacchetto

Quanto segue è stato letto direttamente dai file estratti da `app.asar`
(`main.js`, `preload.js`, `mpv-manager.js`, `hls-proxy.js`,
`player-preload.js`, `player-overlay.html`).

- **Finestra principale**: `BrowserWindow` con `contextIsolation: true`,
  `nodeIntegration: false`, `sandbox: false`, `webSecurity: false`; carica
  `https://app.veezie.st/new/`.
- **Shim Cordova**: il preload espone `ExoPlayer`, `cordovaHTTP`, flag di
  versione e callback di stato. `ExoPlayer.show()` inoltra un messaggio IPC
  (`mpv-show`) al main process.
- **mpv**: processo separato avviato con
  `--input-ipc-server=\\.\pipe\mpv-veezie-<pid>`, `--idle=once`,
  `--force-window=yes`, `--fullscreen`, `--osc=no`, `--keep-open=yes`,
  `--no-terminal`.
- **Header HTTP**: prima del `loadfile`, il main process imposta la proprietà
  mpv `http-header-fields` con Referer/User-Agent/header aggiuntivi.
- **Stato**: proprietà mpv osservate (`time-pos`, `duration`, `pause`,
  `idle-active`, `eof-reached`, `video-params/w`, `video-params/h`,
  `video-bitrate`, `paused-for-cache`), convertite in un oggetto di stato.
- **Overlay**: una seconda `BrowserWindow` trasparente e fullscreen mostra
  `player-overlay.html` sopra la finestra mpv, con controlli di trasporto.
- **Proxy HLS**: server HTTP su `127.0.0.1` con porta effimera; accetta URL
  remoti codificati, riscrive i manifest `.m3u8` instradando varianti,
  segmenti e chiavi attraverso sé stesso, inoltra `Range` e applica header
  personalizzati. Nel pacchetto include anche un meccanismo di refresh
  periodico del token e pattern specifici del provider.

## 3. Mappatura osservato → prototipo

| Comportamento osservato | Implementazione nel prototipo | Differenza intenzionale |
| --- | --- | --- |
| URL remoto fisso | `VIEWERLAB_URL` o demo locale | Configurabile, nessun host cablato |
| Shim Cordova/ExoPlayer | `preload.js`: API `ViewerLAB` + shim `ExoPlayer` minimale | Solo il sottoinsieme di playback, nessuna API HTTP nativa |
| mpv su named pipe | `mpv-manager.js` | Riscritto da zero sul protocollo IPC pubblico |
| Header via `http-header-fields` | `load(url, { referer, userAgent, headers })` | Stessa tecnica, input generico |
| Polling/osservazione stato | `observe_property` + eventi + polling 400 ms | Ridotto alle proprietà necessarie |
| Overlay trasparente fullscreen | `player-overlay.html/css/js` | Controlli originali, nessun asset copiato |
| Proxy HLS con rewriting | `hls-proxy.js` | Generico, con path segreto e blocco target privati |
| Token refresh con endpoint fornito dal chiamante | `HlsProxy.startRefresh(url, headers, patterns)` | Nessun endpoint, pattern o intervallo cablato |

## 4. Flusso del prototipo

```
┌────────────────────────────┐
│ Renderer (demo o web app)  │
│ window.ViewerLAB           │
└─────────────┬──────────────┘
              │ IPC invoke
┌─────────────▼──────────────┐        ┌──────────────────────┐
│ main.js                    │───────▶│ HlsProxy             │
│ - player lifecycle         │        │ 127.0.0.1:<port>/p/… │
│ - overlay window           │        │ manifest rewrite     │
└─────────────┬──────────────┘        │ Range passthrough    │
              │ JSON IPC (pipe)       └──────────┬───────────┘
┌─────────────▼──────────────┐                   │ HTTP
│ mpv.exe (finestra propria) │◀──────────────────┘
│ --input-ipc-server=…       │
└─────────────▲──────────────┘
              │ comandi/eventi
┌─────────────┴──────────────┐
│ Overlay trasparente        │
│ controlli + timeline       │
└────────────────────────────┘
```

## 5. Scelte di progetto

- **mpv come processo separato**: mantiene il player fuori dal processo
  Chromium, isola i codec e permette di chiudere/riaprire il player senza
  ricaricare la UI.
- **Overlay come finestra dedicata**: consente un fullscreen trasparente sopra
  mpv senza sovrapporre contenuti alla pagina web.
- **Proxy loopback con segreto casuale**: evita che altri processi locali
  possano usare il proxy come relay generico.
- **Blocco dei target privati**: mitigazione SSRF; disattivabile solo
  esplicitamente per test locali.
- **Nessuna logica di provider**: il proxy riceve URL già risolti dal chiamante;
  non conosce CDN, token o pagine di terzi.

## 6. Limiti e questioni aperte

- L'analisi è **statica**: non è stato osservato il comportamento a runtime.
- `player-overlay.html` conteneva un blocco JS inline non analizzato; il
  prototipo non ne dipende.
- Il codice del sito remoto (`app.veezie.st`) è stato consultato solo come
  corroborazione esterna e non fa parte dell'artefatto spedito.
- L'ipotesi che mpv usi una finestra propria (e non un embedding `--wid`) è
  coerente con gli argomenti osservati (`--force-window`, `--fullscreen`,
  `--focus-on=never`), ma non è stata verificata a runtime.
- Il prototipo non implementa DRM, anti-bot, estrazione link o refresh token
  specifici: sono fuori scope per scelta.
