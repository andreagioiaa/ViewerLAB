"""ViewerLAB — avvio: schermata di benvenuto (Locale / Online)."""

import sys

# Nell'eseguibile PyInstaller il browser integrato riusa lo stesso .exe in un
# processo separato: il dispatch deve avvenire prima di creare la QApplication.
if "--browser-engine" in sys.argv:
    from vistoflow.library.browser_engine import main as _browser_engine_main

    raise SystemExit(_browser_engine_main())

from vistoflow.app import main

if __name__ == "__main__":
    raise SystemExit(main())
