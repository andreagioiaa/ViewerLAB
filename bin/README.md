# Cartella mpv

Metti qui `mpv.exe` (Windows) o `mpv` (Unix) per farlo trovare
automaticamente a VistoFlow. In alternativa imposta la variabile
d'ambiente `MPV_PATH` oppure usa `--mpv PATH`.

Quando l'app è impacchettata, questa cartella deve stare accanto
all'eseguibile:

```
dist/VistoFlow/
├─ VistoFlow.exe
└─ bin/
   └─ mpv.exe
```

mpv non è incluso nel progetto: scaricalo dal sito ufficiale o dal
pacchetto che preferisci, rispettandone la licenza.
