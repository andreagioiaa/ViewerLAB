# Canali della ricerca online

VistoFlow Pro carica automaticamente tutti i file `.json`, `.yaml` e `.yml`
presenti in questa cartella. Ogni file descrive un canale autorizzato con
selettori CSS generici: non è necessario modificare il codice dell'app.

Il file `example.json` è **disattivato** di proposito: punta a un dominio
fittizio (`example.invalid`). Copialo, rinominalo e attivalo solo dopo aver
inserito una fonte che hai il diritto di usare.

## Esempio minimo

```json
{
  "id": "mia-fonte",
  "name": "Mia fonte autorizzata",
  "domain": "https://www.esempio-autorizzato.org",
  "search_url": "https://www.esempio-autorizzato.org/cerca?q={query}",
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
| `name` | sì | Nome mostrato nella ricerca. |
| `domain` | no | Base per gli URL relativi. |
| `search_url` | sì | Deve contenere `{query}`. |
| `selectors.item_card` | sì | Contenitore di ogni risultato. |
| `selectors.title` | sì | Titolo, relativo alla card. |
| `selectors.url` | sì | Link, relativo alla card. |
| `selectors.cover` | no | Immagine di copertina. |
| `detail_selectors.embed_links` | no | Selettore per iframe/link embed nella pagina dettaglio. |
| `headers` | no | Header extra per le richieste del canale. |
| `enabled` | no | Default `true`. |
| `priority` | no | Ordinamento, default `100`. |

Dopo aver modificato un file, usa **⋯ → Ricarica canali** nella finestra di
ricerca online.

## Limiti

- Sono supportati solo contenuti leciti e fonti che autorizzano l'accesso.
- Non vengono aggirati DRM (Widevine/PlayReady), paywall, login o altre
  protezioni.
- I markup dei siti cambiano: aggiorna i selettori quando necessario.
- I resolver inclusi (`direct`, `mixdrop`, `voe`, `supervideo`, `streamtape`)
  sono un punto di partenza e non una garanzia di funzionamento permanente.
