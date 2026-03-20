"""Code Crawler CLI — Click-based command interface."""

from __future__ import annotations

import click
from rich.console import Console

from codecrawler import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="codecrawler")
@click.option("--config", "-c", default=".codecrawler.toml", help="Path to config file.")
@click.pass_context
def main(ctx: click.Context, config: str) -> None:
    """🕷️ Code Crawler — LLM-first semantic code indexer for massive embedded projects."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@main.command()
@click.option("--project", "-p", help="Project type (yocto, buildroot, kernel, generic).")
@click.option("--root", "-r", default=".", help="Project root directory.")
@click.option("--image", "-i", help="Target image name (e.g., rdk-b).")
@click.pass_context
def index(ctx: click.Context, project: str | None, root: str, image: str | None) -> None:
    """Index a project codebase."""
    from codecrawler.core.config import load_config
    from codecrawler.core.pipeline import IndexingPipeline
    from codecrawler.core.registry import ServiceRegistry

    config = load_config(ctx.obj["config_path"], project_type=project, root=root, image=image)
    registry = ServiceRegistry()
    pipeline = IndexingPipeline(config=config, registry=registry)
    console.print(f"[bold green]🕷️ Indexing[/] {root} (type={config.project.type})")
    pipeline.run()
    console.print("[bold green]✅ Indexing complete.[/]")


@main.command()
@click.option("--host", default="localhost", help="MCP server host.")
@click.option("--port", default=3000, help="MCP server port.")
@click.pass_context
def mcp(ctx: click.Context, host: str, port: int) -> None:
    """Start the MCP (Model Context Protocol) server."""
    console.print(f"[bold cyan]🔌 Starting MCP server[/] on {host}:{port}")
    from codecrawler.mcp.server import start_mcp_server

    start_mcp_server(host=host, port=port, config_path=ctx.obj["config_path"])


@main.command()
@click.option("--host", default="localhost", help="UI server host.")
@click.option("--port", default=8080, help="UI server port.")
def ui(host: str, port: int) -> None:
    """Start the Code Nebula 3D dashboard."""
    console.print(f"[bold magenta]🌌 Starting Code Nebula UI[/] on http://{host}:{port}")
    console.print("[yellow]⚠️  Code Nebula UI is planned for v5.[/]")


@main.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Start real-time incremental indexing daemon."""
    console.print("[bold blue]👁️  Watching for changes...[/]")
    console.print("[yellow]⚠️  File watcher daemon is planned for v5.[/]")


@main.command()
@click.pass_context
def sync(ctx: click.Context) -> None:
    """Swarm sync with team master database."""
    console.print("[bold yellow]🔄 Syncing with team master DB...[/]")
    console.print("[yellow]⚠️  Swarm sync is planned for v5.[/]")


@main.command(name="ingest-logs")
@click.argument("log_files", nargs=-1, type=click.Path(exists=True))
@click.pass_context
def ingest_logs(ctx: click.Context, log_files: tuple[str, ...]) -> None:
    """Ingest fleet crash logs and serial traces."""
    if not log_files:
        console.print("[red]No log files specified.[/]")
        return
    console.print(f"[bold]📋 Ingesting {len(log_files)} log file(s)...[/]")
    console.print("[yellow]⚠️  Log ingestion is planned for v5.[/]")


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show index statistics."""
    from codecrawler.core.config import load_config
    from codecrawler.storage.database import Database

    config = load_config(ctx.obj["config_path"])
    db = Database(config.storage.db_path)

    console.print("[bold]📊 Code Crawler Index Status[/]\n")
    stats = db.get_stats()
    for key, value in stats.items():
        console.print(f"  {key}: [cyan]{value}[/]")


if __name__ == "__main__":
    main()
