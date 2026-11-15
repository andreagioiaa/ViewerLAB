# ViewerLAB

Media center desktop (PySide6) in un'unica finestra, con barra laterale in stile
Stream Goat:

| Pagina | Cosa fa | Player |
|---|---|---|
| **🏠 Home** | Ricerca su StreamingCommunity e AnimeUnity, vetrine *Di tendenza* e **Continua a guardare**. Dalla scheda di un titolo: **Guarda** o **Scarica**. | mpv |
| **📁 Libreria** | Film e serie TV sul disco, con copertine e **scheda IMDb**. | VLC |
| **🎬 Watchlist** | La watchlist di **Letterboxd** importata da CSV, ordinabile per durata, anno e voto IMDb; un clic apre il film con *Guarda* / *Scarica*. | — |
| **▶ Player** | Riproduzione dei flussi online. | mpv |
| **↓ Download** | Coda dei download con avanzamento, pausa e ripresa. | — |
| **🔔 Serie seguite** | Serie e anime che scaricano da soli i nuovi episodi. | — |
| **🗂 File** | File manager dei contenuti scaricati. | — |
| **⚙ Impostazioni** | Sorgente, librerie, nomi, download e **cartella dei contenuti**, notifiche, hook, MCP, **Generali** (lingua) e **Watchlist** (import CSV). | — |

> **Uso legale**: configura solo fonti autorizzate e contenuti leciti. ViewerLAB
> non aggira DRM, paywall, login o altre protezioni.

## Scarica

Per usare ViewerLAB senza installare Python:

| File | Cosa è |
|---|---|
| [**ViewerLAB.msi**](https://github.com/andreagioiaa/ViewerLAB/releases/latest/download/ViewerLAB.msi) | Installer: doppio clic, nessun permesso di amministratore. Crea il collegamento nel menu Start. |
| [**ViewerLAB-portable.zip**](https://github.com/andreagioiaa/ViewerLAB/releases/latest/download/ViewerLAB-portable.zip) | Versione portatile: estrai lo zip e avvia `ViewerLAB.exe`. |

Tutte le versioni: [Releases](https://github.com/andreagioiaa/ViewerLAB/releases).

- L'installer mette l'app in `%LOCALAPPDATA%\Programs\ViewerLAB` (solo per il
  tuo utente) e si disinstalla da *Impostazioni di Windows → App*. Una versione
  nuova sostituisce quella vecchia; libreria, watchlist e impostazioni restano.
- **VLC** (player della Libreria) e **mpv** (player online) non sono inclusi:
  installali con `winget install VideoLAN.VLC` e `winget install mpv`, oppure
  copia `mpv.exe` nella cartella `bin\` accanto a `ViewerLAB.exe`.
- Windows può mostrare *"Windows ha protetto il PC"* perché l'eseguibile non è
  firmato: *Ulteriori informazioni → Esegui comunque*.

## Download (StreamingCommunity / AnimeUnity)

La pagina **↓ Download** integra il pannello di *StreamingCommunity-downloader*
(pacchetto `vistoflow_dl`), **senza Jellyfin**: niente login né utenti, si usa
subito. Tutto il resto c'è: ricerca e vetrine delle due fonti, scheda titolo
(trama, generi, voto, trailer), download HLS con scelta di audio e sottotitoli,
coda con avanzamento, pausa e ripresa, download programmati, serie/anime
seguiti, recupero automatico del dominio, librerie e schema dei nomi, formato
MKV/MP4, notifiche (Discord, Telegram, ntfy… via Apprise), webhook post-download,
file manager e server MCP per agenti AI.

- **Guarda senza scaricare**: nella scheda di un film (pulsante *Guarda*) o accanto
  a ogni episodio (▶) il pannello risolve il flusso e lo apre nel **player mpv**
  di ViewerLAB, senza scrivere nulla su disco. Funziona anche da *Apri nel
  browser*: il video parte comunque nella finestra di ViewerLAB.
- Il pannello gira in ViewerLAB su `127.0.0.1` (porta casuale) e parte con
  l'app, così download programmati e serie seguite proseguono da soli finché
  ViewerLAB è aperto. **Apri nel browser** lo apre nel browser di sistema.
- Al primo uso imposta il **dominio della sorgente** in *Impostazioni → Sorgente*
  (o accetta quello proposto) e le **librerie** dove salvare i file.
- Dati in `%LOCALAPPDATA%\ViewerLAB\download\`; senza librerie i file vanno in
  `~/Videos/ViewerLAB`. FFmpeg: dal `PATH` o quello incluso in `imageio-ffmpeg`.
- Note tecniche e regole del codice: [docs/DOWNLOAD.md](docs/DOWNLOAD.md).

## IMDb

I metadati arrivano da **Cinemeta** (`v3-cinemeta.strem.io`), il servizio con dati
IMDb usato anche da Stream Goat: non serve una chiave API.

- **Libreria**: ogni film e ogni serie viene collegato automaticamente a IMDb in
  background (anche i titoli italiani: *Salvate il soldato Ryan* → *Saving
  Private Ryan*). L'intestazione della raccolta mostra ★ voto, anno, durata,
  generi, regia e cast; la trama è nel tooltip. Se manca la copertina viene
  importata la locandina IMDb.
- Pulsante **🎬 IMDb**: *Apri su IMDb*, *Collega a un altro titolo…* (titolo o ID
  `tt…`) per correggere un abbinamento, *Aggiorna da IMDb*.
- **Cerca**: risultati IMDb con locandina; la scheda mostra tutti i dettagli e
  offre **Riproduci dalla libreria** (se il titolo è tra i tuoi file),
  **Cerca nelle tue fonti** e **Apri su IMDb**.
- Gli abbinamenti sono salvati in `visto_settings.json` (sezione `imdb`), le
  risposte di Cinemeta in `%LOCALAPPDATA%\ViewerLAB\imdb_cache.json` (14 giorni).
- Le trame sono in inglese (Cinemeta non ha la localizzazione italiana).

## Lingua (italiano / inglese)

**⚙ Impostazioni → Lingua dell'interfaccia** permette di scegliere *Italiano* o
*English*. La scelta viene salvata in `%LOCALAPPDATA%\ViewerLAB\settings.json` e
applicata al riavvio (il dialogo propone **Riavvia ora**). Sono tradotte le
pagine Cerca, Player, Fonti e Impostazioni; la Libreria è in italiano.

## Fonti online e player mpv

Documentazione completa: [docs/ONLINE.md](docs/ONLINE.md). Analisi REA di
Veezie.st e architettura: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Diagnosi
dei link e soluzione proposta: [requirements_serviti.md](requirements_serviti.md).

- mpv non è incluso: imposta `MPV_PATH` oppure copia `mpv.exe` in `bin/`.
- Configurazione e log: `%LOCALAPPDATA%\ViewerLAB\` (`sources.json`, `viewerlab.log`).
  Al primo avvio fonti e lingua vengono copiate dalla vecchia cartella `ViewerLAB`.
- Riga di comando: `python main.py --self-test sintel`, `--autoplay QUERY`,
  `--smoke-test QUERY`, `--mpv PATH`, `--data-dir DIR`, `--list-sources`.

## Libreria


### Ricerca online integrata
- Il pulsante **🌐 Online** nella barra superiore apre la ricerca dentro
  ViewerLAB.
- I canali si configurano con file **JSON/YAML** nella cartella `channels/`
  (selettori CSS generici, nessun sito hardcodato). Vedi
  [`channels/README.md`](channels/README.md).
- La ricerca gira in parallelo su tutti i canali attivi, con timeout e
  isolamento degli errori: un canale lento o rotto non blocca gli altri.
- I risultati mostrano canale, anno, voto, poster e trama **TMDB** quando la
  chiave API è configurata (opzionale). La chiave si imposta anche dalla GUI:
  **Ricerca online → ⋯ → Imposta chiave TMDB…**.
- Selezionando un risultato, **▶ Risolvi e riproduci** apre la pagina dettaglio,
  estrae gli embed e risolve il flusso con i resolver inclusi (`direct`,
  `mixdrop`, `voe`, `supervideo`, `streamtape`).
- Il flusso viene aperto nel **player VLC integrato** con gli header
  `User-Agent` e `Referer` necessari. Se vengono trovati più flussi,
  una finestra permette di sceglierli e di copiare il comando VLC equivalente.
- È disponibile anche **🔗 URL** per risolvere un link `.m3u8`, `.mp4` o una
  pagina generica: ViewerLAB cerca iframe, tag video e URL HLS/MP4 anche dentro
  gli script e, se serve, apre un livello di embed.
- La ricerca, il download dei poster e la risoluzione avvengono in background:
  l'interfaccia non si blocca.

### Link salvati e flussi scaduti
- Il pulsante **🔗 Link** nella barra superiore apre **I miei link**, accessibile
  anche dalla finestra online.
- Ogni link può essere una pagina da risolvere o un flusso diretto. Puoi
  indicare un titolo, un `Referer`, uno `User-Agent` e una **pagina sorgente**.
- I link sono salvati in `visto_settings.json` sotto `online.saved_links` e
  restano disponibili dopo il riavvio.
- **Aggiorna link** rilegge la pagina e salva l'ultimo flusso trovato.
- Se durante la riproduzione VLC rileva un link scaduto, ViewerLAB prova
  automaticamente a rileggere la pagina sorgente o il risultato del canale e a
  ripartire con un flusso nuovo (massimo due tentativi). Per un flusso diretto
  senza pagina sorgente non è possibile rigenerare il link: in quel caso indica
  la pagina che contiene il player.
- Se il player incorporato blocca le richieste automatiche (ad esempio con
  `HTTP 403`, Cloudflare, login o DRM), ViewerLAB non aggira la protezione:
  usa una fonte autorizzata o un flusso diretto lecito.

### Browser integrato
- Il pulsante **🧭** nella barra superiore apre un browser Chromium/WebEngine
  dentro ViewerLAB, con barra degli indirizzi, indietro/avanti, ricarica,
  copia URL e **Apri nel browser** di sistema.
- Da **I miei link**, il pulsante **🌐 Apri pagina** apre il link selezionato
  nel browser integrato; la stessa cosa avviene da **Apri pagina** nei
  risultati online.
- Il motore WebEngine gira in un processo separato basato su **PySide6** e la
  sua finestra viene incorporata nel dialogo. Questo evita i conflitti tra
  QtWebEngine e PyQt6 su Windows. L'utente può usare login, cookie e
  JavaScript del sito restando nell'applicazione.
- Il browser resta sulla stessa pagina e blocca popup, finestre secondarie e
  nuove tab. Non estrae il flusso per VLC e non aggira Cloudflare, CAPTCHA,
  paywall, login o DRM.
- Se il sito non carica nel browser integrato, ViewerLAB mostra un errore
  esplicito (incluso il dettaglio di rete) invece di lasciare il caricamento
  sospeso. Usa **Apri nel browser** per passare a Chrome/Edge/Firefox.

### Libreria film / serie
- La barra laterale divide automaticamente **🎬 FILM** e **📺 SERIE**.
- In alto ci sono i filtri **Tutti / Film / Serie**, la ricerca e il filtro per TAG.
- La classificazione viene dedotta dal nome del file e, quando manca il titolo
  della serie, anche dalla cartella che contiene l'episodio
  (es. `YOU\Stagione 4\S04 01.mp4` → serie `YOU`, stagione 4, episodio 1).
- Ogni file può essere riclassificato manualmente: tasto destro →
  **Dettagli e TAG…** oppure pulsante **🏷 Dettagli / TAG**.

### TAG
- I TAG si aggiungono dal dialogo dettagli oppure con tasto destro →
  **Aggiungi TAG…** (anche su più file selezionati).
- Il menu in alto filtra la libreria per TAG.
- TAG, tipo (film/serie), titolo, serie, stagione ed episodio sono salvati in
  `visto_settings.json` nella sezione `file_meta`, usando il percorso completo
  del file: file omonimi in cartelle diverse non si confondono.
- Lo storico di visione usa anch'esso il percorso completo, mantenendo la
  compatibilità con i dati salvati in precedenza per nome file.

### Copertine di film e serie
- Clicca sulla copertina accanto al titolo della raccolta per aprire il menu:
  **Cerca online (automatico)**, **Cerca online…**, **Scegli file locale…**,
  **Rimuovi copertina**.
- Il pulsante **🖼 Copertina** nell'intestazione cerca subito la copertina
  online in base al nome del film o della serie. Se trova una corrispondenza
  sicura la importa automaticamente.
- La ricerca online è disponibile anche con tasto destro → **Copertina online**
  e nel dialogo **Dettagli e TAG** con **🌐 Cerca online**.
- Se non viene trovato nulla, il dialogo mostra **Copertina non trovata online**
  e permette di modificare il titolo e riprovare.
- Fonti pubbliche senza chiave API: IMDb, TVmaze e iTunes; per i titoli
  italiani o tradotti viene usato anche Wikidata per risalire all'ID IMDb.
- La ricerca e il download avvengono in background: l'interfaccia non si blocca.
  Serve una connessione a Internet. `certifi` mantiene aggiornati i certificati
  SSL su Windows.
- Per una serie la copertina è condivisa da tutti gli episodi; per un film è
  associata al titolo del film.
- Le immagini vengono copiate nella cartella `covers` accanto a
  `visto_settings.json`, così non si perdono se sposti l'originale. Anche
  nell'eseguibile compilato, configurazione e copertine restano accanto al `.exe`.
- La copertina compare nell'intestazione della raccolta e in miniatura nelle
  card dei file. Nel dialogo dettagli la scelta online viene applicata solo
  salvando; annullando non modifica la copertina.
- Si può rimuovere in qualsiasi momento con **Rimuovi copertina**.

### Riproduttore
- Il pulsante **✕** nei controlli chiude il riproduttore e libera spazio per
  selezionare i file.
- La barra compatta che appare al suo posto permette di riaprire il player o di
  riprodurre subito il file selezionato; la posizione di visione viene salvata.

### Interfaccia
- Tema scuro, card con stato di visione, percentuale e TAG.
- Player con play/pausa, stop, ±10 s, volume, mute, velocità (1× → 2× → 0,75×),
  barra di avanzamento e schermo intero.
- Scorciatoie: `Spazio` play/pausa, `Ctrl+←/→` ±10 s, `F` schermo intero,
  `M` mute, `Esc` esci dallo schermo intero, `Ctrl+F` cerca.

## Avvio

Windows 10 o 11. Basta un doppio clic su **`run.bat`**: al primo avvio prepara
tutto da solo, e dai successivi parte in pochi secondi.

- **Python 3.14** (64 bit): lo cerca e, se manca, propone di installarlo con
  `winget` (solo per il tuo utente). Altre versioni non vanno bene: con Python
  3.15 alcune librerie si rompono (`'lazy_import' object is not callable`). Un
  `.venv` creato con un'altra versione viene ricreato.
- **Librerie**: installa le versioni esatte testate (`requirements.txt` +
  `constraints.txt`) e le reinstalla solo quando quei file cambiano.
- **VLC** (obbligatorio, player della Libreria) e **mpv** (consigliato, player
  delle fonti online): se mancano propone di installarli con `winget`.
- Poi avvia ViewerLAB **senza finestra del cmd**. Se l'app si chiude subito
  con un errore, il cmd resta aperto e mostra le ultime righe del log.

```bat
run.bat
```

Altri modi:

```bat
run.bat -Console
setup.bat
```

`-Console` mostra la console con gli errori completi; `setup.bat` prepara
l'ambiente senza avviare l'app. In PowerShell:
`powershell -ExecutionPolicy Bypass -File .\run.ps1`. Tutto il lavoro lo fa
[`tools/bootstrap.ps1`](tools/bootstrap.ps1).

Se il progetto sta in una cartella dal percorso molto lungo (oltre ~70
caratteri), l'ambiente va in `%LOCALAPPDATA%\ViewerLAB\venv` invece che in
`.venv`: alcuni file di PySide6 supererebbero il limite di 260 caratteri di
Windows.

Test (strumenti di sviluppo a parte):

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -c constraints.txt
.venv\Scripts\python.exe -m pytest
```

### Configurazione TMDB e canali

- `channels/` contiene i canali JSON/YAML. Copia
  [`channels/example.json`](channels/example.json), inserisci una fonte
  autorizzata e imposta `"enabled": true`. Dalla finestra online puoi anche
  aprire la cartella o sceglierne un'altra con **⋯ → Scegli cartella canali…**.
- La chiave TMDB è opzionale: senza chiave la ricerca sui canali funziona, ma
  poster, trama e voto non vengono arricchiti. Puoi inserirla dalla GUI oppure
  in un file `.env` (vedi [`.env.example`](.env.example)).
- Dopo aver modificato i canali, usa **⋯ → Ricarica canali** nella finestra di
  ricerca online.

## Struttura

```
main.py              # avvio + dispatch del processo browser
vistoflow/           # finestra unica, IMDb, lingua, fonti online, player mpv
  app.py main_window.py style.py imdb.py i18n.py dialogs.py player*.py
  html_site.py probe.py search.py sources.py models.py config.py selftest.py
  library/           # libreria locale (ex ViewerLAB Pro)
    window.py dialogs.py media_manager.py player_widget.py online_dialog.py
    link_dialog.py browser_dialog.py browser_engine.py cover_fetcher.py theme.py
vistoflow_online/    # motore canali/resolver/TMDB usato dalla libreria
channels/            # canali JSON/YAML dell'utente
sources/             # catalogo demo delle fonti online
bin/                 # metti qui mpv.exe (non versionato)
installer/           # ViewerLAB.wxs: installer .msi (WiX 5)
build.bat            # doppio clic: crea .exe e .msi in dist/
.github/workflows/   # build.yml: .exe e .msi pubblicati nelle Releases
tests/               # pytest
docs/                # ONLINE.md, ARCHITECTURE.md
```

`visto_settings.json` e `covers/` (dati della libreria) restano nella
cartella dell'app e non sono versionati.

## Creare l'eseguibile (.exe) e l'installer (.msi)

### Sul tuo PC

Doppio clic su **`build.bat`** (dopo aver eseguito `setup.bat` almeno una volta).
Crea `dist\ViewerLAB\ViewerLAB.exe` e, se WiX è installato, anche
`dist\ViewerLAB-<versione>.msi`; alla fine apre la cartella `dist`. Per il `.msi`
serve una sola volta:

```bat
winget install Microsoft.DotNet.SDK.8
dotnet tool install --global wix --version 5.0.2
```

A mano: `.venv\Scripts\python.exe build_exe.py --clean --msi` (senza `--msi`
solo l'exe, con `--onefile` un unico `ViewerLAB.exe`). L'installer è descritto
in [`installer/ViewerLAB.wxs`](installer/ViewerLAB.wxs).

### Su GitHub (per il download)

Il workflow [`build.yml`](.github/workflows/build.yml) crea `.exe` e `.msi` su
una macchina Windows di GitHub e li pubblica nella pagina
[Releases](https://github.com/andreagioiaa/ViewerLAB/releases), da cui partono
i link della sezione [Scarica](#scarica).

1. Fai commit e push delle modifiche.
2. Su GitHub apri **Actions → Build eseguibili → Run workflow**. In alternativa
   pubblica un tag: `git tag v0.3.0` e `git push --tags`.
3. Dopo circa 10–15 minuti la release `v<versione>` contiene `ViewerLAB.msi`
   e `ViewerLAB-portable.zip`.

La versione viene da `vistoflow/__init__.py` (`__version__`): aumentala prima
di una nuova release, altrimenti i file della release esistente vengono
sostituiti. I link *latest* puntano sempre all'ultima release pubblicata.

mpv e VLC non sono inclusi negli eseguibili. Il browser integrato riusa lo
stesso `.exe` con `--browser-engine`.
