"""Schematic: the description of how a row of the fake database is built."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Set

from . import pipes
from .errors import SchemaError
from .generators import GenContext, get as get_generator, exists as generator_exists

#: Field keys that configure FakeBase instead of the generator.
FIELD_KEYWORDS = frozenset({"method", "transform", "nullable", "unique"})

#: Prefix used to reference another field of the same schematic.
FIELD_REF_PREFIX = "__"

#: How many times to retry before giving up on a ``unique`` field.
UNIQUE_ATTEMPTS = 200

RefResolver = Callable[[str], Any]


@dataclass
class FieldSpec:
    """A normalized schematic field."""

    name: str
    method: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    transform: Any = None
    nullable: float = 0.0
    unique: bool = False
    constant: Any = None
    is_constant: bool = False

    @classmethod
    def parse(cls, name: str, raw: Any) -> "FieldSpec":
        if isinstance(raw, str):
            if generator_exists(raw):
                return cls(name=name, method=raw)
            return cls(name=name, constant=raw, is_constant=True)
        if isinstance(raw, dict) and "method" in raw:
            params = {k: v for k, v in raw.items() if k not in FIELD_KEYWORDS}
            method = raw["method"]
            if not isinstance(method, str):
                raise SchemaError(f"Field '{name}': 'method' must be a string")
            if not generator_exists(method):
                raise SchemaError(
                    f"Field '{name}': generator '{method}' does not exist. "
                    "Run 'fakebase generators' to see the list."
                )
            nullable = _as_probability(name, raw.get("nullable", 0.0))
            return cls(
                name=name,
                method=method,
                params=params,
                transform=raw.get("transform"),
                nullable=nullable,
                unique=bool(raw.get("unique", False)),
            )
        return cls(name=name, constant=raw, is_constant=True)

    def describe(self) -> Dict[str, Any]:
        if self.is_constant:
            return {"type": "constant", "value": self.constant}
        info: Dict[str, Any] = {"type": "generator", "method": self.method}
        if self.params:
            info["params"] = self.params
        if self.transform:
            info["transform"] = self.transform
        if self.nullable:
            info["nullable"] = self.nullable
        if self.unique:
            info["unique"] = True
        return info


def _as_probability(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SchemaError(f"Field '{name}': 'nullable' must be a number between 0 and 1")
    if not 0.0 <= number <= 1.0:
        raise SchemaError(f"Field '{name}': 'nullable' must be between 0 and 1")
    return number


class Schematic:
    """Generate rows from a set of fields."""

    def __init__(self, name: str, fields: Mapping[str, Any]):
        self.name = name
        self.raw: Dict[str, Any] = dict(fields)
        self.fields: Dict[str, FieldSpec] = {
            key: FieldSpec.parse(key, value) for key, value in fields.items()
        }

    @property
    def field_names(self) -> List[str]:
        return list(self.fields)

    def describe(self) -> Dict[str, Any]:
        return {name: spec.describe() for name, spec in self.fields.items()}

    def generate(self, ctx: GenContext, resolver: Optional[RefResolver] = None) -> Dict[str, Any]:
        """Generate a complete row."""
        return _RowBuilder(self, ctx, resolver).build()

    # -- helpers used by the manager ----------------------------------------

    def references(self) -> List[str]:
        """Every ``@database:...@`` reference in the schematic."""
        found: List[str] = []
        _collect_refs(self.raw, found)
        return found

    def size_limit(self, base_dir) -> Optional[int]:
        """Smallest row limit imposed by no-repeat generators."""
        limits: List[int] = []
        for spec in self.fields.values():
            if spec.is_constant or spec.method is None:
                continue
            generator = get_generator(spec.method)
            if generator is None or generator.size_limit is None:
                continue
            limit = generator.size_limit(spec.params, base_dir)
            if limit is not None:
                limits.append(limit)
        return min(limits) if limits else None


class _RowBuilder:
    """Resolve dependencies between fields and build a row."""

    def __init__(self, schematic: Schematic, ctx: GenContext, resolver: Optional[RefResolver]):
        self.schematic = schematic
        self.ctx = ctx
        self.resolver = resolver
        self.values: Dict[str, Any] = {}
        self.resolving: List[str] = []

    def build(self) -> Dict[str, Any]:
        self.ctx.row = self.values
        for name in self.schematic.fields:
            self._ensure(name)
        return self.values

    def _ensure(self, name: str) -> Any:
        if name in self.values:
            return self.values[name]
        if name in self.resolving:
            chain = " -> ".join([*self.resolving, name])
            raise SchemaError(f"Circular dependency between fields: {chain}")
        spec = self.schematic.fields[name]
        self.resolving.append(name)
        try:
            value = self._generate(spec)
        finally:
            self.resolving.pop()
        self.values[name] = value
        return value

    def _generate(self, spec: FieldSpec) -> Any:
        ctx = self.ctx.for_field(spec.name)
        ctx.render = lambda sub_spec: self._render(sub_spec, ctx)

        if spec.is_constant:
            return pipes.apply(self._resolve(spec.constant), spec.transform)

        if spec.nullable and ctx.rng.random() < spec.nullable:
            return None

        seen: Optional[Set[Any]] = None
        if spec.unique:
            seen = ctx.local().setdefault("unique", set())

        attempts = UNIQUE_ATTEMPTS if spec.unique else 1
        value = None
        for _ in range(attempts):
            value = self._run(spec, ctx)
            if seen is None:
                return value
            key = _hashable(value)
            if key not in seen:
                seen.add(key)
                return value
        raise SchemaError(
            f"Field '{spec.name}' is marked as 'unique', but the generator "
            f"'{spec.method}' repeated the value {UNIQUE_ATTEMPTS} times in a row. "
            "Increase the variety of the data or reduce the size of the database."
        )

    def _run(self, spec: FieldSpec, ctx: GenContext) -> Any:
        generator = get_generator(spec.method or "")
        if generator is None:  # pragma: no cover - validated in FieldSpec.parse
            raise SchemaError(f"Generator '{spec.method}' does not exist")
        params = {key: self._resolve(value) for key, value in spec.params.items()}
        return pipes.apply(generator.call(ctx, params), spec.transform)

    def _render(self, raw_spec: Any, ctx: GenContext) -> Any:
        """Generate a value from a sub-specification (object/array)."""
        spec = FieldSpec.parse(ctx.field_name, raw_spec)
        if spec.is_constant:
            return pipes.apply(self._resolve(spec.constant), spec.transform)
        generator = get_generator(spec.method or "")
        params = {key: self._resolve(value) for key, value in spec.params.items()}
        return pipes.apply(generator.call(ctx, params), spec.transform)

    def _resolve(self, value: Any) -> Any:
        """Replace ``__field`` and ``@database:...@`` with the real values."""
        if isinstance(value, str):
            if value.startswith(FIELD_REF_PREFIX):
                target = value[len(FIELD_REF_PREFIX) :]
                if target in self.schematic.fields:
                    return self._ensure(target)
                raise SchemaError(
                    f"Field '{target}' referenced by '{value}' does not exist in "
                    f"schematic '{self.schematic.name}'"
                )
            if is_reference(value):
                if self.resolver is None:
                    raise SchemaError(
                        f"Reference {value} used outside of a database"
                    )
                return self.resolver(value)
            return value
        if isinstance(value, list):
            return [self._resolve(item) for item in value]
        if isinstance(value, dict):
            return {key: self._resolve(item) for key, item in value.items()}
        return value


def is_reference(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("@") and value.endswith("@") and len(value) > 2


def _collect_refs(value: Any, found: List[str]) -> None:
    if isinstance(value, str):
        if is_reference(value):
            found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_refs(item, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_refs(item, found)


def _hashable(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((key, _hashable(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(_hashable(item) for item in value)
    return value
