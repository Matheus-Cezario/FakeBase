"""Interface de linha de comando do FakeBase."""

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
    """Guarda as opções globais e abre a configuração sob demanda."""

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
        """Registra ajustes vindos de um subcomando.

        Se a configuração já tiver sido carregada (como acontece em
        ``start``, que gera antes de servir), aplica direto nas settings.
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
    help="Arquivo de configuração.",
)
@click.option(
    "--storage-path",
    "--fakepath",
    "storagePath",
    default=None,
    help=f"Pasta do banco NoSQL (padrão {DEFAULT_STORAGE_PATH}).",
)
@click.option(
    "--storage",
    type=click.Choice(STORAGE_BACKENDS),
    default=None,
    help="Backend de armazenamento.",
)
@click.option("--seed", type=int, default=None, help="Semente aleatória: mesma semente, mesmos dados.")
@click.option("--locale", default=None, help="Locale dos dados falsos, por exemplo pt_BR ou en_US.")
@click.pass_context
def cli(ctx, config_path, storagePath, storage, seed, locale):
    """Gera bancos de dados falsos e serve tudo por rotas CRUD."""
    ctx.obj = CliState(
        config_path=config_path,
        storagePath=storagePath,
        storage=storage,
        seed=seed,
        locale=locale,
    )


# ---------------------------------------------------------------------------
# Geração
# ---------------------------------------------------------------------------
@cli.command()
@click.option("--only", multiple=True, help="Gera apenas estes bancos (pode repetir).")
@click.option("--export", "export_to", type=click.Path(), default=None, help="Também salva JSONs nesta pasta.")
@click.option("--json", "as_json", is_flag=True, help="Mostra o relatório em JSON.")
@pass_state
def generate(state: CliState, only, export_to, as_json):
    """Gera (ou regenera) os bancos de dados falsos."""
    fakebase = state.fakebase
    report = fakebase.generate(only=list(only) or None)
    if export_to:
        fakebase.export(Path(export_to), only=list(only) or None)
    if as_json:
        click.echo(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(f"Banco NoSQL: {fakebase.storage.path} ({fakebase.storage.backend})")
    if report.seed is not None:
        click.echo(f"Semente: {report.seed}")
    for item in report.databases:
        click.echo(f"  {item.name:<20} {item.size:>6} documentos  (schema: {item.schema})")
        for note in item.notes:
            click.echo(f"      - {note}")
    click.echo(f"Total: {report.total} documentos")
    if export_to:
        click.echo(f"JSON exportado para {export_to}")


@cli.command()
@click.option("--host", default=None, help="Endereço de escuta.")
@click.option("--port", type=int, default=None, help="Porta.")
@click.option("--latency", type=int, default=None, help="Atraso artificial por requisição, em ms.")
@pass_state
def serve(state: CliState, host, port, latency):
    """Sobe a API REST sobre os dados já gerados."""
    state.set(latency=latency, host=host, port=port)
    fakebase = state.fakebase
    _announce(fakebase, host, port)
    from .api import serve as run_server

    run_server(fakebase, host=host, port=port)


@cli.command()
@click.option("--host", default=None, help="Endereço de escuta.")
@click.option("--port", type=int, default=None, help="Porta.")
@click.option("--latency", type=int, default=None, help="Atraso artificial por requisição, em ms.")
@click.pass_context
def start(ctx, host, port, latency):
    """Gera os dados e já sobe a API (equivale a generate + serve)."""
    ctx.invoke(generate)
    ctx.invoke(serve, host=host, port=port, latency=latency)


# ---------------------------------------------------------------------------
# Inspeção
# ---------------------------------------------------------------------------
@cli.command(name="list")
@pass_state
def list_databases(state: CliState):
    """Mostra os bancos e quantos documentos cada um tem."""
    stats = state.fakebase.stats()
    click.echo(f"Banco NoSQL: {stats['storage']['path']} ({stats['storage']['backend']})")
    for item in stats["databases"]:
        marker = " " if item["generated"] else "!"
        click.echo(f" {marker} {item['name']:<20} {item['count']:>6} documentos  (schema: {item['schema']})")
    if stats["orphans"]:
        click.echo(f"Coleções fora da configuração: {', '.join(stats['orphans'])}")
    if any(not item["generated"] for item in stats["databases"]):
        click.echo("(!) Bancos ainda não gerados. Rode 'fakebase generate'.")


@cli.command()
@click.argument("database")
@click.option("-n", "--count", default=1, show_default=True, help="Quantas linhas de exemplo.")
@pass_state
def preview(state: CliState, database, count):
    """Mostra linhas de exemplo de um banco sem gravar nada."""
    documents = state.fakebase.preview(database, count)
    click.echo(json.dumps(documents, ensure_ascii=False, indent=2, default=str))


@cli.command()
@pass_state
def validate(state: CliState):
    """Confere a configuração sem gerar dados."""
    config = state.config
    click.echo(f"Configuração válida: {config.path}")
    click.echo(f"  schematics: {', '.join(sorted(config.schematics))}")
    click.echo(f"  bancos:     {', '.join(config.database_names)}")
    order = FakeBase(config).generation_order()
    click.echo(f"  ordem de geração: {' -> '.join(order)}")


@cli.command()
@click.option("--search", default=None, help="Filtra por parte do nome ou da descrição.")
@click.option("--transforms", is_flag=True, help="Lista os transforms em vez dos geradores.")
@pass_state
def generators(state: CliState, search, transforms):
    """Lista os geradores (ou transforms) disponíveis e seus parâmetros."""
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
        aliases = f"  (também: {', '.join(spec.aliases)})" if spec.aliases else ""
        click.echo(f"  {spec.name:<16} {spec.doc}{aliases}")
        for name, description in spec.params.items():
            click.echo(f"      {name}: {description}")


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
@cli.command(name="export")
@click.argument("target", type=click.Path(), default="./export")
@click.option("--only", multiple=True, help="Exporta apenas estes bancos.")
@pass_state
def export_command(state: CliState, target, only):
    """Salva os bancos em arquivos JSON (formato da versão 1.x)."""
    written = state.fakebase.export(Path(target), only=list(only) or None)
    for path in written:
        click.echo(f"  {path}")
    click.echo(f"{len(written)} arquivo(s) exportado(s).")


@cli.command(name="import")
@click.argument("source", type=click.Path(exists=True))
@click.option("--append", is_flag=True, help="Mantém os documentos já existentes.")
@pass_state
def import_command(state: CliState, source, append):
    """Carrega arquivos JSON para dentro do banco NoSQL."""
    loaded = state.fakebase.import_json(Path(source), replace=not append)
    for name, count in loaded.items():
        click.echo(f"  {name:<20} {count:>6} documentos")
    click.echo(f"Total: {sum(loaded.values())} documentos importados.")


@cli.command()
@click.argument("databases", nargs=-1)
@click.option("--all", "drop_all", is_flag=True, help="Apaga todos os bancos.")
@click.confirmation_option(prompt="Apagar os dados?")
@pass_state
def drop(state: CliState, databases, drop_all):
    """Apaga os dados de um ou mais bancos."""
    fakebase = state.fakebase
    targets: List[str] = list(databases)
    if drop_all:
        targets = fakebase.database_names()
    if not targets:
        raise click.UsageError("Informe ao menos um banco ou use --all.")
    for name in targets:
        fakebase.drop(name)
        click.echo(f"  {name} apagado")


@cli.command()
@click.argument("path", type=click.Path(), default=DEFAULT_CONFIG_PATH)
@click.option("--force", is_flag=True, help="Sobrescreve um arquivo existente.")
def init(path, force):
    """Cria um arquivo de configuração de exemplo."""
    target = Path(path)
    if target.exists() and not force:
        raise click.UsageError(f"{target} já existe. Use --force para sobrescrever.")
    target.write_text(
        json.dumps(example_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    click.echo(f"Configuração criada em {target}")
    click.echo("Próximo passo: fakebase start")


def _announce(fakebase: FakeBase, host: Optional[str], port: Optional[int]) -> None:
    settings = fakebase.settings
    base = f"http://{host or settings.host}:{port or settings.port}"
    click.echo(f"FakeBase {__version__} - {fakebase.storage.backend} em {fakebase.storage.path}")
    click.echo(f"  documentação interativa: {base}/docs")
    for name in fakebase.database_names():
        click.echo(f"  {base}/{name}")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        cli(standalone_mode=False)
    except FakeBaseError as exc:
        click.secho(f"Erro: {exc}", fg="red", err=True)
        sys.exit(1)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.exceptions.Abort:
        click.echo("Cancelado.", err=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
