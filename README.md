# VistoFlow Pro

Libreria locale per film e serie TV con player VLC integrato, copertine,
classificazione manuale, TAG, **ricerca online su canali configurabili** e
**browser WebEngine integrato**.

Tutto è integrato in un'unica applicazione desktop: la ricerca online non è un
servizio separato e non richiede una CLI. La pipeline (canali → metadati TMDB →
resolver → player VLC) gira dentro VistoFlow.

> **Uso legale**: configura solo fonti autorizzate e contenuti leciti. VistoFlow
> non aggira DRM, paywall, login o altre protezioni. Il canale di esempio è
> fittizio e disattivato.

## Novità

### Ricerca online integrata
- Il pulsante **🌐 Online** nella barra superiore apre la ricerca dentro
  VistoFlow.
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
  pagina generica: VistoFlow cerca iframe, tag video e URL HLS/MP4 anche dentro
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
- Se durante la riproduzione VLC rileva un link scaduto, VistoFlow prova
  automaticamente a rileggere la pagina sorgente o il risultato del canale e a
  ripartire con un flusso nuovo (massimo due tentativi). Per un flusso diretto
  senza pagina sorgente non è possibile rigenerare il link: in quel caso indica
  la pagina che contiene il player.
- Se il player incorporato blocca le richieste automatiche (ad esempio con
  `HTTP 403`, Cloudflare, login o DRM), VistoFlow non aggira la protezione:
  usa una fonte autorizzata o un flusso diretto lecito.

### Browser integrato
- Il pulsante **🧭** nella barra superiore apre un browser Chromium/WebEngine
  dentro VistoFlow, con barra degli indirizzi, indietro/avanti, ricarica,
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
- Se il sito non carica nel browser integrato, usa **Apri nel browser** per
  passare a Chrome/Edge/Firefox. Il mancato caricamento non è un errore del
  link salvato.

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

Richiede **Python 3.11+** e VLC installato. La via più semplice è il launcher:
crea `.venv` al primo avvio, installa le dipendenze e usa direttamente
`.venv\Scripts\python.exe`. **Non serve attivare manualmente l'ambiente
virtuale** (né `Activate.bat` né `Activate.ps1`).

```bat
run.bat
```

In PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Per preparare o aggiornare l'ambiente senza avviare l'app:

```bat
setup.bat
```

Equivalente manuale, se preferisci:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Test del motore online e dei resolver:

```bat
.venv\Scripts\python.exe -m pytest
```

Serve VLC installato sul sistema (python-vlc usa la libreria di VLC).

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

- `main.py`, `dialogs.py`, `media_manager.py`, `player_widget.py`: applicazione
  desktop e libreria locale.
- `online_dialog.py`: interfaccia della ricerca online.
- `link_dialog.py`: gestione dei link salvati e aggiornamento dei flussi.
- `browser_dialog.py`: browser incorporato e incorporamento della finestra nativa.
- `browser_engine.py`: processo PySide6/QtWebEngine del browser.
- `async_tasks.py`: lavori asincroni condivisi dalla GUI.
- `vistoflow_online/`: motore integrato (canali, resolver, TMDB, servizio).
- `channels/`: configurazione dei canali dell'utente.
- `media_center/`: prototipo/reference usato durante il porting; l'app non lo
  importa e può essere rimosso senza perdere funzionalità.

## Creazione di eseguibili (.exe)

`build_exe.py` è una GUI separata per PyInstaller:

```bat
python build_exe.py
```

oppure doppio click su `build_exe_gui.bat`.

- **Sorgente**: uno script `.py` oppure una cartella di progetto. Se scegli una
  cartella, il tool trova i file Python e ti fa scegliere il file principale.
- **Output**: cartella dove verrà creato l'eseguibile, nome, icona opzionale.
- Opzioni: file unico, senza console, build pulita, import nascosti, dati
  aggiuntivi (`origine;destinazione`), argomenti extra di PyInstaller.
- Il log di PyInstaller è mostrato in tempo reale, con possibilità di annullare.
- Se PyInstaller non è installato, l'app propone di installarlo.
- Per la ricerca online nell'eseguibile, lascia la cartella `channels/` accanto
  al `.exe` (e, se usi un file `.env`, anche quello). I percorsi dei canali e di
  `.env` vengono risolti rispetto alla cartella dell'eseguibile.
- Per il **browser integrato**, `build_exe.py` rileva `browser_engine.py` e
  aggiunge automaticamente `--hidden-import browser_engine` e
  `--collect-all PySide6`. L'eseguibile riusa sé stesso con
  `--browser-engine` per avviare il motore WebEngine in un processo separato.
  Se usi PyInstaller manualmente, aggiungi quegli stessi parametri.

Installazione manuale di PyInstaller:

```bat
python -m pip install pyinstaller
```
