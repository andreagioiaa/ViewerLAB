"""Eccezioni condivise del motore online di VistoFlow."""


class MediaCenterError(Exception):
    """Errore base del Media Center."""


class ChannelError(MediaCenterError):
    """Errore durante caricamento o ricerca di un canale."""


class ChannelConfigError(ChannelError):
    """Configurazione di un canale non valida."""


class ResolverError(MediaCenterError):
    """Errore durante la risoluzione di un flusso."""


class UnsupportedResolver(ResolverError):
    """Nessun resolver disponibile per l'URL richiesto."""


class MetadataError(MediaCenterError):
    """Errore durante il recupero dei metadati TMDB."""
