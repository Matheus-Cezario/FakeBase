"""Leitura e validação do arquivo de configuração (``config.fakebase.json``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .errors import ConfigError
from .schematic import Schematic

SCHEMATICS_KEY = "Schematics"
DATABASE_KEY = "DataBase"
SETTINGS_KEY = "Settings"

KNOWN_KEYS = {SCHEMATICS_KEY, DATABASE_KEY, SETTINGS_KEY}

DEFAULT_CONFIG_PATH = "./config.fakebase.json"
DEFAULT_STORAGE_PATH = "./.fakebase"
DEFAULT_QUERIES_PATH = "./queries"


@dataclass
class Settings:
    """Ajustes globais, vindos da chave ``Settings`` e/ou do CLI."""

    locale: str = "pt_BR"
    seed: Optional[int] = None
    storage: str = "sqlite"
    storagePath: str = DEFAULT_STORAGE_PATH
    database: str = "fakebase"
    idGenerator: str = "objectId"
    minSize: int = 10
    maxSize: int = 50
    host: str = "127.0.0.1"
    port: int = 8080
    cors: bool = True
    latency: int = 0
    queriesPath: str = DEFAULT_QUERIES_PATH
    queriesPrefix: str = "/queries"

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Settings":
        unknown = set(raw) - set(cls.__dataclass_fields__)
        if unknown:
            raise ConfigError(
                f"Settings desconhecido(s): {', '.join(sorted(unknown))}. "
                f"Aceitos: {', '.join(sorted(cls.__dataclass_fields__))}"
            )
        settings = cls(**dict(raw))
        if settings.minSize > settings.maxSize:
            settings.minSize, settings.maxSize = settings.maxSize, settings.minSize
        return settings

    def merge(self, **overrides: Any) -> "Settings":
        """Devolve uma cópia com os valores não nulos de ``overrides``."""
        data = {**self.__dict__}
        for key, value in overrides.items():
            if value is None:
                continue
            if key not in data:
                raise ConfigError(f"Ajuste desconhecido: {key}")
            data[key] = value
        return Settings(**data)


@dataclass
class DatabaseSpec:
    """Um banco de dados a ser gerado."""

    name: str
    schema: str
    size: Optional[int] = None
    size_range: Optional[Tuple[int, int]] = None

    @classmethod
    def parse(cls, name: str, raw: Union[str, Mapping[str, Any]]) -> "DatabaseSpec":
        if isinstance(raw, str):
            return cls(name=name, schema=raw)
        if not isinstance(raw, dict):
            raise ConfigError(
                f"DataBase '{name}': esperado o nome de um schematic ou um objeto"
            )
        if "schema" not in raw:
            raise ConfigError(f"DataBase '{name}': campo 'schema' é obrigatório")
        unknown = set(raw) - {"schema", "size"}
        if unknown:
            raise ConfigError(
                f"DataBase '{name}': chave(s) inválida(s) {', '.join(sorted(unknown))}"
            )
        size = raw.get("size")
        if isinstance(size, (list, tuple)):
            if len(size) != 2:
                raise ConfigError(
                    f"DataBase '{name}': 'size' em lista precisa ter dois números [min, max]"
                )
            low, high = int(size[0]), int(size[1])
            return cls(name=name, schema=raw["schema"], size_range=(min(low, high), max(low, high)))
        if size is not None:
            try:
                size = int(size)
            except (TypeError, ValueError):
                raise ConfigError(f"DataBase '{name}': 'size' precisa ser um número")
            if size < 0:
                raise ConfigError(f"DataBase '{name}': 'size' não pode ser negativo")
        return cls(name=name, schema=raw["schema"], size=size)


@dataclass
class Config:
    """Configuração completa já validada."""

    path: Path
    base_dir: Path
    settings: Settings
    schematics: Dict[str, Schematic] = field(default_factory=dict)
    databases: List[DatabaseSpec] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Union[str, Path], **overrides: Any) -> "Config":
        config_path = Path(path)
        if not config_path.is_file():
            raise ConfigError(f"Arquivo de configuração não encontrado: {config_path}")
        if config_path.stat().st_size == 0:
            raise ConfigError(f"Arquivo de configuração vazio: {config_path}")
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"JSON inválido em {config_path}: {exc}") from exc
        return cls.from_dict(raw, path=config_path, **overrides)

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, Any], path: Union[str, Path] = DEFAULT_CONFIG_PATH, **overrides: Any
    ) -> "Config":
        if not isinstance(raw, dict):
            raise ConfigError("A configuração precisa ser um objeto JSON")
        unknown = set(raw) - KNOWN_KEYS
        if unknown:
            raise ConfigError(
                f"Chave(s) desconhecida(s) na configuração: {', '.join(sorted(unknown))}. "
                f"Esperado: {', '.join(sorted(KNOWN_KEYS))}"
            )
        if SCHEMATICS_KEY not in raw:
            raise ConfigError(f"A configuração precisa da chave '{SCHEMATICS_KEY}'")
        if DATABASE_KEY not in raw:
            raise ConfigError(f"A configuração precisa da chave '{DATABASE_KEY}'")

        config_path = Path(path)
        base_dir = config_path.parent if config_path.parent != Path("") else Path(".")
        settings = Settings.parse(raw.get(SETTINGS_KEY, {})).merge(**overrides)

        raw_schematics = raw[SCHEMATICS_KEY]
        if not isinstance(raw_schematics, dict) or not raw_schematics:
            raise ConfigError(f"'{SCHEMATICS_KEY}' precisa ser um objeto com ao menos um schematic")

        schematics: Dict[str, Schematic] = {}
        for name, fields in raw_schematics.items():
            if not isinstance(fields, dict):
                raise ConfigError(f"Schematic '{name}' precisa ser um objeto de campos")
            schematics[name] = Schematic(name, _with_id(fields, settings.idGenerator))

        raw_databases = raw[DATABASE_KEY]
        if not isinstance(raw_databases, dict) or not raw_databases:
            raise ConfigError(f"'{DATABASE_KEY}' precisa ser um objeto com ao menos um banco")

        databases = [DatabaseSpec.parse(name, value) for name, value in raw_databases.items()]
        known = set(schematics)
        for spec in databases:
            if spec.schema not in known:
                raise ConfigError(
                    f"DataBase '{spec.name}' usa o schematic '{spec.schema}', que não existe. "
                    f"Schematics disponíveis: {', '.join(sorted(known))}"
                )

        config = cls(
            path=config_path,
            base_dir=base_dir,
            settings=settings,
            schematics=schematics,
            databases=databases,
            raw=dict(raw),
        )
        config.validate_references()
        return config

    # ------------------------------------------------------------------
    @property
    def database_names(self) -> List[str]:
        return [spec.name for spec in self.databases]

    def database(self, name: str) -> Optional[DatabaseSpec]:
        for spec in self.databases:
            if spec.name == name:
                return spec
        return None

    def schematic_for(self, name: str) -> Schematic:
        spec = self.database(name)
        if spec is None:
            raise ConfigError(f"Banco '{name}' não existe na configuração")
        return self.schematics[spec.schema]

    def validate_references(self) -> None:
        """Confere se toda referência ``@banco:...@`` aponta para um banco real."""
        from .references import parse_reference  # import tardio evita ciclo

        known = set(self.database_names)
        for spec in self.databases:
            schematic = self.schematics[spec.schema]
            for raw_ref in schematic.references():
                reference = parse_reference(raw_ref)
                if reference.database not in known:
                    raise ConfigError(
                        f"Schematic '{schematic.name}' referencia o banco "
                        f"'{reference.database}', que não existe. "
                        f"Bancos disponíveis: {', '.join(sorted(known))}"
                    )

    @property
    def queries_dir(self) -> Path:
        """Pasta das queries customizadas (relativa ao arquivo de configuração)."""
        folder = Path(self.settings.queriesPath)
        return folder if folder.is_absolute() else self.base_dir / folder

    def describe(self) -> Dict[str, Any]:
        return {
            "config": str(self.path),
            "settings": dict(self.settings.__dict__),
            "databases": [
                {
                    "name": spec.name,
                    "schema": spec.schema,
                    "size": spec.size,
                    "sizeRange": list(spec.size_range) if spec.size_range else None,
                }
                for spec in self.databases
            ],
            "schematics": {name: s.describe() for name, s in self.schematics.items()},
        }


def _with_id(fields: Mapping[str, Any], id_generator: str) -> Dict[str, Any]:
    """Garante que todo schematic tenha um ``_id`` único.

    O ``_id`` gerado automaticamente nasce com ``unique``: além de evitar
    repetições dentro do mesmo lote, isso faz o FakeBase carregar os ids já
    gravados antes de acrescentar documentos a um banco existente.
    """
    if "_id" in fields:
        return dict(fields)
    return {"_id": {"method": id_generator, "unique": True}, **dict(fields)}


def example_config() -> Dict[str, Any]:
    """Configuração de exemplo usada por ``fakebase init``."""
    return {
        "Settings": {"locale": "pt_BR", "seed": 42},
        "Schematics": {
            "user": {
                "name": {"method": "humanName", "gender": "__gender"},
                "gender": {"method": "choice", "data": ["male", "female"]},
                "email": {"method": "email", "name": "__name", "unique": True},
                "age": {"method": "integer", "start": 18, "stop": 80},
                "active": {"method": "boolean", "chance": 0.8},
                "createdAt": {"method": "isoDate", "dateType": "past", "dataRange": 2},
            },
            "product": {
                "name": {"method": "words", "count": 2, "transform": "title"},
                "price": {"method": "number", "start": 10, "stop": 500, "precision": 2},
                "stock": {"method": "integer", "start": 0, "stop": 100},
            },
        },
        "DataBase": {
            "users": {"schema": "user", "size": 20},
            "products": {"schema": "product", "size": 15},
        },
    }
