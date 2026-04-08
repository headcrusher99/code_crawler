"""Code Crawler CLI — Click-based command interface."""

from __future__ import annotations

import logging
import time

import click
from rich.console import Console
from rich.table import Table

from codecrawler import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="codecrawler")
@click.option("--config", "-c", default=".codecrawler.toml", help="Path to config file.")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.pass_context
def main(ctx: click.Context, config: str, verbose: bool) -> None:
    """🕷️ Code Crawler — LLM-first semantic code indexer for massive embedded projects."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


@main.command()
@click.option("--project", "-p", help="Project type (yocto, buildroot, kernel, generic).")
@click.option("--root", "-r", default=".", help="Project root directory.")
@click.option("--image", "-i", help="Target image name (e.g., rdk-b).")
@click.option("--no-native", is_flag=True, help="Disable Rust native acceleration.")
@click.pass_context
def index(
    ctx: click.Context,
    project: str | None,
    root: str,
    image: str | None,
    no_native: bool,
) -> None:
    """Index a project codebase."""
    from codecrawler.core.config import load_config
    from codecrawler.core.event_bus import EventBus
    from codecrawler.core.pipeline import IndexingPipeline
    from codecrawler.core.registry import ServiceRegistry
    from codecrawler.plugins.loader import load_builtin_plugins
    from codecrawler.plugins.registry import PluginRegistry
    from codecrawler.storage.database import Database

    config = load_config(ctx.obj["config_path"], project_type=project, root=root, image=image)

    console.print(f"\n[bold green]🕷️  Code Crawler v{__version__}[/]")
    console.print(f"   Indexing [cyan]{root}[/] (type=[yellow]{config.project.type}[/])\n")

    # Disable native accel if requested
    if no_native:
        import codecrawler.native_accel as _na
        _na._NATIVE_AVAILABLE = False
        console.print("   [dim]Native acceleration disabled[/]\n")

    # Initialize database
    db = Database(config.storage.db_path)
    db.initialize()

    # Initialize plugin system
    event_bus = EventBus()
    service_registry = ServiceRegistry()

    plugins = load_builtin_plugins()
    plugin_registry = PluginRegistry(service_registry, event_bus)
    plugin_registry.register_all(plugins)
    plugin_registry.activate_all()

    console.print(
        f"   Loaded [magenta]{len(plugins)}[/] plugins: "
        f"{', '.join(p.manifest.name for p in plugins)}\n"
    )

    # Run pipeline
    t0 = time.perf_counter()
    pipeline = IndexingPipeline(
        config=config,
        registry=service_registry,
        event_bus=event_bus,
        db_connection=db.connection,
    )
    stats = pipeline.run()
    dt = time.perf_counter() - t0

    # Deactivate plugins
    plugin_registry.deactivate_all()

    # Display results
    _display_results(stats, dt, config.storage.db_path)

    db.close()


def _display_results(stats: dict, total_time: float, db_path: str) -> None:
    """Display indexing results in a rich table."""
    console.print()

    # Stats table
    table = Table(title="📊 Indexing Results", show_edge=False)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Count", style="bold white", justify="right")

    for key in ("files", "functions", "structs", "macros", "variables", "calls", "includes", "directories"):
        value = stats.get(key, 0)
        if value > 0:
            table.add_row(key.capitalize(), f"{value:,}")

    console.print(table)

    # Timing table
    stage_times = stats.get("stage_times", {})
    if stage_times:
        console.print()
        time_table = Table(title="⏱️  Stage Timing", show_edge=False)
        time_table.add_column("Stage", style="cyan", no_wrap=True)
        time_table.add_column("Time", style="bold white", justify="right")

        for stage, dt in stage_times.items():
            if stage == "total":
                continue
            time_table.add_row(stage.replace("_", " ").title(), f"{dt:.3f}s")
        time_table.add_row("─" * 20, "─" * 10, style="dim")
        time_table.add_row("Total", f"{total_time:.3f}s", style="bold green")

        console.print(time_table)

    # Native accel status
    try:
        from codecrawler.native_accel import is_available

        if is_available():
            console.print("\n   [bold green]⚡ Rust native acceleration: active[/]")
        else:
            console.print("\n   [dim]🐍 Running in pure-Python mode (install codecrawler-native for speed)[/]")
    except ImportError:
        console.print("\n   [dim]🐍 Running in pure-Python mode[/]")

    console.print(f"\n   [dim]Database: {db_path}[/]")
    console.print("[bold green]\n   ✅ Indexing complete.[/]\n")


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

    console.print(f"\n[bold]📊 Code Crawler Index Status[/]")
    console.print(f"   [dim]Database: {config.storage.db_path}[/]\n")

    try:
        db.initialize()
        stats = db.get_stats()

        table = Table(show_edge=False)
        table.add_column("Table", style="cyan", no_wrap=True)
        table.add_column("Rows", style="bold white", justify="right")

        total = 0
        for key, value in stats.items():
            table.add_row(key, f"{value:,}")
            total += value

        table.add_row("─" * 20, "─" * 10, style="dim")
        table.add_row("Total", f"{total:,}", style="bold green")

        console.print(table)
    except Exception as e:
        console.print(f"[red]Could not read database: {e}[/]")
    finally:
        db.close()

    console.print()


if __name__ == "__main__":
    main()
