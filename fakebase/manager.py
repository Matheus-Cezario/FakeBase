"""Orchestration: generates the fake data and exposes the CRUD operations."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from faker import Faker

from .config import Config
from .errors import LinkError, NotFoundError
from .generators import GenContext, get as get_generator
from .queries import QueryEndpoint, load_queries
from .query import ListOptions
from .references import ReferenceResolver, parse_reference
from .schematic import Schematic
from .storage import MontyStorage, open_storage

Document = Dict[str, Any]


@dataclass
class DatabaseReport:
    """Result of generating one database."""

    name: str
    schema: str
    size: int
    notes: List[str] = field(default_factory=list)


@dataclass
class GenerationReport:
    """Complete result of ``fakebase generate``."""

    databases: List[DatabaseReport] = field(default_factory=list)
    seed: Optional[int] = None

    @property
    def total(self) -> int:
        return sum(item.size for item in self.databases)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "total": self.total,
            "databases": [
                {"name": d.name, "schema": d.schema, "size": d.size, "notes": d.notes}
                for d in self.databases
            ],
        }


class FakeBase:
    """Main facade: generates the fake databases and operates on them."""

    def __init__(self, config: Config, storage: Optional[MontyStorage] = None):
        self.config = config
        self.settings = config.settings
        self.storage = storage or open_storage(config.settings)
        self.rng = random.Random(self.settings.seed)
        self.faker = Faker(self.settings.locale)
        if self.settings.seed is not None:
            self.faker.seed_instance(self.settings.seed)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(self, only: Optional[Sequence[str]] = None, progress=None) -> GenerationReport:
        """(Re)generate every database, honoring the dependencies between them."""
        report = GenerationReport(seed=self.settings.seed)
        wanted = set(only) if only else None
        for name in self.generation_order():
            if wanted is not None and name not in wanted:
                continue
            spec = self.config.database(name)
            schematic = self.config.schematics[spec.schema]
            size, notes = self._resolve_size(name, schematic)
            documents = self._build_documents(name, schematic, size, fresh=True)
            self.storage.replace_collection(name, documents)
            report.databases.append(
                DatabaseReport(name=name, schema=spec.schema, size=len(documents), notes=notes)
            )
            if progress:
                progress(name, len(documents))
        return report

    def append(self, name: str, count: int) -> List[Document]:
        """Generate more rows in an existing database, without deleting the current ones."""
        schematic = self.schematic_of(name)
        documents = self._build_documents(name, schematic, count, fresh=False)
        self.storage.insert(name, documents)
        return documents

    def preview(self, name: str, count: int = 1) -> List[Document]:
        """Generate sample rows without storing anything."""
        return self._build_documents(name, self.schematic_of(name), count, fresh=False)

    def generation_order(self) -> List[str]:
        """Order in which the databases must be generated (topological sort)."""
        graph = self.dependency_graph()
        order: List[str] = []
        visited: Dict[str, int] = {}

        def visit(node: str, stack: Tuple[str, ...]) -> None:
            state = visited.get(node)
            if state == 2:
                return
            if state == 1:
                chain = " -> ".join([*stack, node])
                raise LinkError(f"Circular reference between databases: {chain}")
            visited[node] = 1
            for dependency in sorted(graph.get(node, set())):
                visit(dependency, (*stack, node))
            visited[node] = 2
            order.append(node)

        for name in self.config.database_names:
            visit(name, ())
        return order

    def dependency_graph(self) -> Dict[str, set]:
        """Map database -> databases it references."""
        graph: Dict[str, set] = {}
        for spec in self.config.databases:
            schematic = self.config.schematics[spec.schema]
            targets = {parse_reference(raw).database for raw in schematic.references()}
            graph[spec.name] = {target for target in targets if target != spec.name}
        return graph

    # ------------------------------------------------------------------
    def _build_documents(
        self, name: str, schematic: Schematic, count: int, *, fresh: bool
    ) -> List[Document]:
        resolver = ReferenceResolver(self.storage, self.rng)
        context = GenContext(
            rng=self.rng,
            faker=self.faker,
            base_dir=self.config.base_dir,
            database=name,
        )
        if not fresh:
            self._prime_state(name, schematic, context)
        documents: List[Document] = []
        for index in range(max(count, 0)):
            context.row_index = index
            documents.append(schematic.generate(context, resolver))
        return documents

    def _prime_state(self, name: str, schematic: Schematic, context: GenContext) -> None:
        """Resume counters and uniqueness sets from what already exists."""
        if not self.storage.exists(name):
            return
        existing = self.storage.count(name)
        for field_name, spec in schematic.fields.items():
            scope = f"{name}.{field_name}"
            state = context.state.setdefault(scope, {})
            if spec.unique:
                state["unique"] = set(self.storage.distinct(name, field_name))
            # 'choice' and 'sequence' without repetition consume a pool: values
            # already stored must leave it before generating more rows.
            if spec.method in ("choice", "sequence") and _says_no_repeat(spec.params.get("repeat")):
                state["exclude"] = _hashable_set(self.storage.distinct(name, field_name))
                if spec.method == "sequence":
                    state["index"] = existing
            if spec.method in ("autoIncrement", "counter"):
                highest = self.storage.find_one(name, {}, sort=[(field_name, -1)])
                if highest and isinstance(highest.get(field_name), int):
                    state["counter"] = highest[field_name]

    def _resolve_size(self, name: str, schematic: Schematic) -> Tuple[int, List[str]]:
        spec = self.config.database(name)
        notes: List[str] = []
        limit = schematic.size_limit(self.config.base_dir)

        if spec.size is not None:
            size = spec.size
        elif spec.size_range is not None:
            size = self.rng.randint(*spec.size_range)
        elif limit is not None:
            size = limit
            notes.append(f"size limited to {limit} by a no-repeat generator")
        else:
            size = self.rng.randint(self.settings.minSize, self.settings.maxSize)
            notes.append(f"size drawn between {self.settings.minSize} and {self.settings.maxSize}")

        if limit is not None and size > limit:
            notes.append(
                f"'size' asked for {size}, but a no-repeat generator limits it to {limit} rows"
            )
            size = limit
        return size, notes

    # ------------------------------------------------------------------
    # Queries and CRUD
    # ------------------------------------------------------------------
    def database_names(self) -> List[str]:
        return self.config.database_names

    def ensure_database(self, name: str) -> str:
        if name not in self.config.database_names:
            raise NotFoundError(
                f"Database '{name}' does not exist. "
                f"Available: {', '.join(self.config.database_names)}"
            )
        return name

    def schematic_of(self, name: str) -> Schematic:
        self.ensure_database(name)
        return self.config.schematic_for(name)

    def list(self, name: str, options: ListOptions) -> Tuple[List[Document], int]:
        self.ensure_database(name)
        total = self.storage.count(name, options.filter)
        documents = self.storage.find(
            name,
            options.filter,
            projection=options.projection,
            sort=options.sort,
            skip=options.skip,
            limit=options.limit,
        )
        return documents, total

    def get(self, name: str, options: ListOptions) -> Optional[Document]:
        self.ensure_database(name)
        return self.storage.find_one(
            name, options.filter, projection=options.projection, sort=options.sort
        )

    def get_by_id(self, name: str, item_id: Any) -> Optional[Document]:
        self.ensure_database(name)
        return self.storage.find_one(name, {"_id": item_id})

    def count(self, name: str, filter: Optional[Document] = None) -> int:
        self.ensure_database(name)
        return self.storage.count(name, filter or {})

    def distinct(self, name: str, field_name: str, filter: Optional[Document] = None) -> List[Any]:
        self.ensure_database(name)
        return self.storage.distinct(name, field_name, filter or {})

    def create(self, name: str, document: Mapping[str, Any], *, fill: bool = True) -> Document:
        """Insert a document; missing fields are generated by the schematic."""
        self.ensure_database(name)
        payload: Document = dict(document or {})
        if fill:
            generated = self.preview(name, 1)[0]
            generated.update(payload)
            payload = generated
        payload.setdefault("_id", self.new_id())
        self.storage.insert(name, [payload])
        return payload

    def update(
        self, name: str, filter: Document, changes: Mapping[str, Any], *, every: bool = False
    ) -> List[Document]:
        self.ensure_database(name)
        return self.storage.update(name, filter, dict(changes), every=every)

    def replace(
        self, name: str, filter: Document, document: Mapping[str, Any], *, every: bool = False
    ) -> List[Document]:
        self.ensure_database(name)
        return self.storage.replace(name, filter, dict(document), every=every)

    def delete(self, name: str, filter: Document, *, every: bool = False) -> List[Document]:
        self.ensure_database(name)
        return self.storage.delete(name, filter, every=every)

    def load_queries(self) -> List[QueryEndpoint]:
        """Load the custom queries from the configured folder."""
        return load_queries(
            self.config.queries_dir,
            prefix=self.settings.queriesPrefix,
            databases=self.config.database_names,
        )

    def drop(self, name: str) -> None:
        self.ensure_database(name)
        self.storage.drop(name)

    def new_id(self) -> Any:
        generator = get_generator(self.settings.idGenerator)
        context = GenContext(rng=self.rng, faker=self.faker, base_dir=self.config.base_dir)
        return generator.call(context, {})

    # ------------------------------------------------------------------
    # Import / export
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        stored = self.storage.stats()
        return {
            "storage": {"path": self.storage.path, "backend": self.storage.backend},
            "databases": [
                {
                    "name": name,
                    "schema": self.config.database(name).schema,
                    "count": stored.get(name, 0),
                    "generated": name in stored,
                }
                for name in self.config.database_names
            ],
            "orphans": sorted(set(stored) - set(self.config.database_names)),
        }

    def export(self, target: Path, *, only: Optional[Sequence[str]] = None, indent: int = 2) -> List[Path]:
        """Write each database to a JSON file (compatible with version 1.x)."""
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        written: List[Path] = []
        for name in only or self.config.database_names:
            documents = self.storage.find(name, {})
            path = target / f"{name}.json"
            path.write_text(
                json.dumps({name: documents}, indent=indent, ensure_ascii=False),
                encoding="utf-8",
            )
            written.append(path)
        return written

    def import_json(self, source: Path, *, replace: bool = True) -> Dict[str, int]:
        """Load JSON files (one per database) into the NoSQL store."""
        source = Path(source)
        files: Iterable[Path]
        if source.is_dir():
            files = sorted(source.glob("*.json"))
        else:
            files = [source]
        loaded: Dict[str, int] = {}
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for name, documents in _iter_collections(payload, path.stem):
                if replace:
                    self.storage.drop(name)
                self.storage.insert(name, documents)
                loaded[name] = loaded.get(name, 0) + len(documents)
        return loaded

    def close(self) -> None:
        self.storage.close()


def _hashable_set(values: Iterable[Any]) -> set:
    """Set of the values that can be hashed; the rest is ignored."""
    result = set()
    for value in values:
        try:
            result.add(value)
        except TypeError:  # lists and dicts do not go into the set
            continue
    return result


def _says_no_repeat(value: Any) -> bool:
    """``repeat`` turned off, either as ``false`` or as ``"false"``."""
    if isinstance(value, str):
        return value.strip().lower() in ("false", "0", "no", "off", "n")
    return value is False


def _iter_collections(payload: Any, fallback: str):
    if isinstance(payload, list):
        yield fallback, payload
    elif isinstance(payload, dict):
        for name, documents in payload.items():
            if isinstance(documents, list):
                yield name, documents
