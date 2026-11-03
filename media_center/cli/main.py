"""CLI Typer/Rich del Media Center."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from core.channels import ChannelEngine, load_channels_with_errors
from core.config import load_settings
from core.errors import MediaCenterError
from core.http import create_client
from core.logging import configure_logging
from core.metadata import clean_title, extract_year
from core.metadata.tmdb import TMDBClient
from core.models import StreamSource
from core.resolvers import ResolverEngine, supported_domains

app = typer.Typer(
    help="Media Center: ricerca canali, metadati TMDB e flussi pronti per VLC.",
    no_args_is_help=True,
    add_completion=False,
)
channels_app = typer.Typer(help="Gestione dei canali configurati.")
app.add_typer(channels_app, name="channels")

console = Console()
error_console = Console(stderr=True)


def _header(stream: StreamSource, name: str) -> str | None:
    for key, value in stream.headers.items():
        if key.lower() == name.lower():
            return value
    return None


def build_vlc_args(stream: StreamSource) -> list[str]:
    """Costruisce gli argomenti VLC con UA e Referer del flusso."""

    args = ["vlc"]
    user_agent = _header(stream, "user-agent")
    referer = _header(stream, "referer")
    if user_agent:
        args.extend(["--http-user-agent", user_agent])
    if referer:
        args.extend(["--http-referrer", referer])
    args.append(stream.url)
    return args


def format_command(args: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def _media_title(result: dict[str, Any]) -> str:
    media_item = result.get("media_item")
    if isinstance(media_item, dict):
        return str(media_item.get("title") or result.get("title") or "?")
    if media_item is not None:
        return str(getattr(media_item, "title", None) or result.get("title") or "?")
    return str(result.get("title") or "?")


def _validate_media_type(value: str) -> str:
    normalized = value.lower().strip()
    if normalized not in {"auto", "movie", "tv"}:
        raise typer.BadParameter("Scegli tra: auto, movie, tv")
    return normalized


async def collect_data(
    query: str,
    *,
    media_type: str = "auto",
    resolve: bool = False,
    limit: int = 10,
    channels_dir: Path | None = None,
    use_metadata: bool = True,
    year: int | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Esegue la pipeline completa e restituisce un payload serializzabile."""

    settings = load_settings(channels_dir)
    configure_logging("DEBUG" if verbose else settings.log_level)
    media_type = _validate_media_type(media_type)
    warnings: list[str] = []
    errors: dict[str, str] = {}
    results_payload: list[dict[str, Any]] = []
    streams_payload: list[dict[str, Any]] = []

    async with create_client(settings) as client:
        async with ChannelEngine(settings, client=client) as channel_engine:
            errors.update(channel_engine.load_errors)
            report = await channel_engine.search_all(query, media_type)
            errors.update(report.errors)
            selected = report.results[: max(1, limit)]

            if use_metadata:
                if settings.tmdb_api_key:
                    tmdb = TMDBClient(
                        settings.tmdb_api_key,
                        client,
                        language=settings.tmdb_language,
                        timeout=settings.request_timeout,
                    )
                    for result in selected:
                        try:
                            item = await tmdb.search(
                                result.title,
                                media_type,
                                year=year,
                            )
                            result.media_item = item
                            if item and item.poster_url:
                                result.cover_url = item.poster_url
                        except MediaCenterError as exc:
                            errors[f"tmdb:{result.channel_id}:{result.title}"] = str(exc)
                else:
                    warnings.append(
                        "TMDB_API_KEY non configurata: i risultati restano senza metadati."
                    )

            results_payload = [result.model_dump(mode="json") for result in selected]

            if resolve:
                resolver_engine = ResolverEngine(
                    client,
                    timeout=settings.resolver_timeout,
                    concurrency=settings.concurrency,
                )
                for result in selected:
                    candidates: list[str] = []
                    try:
                        candidates = await channel_engine.find_embed_urls(result)
                    except MediaCenterError as exc:
                        errors[f"detail:{result.page_url}"] = str(exc)
                    except Exception as exc:  # pragma: no cover - difensivo
                        errors[f"detail:{result.page_url}"] = str(exc)

                    if not candidates and resolver_engine.can_handle(result.page_url):
                        candidates = [result.page_url]

                    for candidate in candidates:
                        try:
                            stream = await resolver_engine.resolve(
                                candidate,
                                referer=result.page_url,
                            )
                        except Exception as exc:
                            errors[candidate] = str(exc) or type(exc).__name__
                            continue
                        entry = stream.model_dump(mode="json")
                        entry["vlc_args"] = build_vlc_args(stream)
                        entry["vlc_command"] = format_command(entry["vlc_args"])
                        entry["media_title"] = _media_title(
                            {"media_item": result.media_item, "title": result.title}
                        )
                        entry["channel_name"] = result.channel_name
                        entry["source_page_url"] = result.page_url
                        streams_payload.append(entry)

    return {
        "query": query,
        "media_type": media_type,
        "channels": len(channel_engine.channels),
        "results": results_payload,
        "streams": streams_payload,
        "errors": errors,
        "warnings": warnings,
    }


def emit_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    results = payload.get("results", [])
    if results:
        table = Table(title=f"Risultati per: {payload.get('query', '')}")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Canale", style="cyan")
        table.add_column("Titolo", style="bold")
        table.add_column("Anno", justify="center")
        table.add_column("Voto", justify="center")
        table.add_column("Pagina")
        for index, result in enumerate(results, start=1):
            media_item = result.get("media_item") or {}
            table.add_row(
                str(index),
                escape(str(result.get("channel_name", ""))),
                escape(_media_title(result)),
                str(media_item.get("year") or ""),
                f"{media_item['rating']:.1f}" if media_item.get("rating") else "",
                escape(str(result.get("page_url", ""))),
            )
        console.print(table)
    else:
        console.print("[yellow]Nessun risultato trovato.[/yellow]")

    streams = payload.get("streams", [])
    if streams:
        stream_table = Table(title="Flussi risolti")
        stream_table.add_column("Titolo", style="bold")
        stream_table.add_column("Host", style="cyan")
        stream_table.add_column("Tipo")
        stream_table.add_column("URL")
        for stream in streams:
            stream_table.add_row(
                escape(str(stream.get("media_title", ""))),
                escape(str(stream.get("resolver_name", ""))),
                escape(str(stream.get("mime_type") or "")),
                escape(str(stream.get("url", ""))),
            )
        console.print(stream_table)
        console.print("\n[bold]Comandi VLC[/bold]")
        for stream in streams:
            console.print(escape(str(stream.get("vlc_command", ""))))

    warnings = payload.get("warnings") or []
    for warning in warnings:
        error_console.print(f"[yellow]Avviso:[/yellow] {escape(str(warning))}")
    errors = payload.get("errors") or {}
    for key, message in errors.items():
        error_console.print(f"[red]Errore[/red] {escape(str(key))}: {escape(str(message))}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Titolo o parola chiave da cercare."),
    media_type: str = typer.Option("auto", "--type", "-t", help="auto, movie o tv."),
    resolve: bool = typer.Option(
        False,
        "--resolve/--no-resolve",
        help="Risolvi anche i flussi video dagli embed.",
    ),
    limit: int = typer.Option(10, "--limit", "-n", min=1, help="Numero massimo di risultati."),
    as_json: bool = typer.Option(False, "--json", help="Output JSON machine-readable."),
    metadata: bool = typer.Option(
        True,
        "--metadata/--no-metadata",
        help="Arricchisci i risultati con TMDB.",
    ),
    year: int | None = typer.Option(None, "--year", help="Anno da passare a TMDB."),
    channels_dir: Path | None = typer.Option(None, "--channels-dir", help="Cartella canali."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Cerca un titolo sui canali configurati e, opzionalmente, risolve i flussi."""

    _validate_media_type(media_type)
    try:
        payload = asyncio.run(
            collect_data(
                query,
                media_type=media_type,
                resolve=resolve,
                limit=limit,
                channels_dir=channels_dir,
                use_metadata=metadata,
                year=year,
                verbose=verbose,
            )
        )
    except MediaCenterError as exc:
        error_console.print(f"[red]Errore:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc
    emit_payload(payload, as_json=as_json)


@app.command()
def play(
    query: str = typer.Argument(..., help="Titolo o parola chiave da cercare."),
    media_type: str = typer.Option("auto", "--type", "-t"),
    limit: int = typer.Option(5, "--limit", "-n", min=1),
    launch: bool = typer.Option(False, "--launch", help="Avvia VLC sul primo flusso."),
    as_json: bool = typer.Option(False, "--json"),
    metadata: bool = typer.Option(True, "--metadata/--no-metadata"),
    channels_dir: Path | None = typer.Option(None, "--channels-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Cerca, risolve e stampa (o avvia) il comando VLC."""

    _validate_media_type(media_type)
    try:
        payload = asyncio.run(
            collect_data(
                query,
                media_type=media_type,
                resolve=True,
                limit=limit,
                channels_dir=channels_dir,
                use_metadata=metadata,
                verbose=verbose,
            )
        )
    except MediaCenterError as exc:
        error_console.print(f"[red]Errore:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc
    emit_payload(payload, as_json=as_json)

    streams = payload.get("streams") or []
    if not streams:
        error_console.print("[red]Nessun flusso risolto.[/red]")
        raise typer.Exit(code=1)
    if launch:
        args = streams[0].get("vlc_args") or []
        if not args:
            raise typer.Exit(code=1)
        if shutil.which("vlc") is None:
            error_console.print("[red]VLC non trovato nel PATH.[/red]")
            raise typer.Exit(code=1)
        subprocess.run(args, check=False)


@app.command("resolve")
def resolve_command(
    url: str = typer.Argument(..., help="URL pagina host o flusso diretto."),
    referer: str | None = typer.Option(None, "--referer", help="Referer da usare."),
    as_json: bool = typer.Option(False, "--json"),
    channels_dir: Path | None = typer.Option(None, "--channels-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Risolve un singolo URL e stampa URL, header e comando VLC."""

    settings = load_settings(channels_dir)
    configure_logging("DEBUG" if verbose else settings.log_level)

    async def _run() -> StreamSource:
        async with create_client(settings) as client:
            engine = ResolverEngine(client, timeout=settings.resolver_timeout)
            return await engine.resolve(url, referer=referer)

    try:
        stream = asyncio.run(_run())
    except MediaCenterError as exc:
        error_console.print(f"[red]Errore:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    args = build_vlc_args(stream)
    payload = stream.model_dump(mode="json")
    payload["vlc_args"] = args
    payload["vlc_command"] = format_command(args)
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    console.print_json(json.dumps(payload, ensure_ascii=False))


@channels_app.command("list")
def channels_list(
    channels_dir: Path | None = typer.Option(None, "--channels-dir", help="Cartella canali."),
    as_json: bool = typer.Option(False, "--json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Elenca i canali caricati e gli eventuali errori di configurazione."""

    settings = load_settings(channels_dir)
    configure_logging("DEBUG" if verbose else settings.log_level)
    channels, errors = load_channels_with_errors(settings.channels_dir)
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "channels": [channel.model_dump(mode="json") for channel in channels],
                    "errors": errors,
                    "directory": str(settings.channels_dir),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    table = Table(title=f"Canali in {settings.channels_dir}")
    table.add_column("ID", style="cyan")
    table.add_column("Nome", style="bold")
    table.add_column("Dominio")
    table.add_column("Attivo", justify="center")
    table.add_column("Priorità", justify="right")
    for channel in channels:
        table.add_row(
            escape(channel.id),
            escape(channel.name),
            escape(channel.domain or ""),
            "sì" if channel.enabled else "no",
            str(channel.priority),
        )
    console.print(table)
    for name, message in errors.items():
        error_console.print(f"[red]Errore[/red] {escape(name)}: {escape(message)}")


@app.command()
def doctor(
    channels_dir: Path | None = typer.Option(None, "--channels-dir", help="Cartella canali."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Controlla configurazione, dipendenze e resolver disponibili (senza rete)."""

    settings = load_settings(channels_dir)
    channels, errors = load_channels_with_errors(settings.channels_dir)
    versions: dict[str, str] = {}
    for package in ("httpx", "beautifulsoup4", "pydantic", "typer", "rich", "tenacity"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "non installato"

    payload: dict[str, Any] = {
        "python": sys.version.split()[0],
        "channels_dir": str(settings.channels_dir),
        "channels_found": len(channels),
        "enabled_channels": sum(1 for channel in channels if channel.enabled),
        "channel_errors": errors,
        "tmdb_configured": bool(settings.tmdb_api_key),
        "tmdb_language": settings.tmdb_language,
        "resolvers": supported_domains(),
        "versions": versions,
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="Doctor Media Center")
    table.add_column("Voce", style="cyan")
    table.add_column("Valore")
    table.add_row("Python", escape(payload["python"]))
    table.add_row("Cartella canali", escape(payload["channels_dir"]))
    table.add_row("Canali trovati", str(payload["channels_found"]))
    table.add_row("Canali attivi", str(payload["enabled_channels"]))
    table.add_row("TMDB configurato", "sì" if payload["tmdb_configured"] else "no")
    table.add_row("Lingua TMDB", escape(payload["tmdb_language"]))
    table.add_row("Resolver", escape(", ".join(payload["resolvers"].keys())))
    for package, version in versions.items():
        table.add_row(f"Versione {package}", escape(version))
    console.print(table)
    for name, message in errors.items():
        error_console.print(f"[red]Errore canale[/red] {escape(name)}: {escape(message)}")


@app.command("clean")
def clean_title_command(title: str = typer.Argument(...)) -> None:
    """Mostra la pulizia di un titolo e l'anno estratto (utile per debug)."""

    typer.echo(f"Pulito: {clean_title(title)}")
    typer.echo(f"Anno: {extract_year(title) or '-'}")


def main() -> None:
    """Entry point per console_script e `python main.py`."""

    app()


if __name__ == "__main__":
    main()
