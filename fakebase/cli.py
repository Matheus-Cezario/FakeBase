"""FakeBase command-line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from . import __version__
from .config import DEFAULT_CONFIG_PATH, DEFAULT_STORAGE_PATH, Config, example_config
from .errors import FakeBaseError
from .generators import available as available_generators
from .manager import FakeBase
from .pipes import available as available_pipes
from .storage import STORAGE_BACKENDS


class CliState:
    """Keep the global options and open the configuration on demand."""

    def __init__(self, **overrides: Any):
        self.config_path: str = overrides.pop("config_path")
        self.overrides: Dict[str, Any] = {k: v for k, v in overrides.items() if v is not None}
        self._config: Optional[Config] = None
        self._fakebase: Optional[FakeBase] = None

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = Config.load(self.config_path, **self.overrides)
        return self._config

    @property
    def fakebase(self) -> FakeBase:
        if self._fakebase is None:
            self._fakebase = FakeBase(self.config)
        return self._fakebase

    def set(self, **overrides: Any) -> None:
        """Record settings coming from a subcommand.

        If the configuration was already loaded (as happens in ``start``,
        which generates before serving), apply them straight to the settings.
        """
        for key, value in overrides.items():
            if value is None:
                continue
            self.overrides[key] = value
            if self._config is not None:
                setattr(self._config.settings, key, value)


pass_state = click.make_pass_decorator(CliState)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="FakeBase")
@click.option(
    "--config",
    "--path",
    "-c",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Configuration file.",
)
@click.option(
    "--storage-path",
    "--fakepath",
    "storagePath",
    default=None,
    help=f"NoSQL database folder (default {DEFAULT_STORAGE_PATH}).",
)
@click.option(
    "--storage",
    type=click.Choice(STORAGE_BACKENDS),
    default=None,
    help="Storage backend.",
)
@click.option("--seed", type=int, default=None, help="Random seed: same seed, same data.")
@click.option("--locale", default=None, help="Locale of the fake data, for example pt_BR or en_US.")
@click.option(
    "--queries",
    "queriesPath",
    default=None,
    help="Custom queries folder (default ./queries, relative to the configuration).",
)
@click.pass_context
def cli(ctx, config_path, storagePath, storage, seed, locale, queriesPath):
    """Generate fake databases and serve them through CRUD routes."""
    ctx.obj = CliState(
        config_path=config_path,
        storagePath=storagePath,
        storage=storage,
        seed=seed,
        locale=locale,
        queriesPath=queriesPath,
    )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
@cli.command()
@click.option("--only", multiple=True, help="Generate only these databases (repeatable).")
@click.option("--export", "export_to", type=click.Path(), default=None, help="Also save JSON files to this folder.")
@click.option("--json", "as_json", is_flag=True, help="Print the report as JSON.")
@pass_state
def generate(state: CliState, only, export_to, as_json):
    """Generate (or regenerate) the fake databases."""
    fakebase = state.fakebase
    report = fakebase.generate(only=list(only) or None)
    if export_to:
        fakebase.export(Path(export_to), only=list(only) or None)
    if as_json:
        click.echo(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(f"NoSQL database: {fakebase.storage.path} ({fakebase.storage.backend})")
    if report.seed is not None:
        click.echo(f"Seed: {report.seed}")
    for item in report.databases:
        click.echo(f"  {item.name:<20} {item.size:>6} documents  (schema: {item.schema})")
        for note in item.notes:
            click.echo(f"      - {note}")
    click.echo(f"Total: {report.total} documents")
    if export_to:
        click.echo(f"JSON exported to {export_to}")


@cli.command()
@click.option("--host", default=None, help="Listen address.")
@click.option("--port", type=int, default=None, help="Port.")
@click.option("--latency", type=int, default=None, help="Artificial delay per request, in ms.")
@pass_state
def serve(state: CliState, host, port, latency):
    """Start the REST API over the already generated data."""
    state.set(latency=latency, host=host, port=port)
    fakebase = state.fakebase
    _announce(fakebase, host, port)
    from .api import serve as run_server

    run_server(fakebase, host=host, port=port)


@cli.command()
@click.option("--host", default=None, help="Listen address.")
@click.option("--port", type=int, default=None, help="Port.")
@click.option("--latency", type=int, default=None, help="Artificial delay per request, in ms.")
@click.pass_context
def start(ctx, host, port, latency):
    """Generate the data and start the API (same as generate + serve)."""
    ctx.invoke(generate)
    ctx.invoke(serve, host=host, port=port, latency=latency)


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------
@cli.command(name="list")
@pass_state
def list_databases(state: CliState):
    """Show the databases and how many documents each one has."""
    stats = state.fakebase.stats()
    click.echo(f"NoSQL database: {stats['storage']['path']} ({stats['storage']['backend']})")
    for item in stats["databases"]:
        marker = " " if item["generated"] else "!"
        click.echo(f" {marker} {item['name']:<20} {item['count']:>6} documents  (schema: {item['schema']})")
    if stats["orphans"]:
        click.echo(f"Collections outside the configuration: {', '.join(stats['orphans'])}")
    if any(not item["generated"] for item in stats["databases"]):
        click.echo("(!) Databases not generated yet. Run 'fakebase generate'.")


@cli.command()
@click.argument("database")
@click.option("-n", "--count", default=1, show_default=True, help="How many sample rows.")
@pass_state
def preview(state: CliState, database, count):
    """Show sample rows of a database without storing anything."""
    documents = state.fakebase.preview(database, count)
    click.echo(json.dumps(documents, ensure_ascii=False, indent=2, default=str))


@cli.command()
@pass_state
def validate(state: CliState):
    """Check the configuration without generating data."""
    config = state.config
    click.echo(f"Valid configuration: {config.path}")
    click.echo(f"  schematics: {', '.join(sorted(config.schematics))}")
    click.echo(f"  databases:  {', '.join(config.database_names)}")
    fakebase = FakeBase(config)
    order = fakebase.generation_order()
    click.echo(f"  generation order: {' -> '.join(order)}")
    click.echo(f"  queries:    {len(fakebase.load_queries())} in {config.queries_dir}")


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Print the queries as JSON.")
@pass_state
def queries(state: CliState, as_json):
    """List the custom queries and the routes they create."""
    endpoints = state.fakebase.load_queries()
    if as_json:
        click.echo(json.dumps([e.describe() for e in endpoints], ensure_ascii=False, indent=2, default=str))
        return
    click.echo(f"Queries folder: {state.config.queries_dir}")
    if not endpoints:
        click.echo("  no queries found (create .sql files in this folder)")
        return
    for endpoint in endpoints:
        params = ", ".join(
            spec.name if spec.required else f"{spec.name}?" for spec in endpoint.params
        )
        click.echo(f"  {endpoint.method:<6} {endpoint.route:<36} {endpoint.relative}")
        if params:
            click.echo(f"         params: {params}")


@cli.command()
@click.option("--search", default=None, help="Filter by part of the name or description.")
@click.option("--transforms", is_flag=True, help="List the transforms instead of the generators.")
@pass_state
def generators(state: CliState, search, transforms):
    """List the available generators (or transforms) and their parameters."""
    if transforms:
        for spec in available_pipes():
            if search and search.lower() not in f"{spec.name} {spec.doc}".lower():
                continue
            click.echo(f"{spec.name:<14} {spec.doc}")
            for name, description in spec.params.items():
                click.echo(f"    {name}: {description}")
        return
    category = None
    for spec in available_generators():
        if search and search.lower() not in f"{spec.name} {spec.doc} {spec.category}".lower():
            continue
        if spec.category != category:
            category = spec.category
            click.echo(f"\n[{category}]")
        aliases = f"  (also: {', '.join(spec.aliases)})" if spec.aliases else ""
        click.echo(f"  {spec.name:<16} {spec.doc}{aliases}")
        for name, description in spec.params.items():
            click.echo(f"      {name}: {description}")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@cli.command(name="export")
@click.argument("target", type=click.Path(), default="./export")
@click.option("--only", multiple=True, help="Export only these databases.")
@pass_state
def export_command(state: CliState, target, only):
    """Save the databases to JSON files (version 1.x format)."""
    written = state.fakebase.export(Path(target), only=list(only) or None)
    for path in written:
        click.echo(f"  {path}")
    click.echo(f"{len(written)} file(s) exported.")


@cli.command(name="import")
@click.argument("source", type=click.Path(exists=True))
@click.option("--append", is_flag=True, help="Keep the existing documents.")
@pass_state
def import_command(state: CliState, source, append):
    """Load JSON files into the NoSQL database."""
    loaded = state.fakebase.import_json(Path(source), replace=not append)
    for name, count in loaded.items():
        click.echo(f"  {name:<20} {count:>6} documents")
    click.echo(f"Total: {sum(loaded.values())} documents imported.")


@cli.command()
@click.argument("databases", nargs=-1)
@click.option("--all", "drop_all", is_flag=True, help="Drop every database.")
@click.confirmation_option(prompt="Delete the data?")
@pass_state
def drop(state: CliState, databases, drop_all):
    """Delete the data of one or more databases."""
    fakebase = state.fakebase
    targets: List[str] = list(databases)
    if drop_all:
        targets = fakebase.database_names()
    if not targets:
        raise click.UsageError("Name at least one database or use --all.")
    for name in targets:
        fakebase.drop(name)
        click.echo(f"  {name} dropped")


@cli.command()
@click.argument("path", type=click.Path(), default=DEFAULT_CONFIG_PATH)
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
def init(path, force):
    """Create an example configuration file."""
    target = Path(path)
    if target.exists() and not force:
        raise click.UsageError(f"{target} already exists. Use --force to overwrite.")
    target.write_text(
        json.dumps(example_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    click.echo(f"Configuration created at {target}")
    click.echo("Next step: fakebase start")


def _announce(fakebase: FakeBase, host: Optional[str], port: Optional[int]) -> None:
    settings = fakebase.settings
    base = f"http://{host or settings.host}:{port or settings.port}"
    click.echo(f"FakeBase {__version__} - {fakebase.storage.backend} at {fakebase.storage.path}")
    click.echo(f"  interactive docs: {base}/docs")
    for name in fakebase.database_names():
        click.echo(f"  {base}/{name}")
    for endpoint in fakebase.load_queries():
        click.echo(f"  {endpoint.method:<6} {base}{endpoint.route}")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        cli(standalone_mode=False)
    except FakeBaseError as exc:
        click.secho(f"Error: {exc}", fg="red", err=True)
        sys.exit(1)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.exceptions.Abort:
        click.echo("Cancelled.", err=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
