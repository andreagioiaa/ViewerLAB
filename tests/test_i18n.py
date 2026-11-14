from vistoflow import i18n
from vistoflow.i18n import _


def test_translation_exact_template_and_nested():
    try:
        i18n.set_language("it")
        assert _("Cerca") == "Cerca"
        i18n.set_language("en")
        assert _("Cerca") == "Search"
        assert _("Fonte aggiunta: Demo") == "Source added: Demo"
        assert _("Verifica non riuscita: La risposta è HTML") == "Check failed: The response is HTML"
        assert _("testo sconosciuto") == "testo sconosciuto"
    finally:
        i18n.set_language("it")
