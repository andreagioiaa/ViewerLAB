# Media Center CLI

Media Center modulare in **Python 3.11+** per cercare titoli su canali configurabili, arricchire i risultati con **TMDB**, risolvere flussi video da host compatibili e generare comandi pronti per **VLC**.

Il progetto usa esclusivamente `asyncio` + `httpx` e non esegue JavaScript arbitrario: il decoder integrato interpreta solo il classico *packer* JavaScript (Dean Edwards) usato da alcuni host.

> **Uso legale**: configura solo fonti autorizzate e contenuti leciti. Il progetto non aggira DRM, paywall, autenticazioni o altre protezioni. Il canale incluso è fittizio (`example.invalid`) e i test usano esclusivamente fixture locali.

---

## Caratteristiche

- Canali caricati da file **JSON/YAML** con selettori CSS generici.
- Ricerca parallela su tutti i canali con `asyncio.TaskGroup`, semaforo e timeout per canale.
- Parser HTML basato su **BeautifulSoup** (`lxml` con fallback `html.parser`).
- Pipeline dettaglio → embed → resolver.
- Resolver inclusi:
  - `direct` per URL `.m3u8` / `.mp4`;
  - `mixdrop`, `voe`, `supervideo`, `streamtape` tramite un resolver HTML con supporto packer.
- Decoder Python del packer JavaScript e estrazione di URL HLS/MP4.
- `StreamSource` con **User-Agent** e **Referer** obbligatori.
- Client TMDB v3 asincrono con cache, rate limit, fallback `it-IT` → `en-US` e poster `w500`.
- CLI Typer/Rich con output umano e **JSON**.
- Comandi: `search`, `play`, `resolve`, `channels list`, `doctor`, `clean`.
- Test offline con `pytest`, `pytest-asyncio` e `respx`.

---

## Struttura

```text
media_center/
├── cli/
│   └── main.py                 # CLI Typer
├── core/
│   ├── channels/
│   │   ├── engine.py           # ricerca parallela + dettaglio
│   │   ├── loader.py           # caricamento JSON/YAML
│   │   └── parser.py           # parser CSS generico
│   ├── metadata/
│   │   ├── title_cleaner.py    # clean_title, extract_year, scoring
│   │   └── tmdb.py             # client TMDB v3
│   ├── resolvers/
│   │   ├── base.py             # interfaccia resolver
│   │   ├── html.py             # resolver HTML + unpacker
│   │   ├── js_unpacker.py      # decoder packer
│   │   ├── registry.py         # registro resolver
│   │   ├── engine.py           # risoluzione parallela
│   │   ├── direct.py
│   │   ├── mixdrop.py
│   │   ├── voe.py
│   │   ├── supervideo.py
│   │   └── streamtape.py
│   ├── config.py
│   ├── errors.py
│   ├── http.py
│   ├── logging.py
│   └── models.py
├── channels/
│   └── example.json            # canale fittizio di esempio
├── tests/
├── main.py
├── pyproject.toml
└── .env.example
```

I pacchetti installabili sono `core` e `cli`; il comando console è `media-center`.

---

## Installazione

```powershell
cd C:\Users\Andrea\Desktop\Video_test\media_center
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Su Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copia `.env.example` in `.env` e inserisci la chiave TMDB:

```powershell
Copy-Item .env.example .env
notepad .env
```

```dotenv
TMDB_API_KEY=la_tua_chiave_tmdb_v3
TMDB_LANGUAGE=it-IT
CHANNELS_DIR=channels
HTTP_TIMEOUT=15
CHANNEL_TIMEOUT=20
RESOLVER_TIMEOUT=25
MAX_CONCURRENCY=8
LOG_LEVEL=INFO
```

La chiave TMDB è opzionale: senza chiave la ricerca sui canali funziona, ma i risultati non vengono arricchiti con poster, trama e voto.

---

## Uso della CLI

```powershell
# Ricerca semplice
media-center search "Inception"

# Ricerca con metadati TMDB e risoluzione dei flussi
media-center search "Inception" --resolve --limit 5

# Output JSON, utile per integrazioni
media-center search "Dune" --json --no-metadata

# Cerca una serie TV
media-center search "The Last of Us" --type tv --resolve

# Risolve un singolo host o un flusso diretto
media-center resolve "https://mixdrop.co/e/example"
media-center resolve "https://cdn.example.com/video.m3u8"

# Genera il comando VLC; --launch avvia VLC se è nel PATH
media-center play "Inception" --limit 3
media-center play "Inception" --launch

# Diagnostica senza rete
media-center doctor
media-center channels list
media-center clean "The.Last.of.Us.S01E02.ITA.1080p.WEB-DL.mkv"
```

Se il progetto non è installato in modalità editable, esegui dalla cartella del progetto:

```powershell
python -m cli.main search "Inception"
python main.py doctor
```

---

## Configurazione dei canali

Un canale è un oggetto JSON/YAML. Esempio minimo:

```json
{
  "id": "mio-canale",
  "name": "Mio Canale",
  "domain": "https://www.esempio-autorizzato.org",
  "search_url": "https://www.esempio-autorizzato.org/cerca?q={query}",
  "headers": {
    "Accept-Language": "it-IT,it;q=0.9"
  },
  "selectors": {
    "item_card": "article.result",
    "title": "h2 a",
    "url": "h2 a",
    "cover": "img.poster"
  },
  "detail_selectors": {
    "embed_links": "iframe[src], a.embed-link[href]"
  },
  "enabled": true,
  "priority": 50
}
```

Campi:

| Campo | Obbligatorio | Descrizione |
|---|---:|---|
| `id` | sì | Identificativo univoco. |
| `name` | sì | Nome mostrato nella CLI. |
| `domain` | no | Base per URL relativi. |
| `search_url` | sì | Deve contenere `{query}`. |
| `selectors.item_card` | sì | Contenitore di ogni risultato. |
| `selectors.title` | sì | Titolo, relativo alla card. |
| `selectors.url` | sì | Link, relativo alla card. |
| `selectors.cover` | no | Immagine di copertina. |
| `detail_selectors.embed_links` | no | Selettore per iframe/link embed nella pagina dettaglio. |
| `headers` | no | Header extra per le richieste del canale. |
| `enabled` | no | Default `true`. |
| `priority` | no | Ordinamento, default `100`. |

Senza `detail_selectors.embed_links`, il parser cerca `iframe[src]`, `iframe[data-src]`, `video[src]`, `video source[src]`, `a[data-embed]` e URL `.m3u8`/`.mp4` nel HTML.

I selettori sono generici: il codice non contiene selettori specifici di siti reali.

---

## Aggiungere un resolver

Ogni resolver implementa `BaseResolver` e viene registrato con il decorator:

```python
from core.resolvers.html import HTMLStreamResolver
from core.resolvers.registry import register_resolver


@register_resolver
class MioHostResolver(HTMLStreamResolver):
    name = "miohost"
    priority = 50
    domains = ("miohost.example", "miohost2.example")
```

`HTMLStreamResolver`:

1. scarica la pagina host con `Referer`;
2. prova a decodificare i blocchi packer;
3. cerca URL `.m3u8` / `.mp4`;
4. restituisce uno `StreamSource` con `User-Agent` e `Referer`.

Per host con markup molto diverso si può sovrascrivere `resolve()` e usare `httpx`/BeautifulSoup direttamente. I test devono usare fixture locali e `respx`, non siti reali.

> I markup degli host cambiano frequentemente. I resolver inclusi sono un punto di partenza documentato, non una garanzia di funzionamento permanente.

---

## Modelli principali

- `MediaItem`: titolo, titolo originale, anno, tipo, poster, trama, voto, ID TMDB.
- `SearchResult`: risultato di un canale con `page_url`, copertina e `MediaItem` opzionale.
- `StreamSource`: URL del flusso, header obbligatori, MIME, qualità, resolver.
- `ChannelConfig`: configurazione validata di un canale.
- `SearchReport` / `ResolveReport`: report aggregati con errori per canale/URL.

`StreamSource` rifiuta la creazione se mancano `User-Agent` o `Referer` (confronto case-insensitive).

---

## Pipeline

```text
query
  ↓
ChannelEngine.search_all()       # ricerca parallela sui canali
  ↓
clean_title() + TMDBClient       # metadati e poster
  ↓
ChannelEngine.find_embed_urls()  # pagina dettaglio → iframe/embed
  ↓
ResolverEngine.resolve()         # host → StreamSource
  ↓
CLI: tabella / JSON / comando VLC
```

Il comando VLC generato ha la forma:

```text
vlc --http-user-agent "..." --http-referrer "..." "https://host/video.m3u8"
```

VLC non viene avviato automaticamente, a meno di usare `play --launch`.

---

## Test

```powershell
pytest
```

I test non contattano siti esterni: usano fixture HTML locali e `respx`. Coprono:

- pulizia titoli e estrazione anno;
- parsing ricerca/dettaglio;
- ricerca parallela e isolamento errori;
- decoder packer JavaScript;
- resolver e header obbligatori;
- client TMDB e fallback lingua;
- comandi CLI offline.

---

## Limiti e note

- Il decoder packer supporta la variante classica `eval(function(p,a,c,k,e,d){...})`; non è un interprete JavaScript.
- Alcuni host cambiano dominio o offuscamento: aggiorna `domains` e le fixture quando necessario.
- Non vengono gestiti DRM (Widevine/PlayReady), token paywall o login.
- Le richieste HTTP usano un User-Agent configurabile; rispetta i termini d'uso delle fonti autorizzate.
- La chiave TMDB non viene stampata nei log o nei messaggi d'errore.

---

## Licenza

MIT. Vedi il campo `license` in `pyproject.toml`.
