"""Loading and validation of the configuration file (``config.fakebase.json``)."""

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
    """Global settings, from the ``Settings`` key and/or the CLI."""

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
                f"Unknown setting(s): {', '.join(sorted(unknown))}. "
                f"Accepted: {', '.join(sorted(cls.__dataclass_fields__))}"
            )
        settings = cls(**dict(raw))
        if settings.minSize > settings.maxSize:
            settings.minSize, settings.maxSize = settings.maxSize, settings.minSize
        return settings

    def merge(self, **overrides: Any) -> "Settings":
        """Return a copy with the non-null values of ``overrides``."""
        data = {**self.__dict__}
        for key, value in overrides.items():
            if value is None:
                continue
            if key not in data:
                raise ConfigError(f"Unknown setting: {key}")
            data[key] = value
        return Settings(**data)


@dataclass
class DatabaseSpec:
    """A database to be generated."""

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
                f"DataBase '{name}': expected a schematic name or an object"
            )
        if "schema" not in raw:
            raise ConfigError(f"DataBase '{name}': field 'schema' is required")
        unknown = set(raw) - {"schema", "size"}
        if unknown:
            raise ConfigError(
                f"DataBase '{name}': invalid key(s) {', '.join(sorted(unknown))}"
            )
        size = raw.get("size")
        if isinstance(size, (list, tuple)):
            if len(size) != 2:
                raise ConfigError(
                    f"DataBase '{name}': 'size' as a list needs two numbers [min, max]"
                )
            low, high = int(size[0]), int(size[1])
            return cls(name=name, schema=raw["schema"], size_range=(min(low, high), max(low, high)))
        if size is not None:
            try:
                size = int(size)
            except (TypeError, ValueError):
                raise ConfigError(f"DataBase '{name}': 'size' must be a number")
            if size < 0:
                raise ConfigError(f"DataBase '{name}': 'size' cannot be negative")
        return cls(name=name, schema=raw["schema"], size=size)


@dataclass
class Config:
    """Complete, already validated configuration."""

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
            raise ConfigError(f"Configuration file not found: {config_path}")
        if config_path.stat().st_size == 0:
            raise ConfigError(f"Empty configuration file: {config_path}")
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in {config_path}: {exc}") from exc
        return cls.from_dict(raw, path=config_path, **overrides)

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, Any], path: Union[str, Path] = DEFAULT_CONFIG_PATH, **overrides: Any
    ) -> "Config":
        if not isinstance(raw, dict):
            raise ConfigError("The configuration must be a JSON object")
        unknown = set(raw) - KNOWN_KEYS
        if unknown:
            raise ConfigError(
                f"Unknown key(s) in the configuration: {', '.join(sorted(unknown))}. "
                f"Expected: {', '.join(sorted(KNOWN_KEYS))}"
            )
        if SCHEMATICS_KEY not in raw:
            raise ConfigError(f"The configuration needs the '{SCHEMATICS_KEY}' key")
        if DATABASE_KEY not in raw:
            raise ConfigError(f"The configuration needs the '{DATABASE_KEY}' key")

        config_path = Path(path)
        base_dir = config_path.parent if config_path.parent != Path("") else Path(".")
        settings = Settings.parse(raw.get(SETTINGS_KEY, {})).merge(**overrides)

        raw_schematics = raw[SCHEMATICS_KEY]
        if not isinstance(raw_schematics, dict) or not raw_schematics:
            raise ConfigError(f"'{SCHEMATICS_KEY}' must be an object with at least one schematic")

        schematics: Dict[str, Schematic] = {}
        for name, fields in raw_schematics.items():
            if not isinstance(fields, dict):
                raise ConfigError(f"Schematic '{name}' must be an object of fields")
            schematics[name] = Schematic(name, _with_id(fields, settings.idGenerator))

        raw_databases = raw[DATABASE_KEY]
        if not isinstance(raw_databases, dict) or not raw_databases:
            raise ConfigError(f"'{DATABASE_KEY}' must be an object with at least one database")

        databases = [DatabaseSpec.parse(name, value) for name, value in raw_databases.items()]
        known = set(schematics)
        for spec in databases:
            if spec.schema not in known:
                raise ConfigError(
                    f"DataBase '{spec.name}' uses the schematic '{spec.schema}', which does not exist. "
                    f"Available schematics: {', '.join(sorted(known))}"
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
            raise ConfigError(f"Database '{name}' does not exist in the configuration")
        return self.schematics[spec.schema]

    def validate_references(self) -> None:
        """Check that every ``@database:...@`` reference points to a real database."""
        from .references import parse_reference  # late import avoids a cycle

        known = set(self.database_names)
        for spec in self.databases:
            schematic = self.schematics[spec.schema]
            for raw_ref in schematic.references():
                reference = parse_reference(raw_ref)
                if reference.database not in known:
                    raise ConfigError(
                        f"Schematic '{schematic.name}' references the database "
                        f"'{reference.database}', which does not exist. "
                        f"Available databases: {', '.join(sorted(known))}"
                    )

    @property
    def queries_dir(self) -> Path:
        """Custom queries folder (relative to the configuration file)."""
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
    """Ensure every schematic has a unique ``_id``.

    The automatically generated ``_id`` is created with ``unique``: besides
    avoiding repetitions within the same batch, this makes FakeBase load the
    ids already stored before appending documents to an existing database.
    """
    if "_id" in fields:
        return dict(fields)
    return {"_id": {"method": id_generator, "unique": True}, **dict(fields)}


def example_config() -> Dict[str, Any]:
    """Example configuration used by ``fakebase init``."""
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
