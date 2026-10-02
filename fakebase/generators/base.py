"""Value generator infrastructure.

A generator is a function registered with :func:`generator` that receives a
:class:`GenContext` and the parameters declared in the *schematic*::

    @generator("number", doc="Random number")
    def number(ctx: GenContext, start: float = -1000.0, stop: float = 1000.0):
        ...

The registry keeps the signature, which makes it possible to reject unknown
parameters, convert types coming from JSON and document everything in
``fakebase generators``.
"""

from __future__ import annotations

import inspect
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from ..errors import GeneratorError

Renderer = Callable[[Any], Any]


@dataclass
class GenContext:
    """State shared by every generator during generation."""

    rng: random.Random
    faker: Any
    base_dir: Path
    #: persistent state per scope (``database.field``) - pools, counters...
    state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: fields already generated for the current row
    row: Dict[str, Any] = field(default_factory=dict)
    database: str = ""
    field_name: str = ""
    row_index: int = 0
    #: generates the value of a sub-specification (used by ``object``/``array``)
    render: Optional[Renderer] = None

    @property
    def scope(self) -> str:
        return f"{self.database}.{self.field_name}"

    def local(self) -> Dict[str, Any]:
        """Persistent state of the current field."""
        return self.state.setdefault(self.scope, {})

    def shared(self) -> Dict[str, Any]:
        """State shared by the whole generation (file cache)."""
        return self.state.setdefault("__shared__", {})

    def for_field(self, field_name: str) -> "GenContext":
        clone = GenContext(
            rng=self.rng,
            faker=self.faker,
            base_dir=self.base_dir,
            state=self.state,
            row=self.row,
            database=self.database,
            field_name=field_name,
            row_index=self.row_index,
            render=self.render,
        )
        return clone


SizeLimit = Callable[[Mapping[str, Any], Path], Optional[int]]


@dataclass
class GeneratorSpec:
    """Metadata of a registered generator."""

    name: str
    func: Callable[..., Any]
    doc: str = ""
    params: Dict[str, str] = field(default_factory=dict)
    aliases: Sequence[str] = ()
    size_limit: Optional[SizeLimit] = None
    category: str = "general"

    @property
    def signature(self) -> inspect.Signature:
        return inspect.signature(self.func)

    def accepted_params(self) -> List[str]:
        return [p for p in self.signature.parameters if p != "ctx"]

    def call(self, ctx: GenContext, params: Mapping[str, Any]) -> Any:
        kwargs = self._prepare(params)
        try:
            return self.func(ctx, **kwargs)
        except GeneratorError:
            raise
        except Exception as exc:  # pragma: no cover - generic safeguard
            raise GeneratorError(
                f"Generator '{self.name}' failed (field '{ctx.field_name}'): {exc}"
            ) from exc

    def _prepare(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        signature = self.signature
        accepted = set(self.accepted_params())
        has_var_kw = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
        )
        kwargs: Dict[str, Any] = {}
        for key, value in params.items():
            if key not in accepted and not has_var_kw:
                raise GeneratorError(
                    f"Parameter '{key}' does not exist in generator '{self.name}'. "
                    f"Available: {', '.join(sorted(accepted)) or 'none'}"
                )
            parameter = signature.parameters.get(key)
            kwargs[key] = _convert(value, parameter.annotation if parameter else None, self.name, key)
        return kwargs


REGISTRY: Dict[str, GeneratorSpec] = {}


def generator(
    name: str,
    *,
    doc: str = "",
    params: Optional[Dict[str, str]] = None,
    aliases: Sequence[str] = (),
    size_limit: Optional[SizeLimit] = None,
    category: str = "general",
):
    """Register a function as a value generator."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        summary = doc.strip() if doc else _first_line(func.__doc__)
        spec = GeneratorSpec(
            name=name,
            func=func,
            doc=summary,
            params=params or {},
            aliases=tuple(aliases),
            size_limit=size_limit,
            category=category,
        )
        REGISTRY[name] = spec
        for alias in spec.aliases:
            REGISTRY[alias] = spec
        return func

    return decorator


def _first_line(text: Optional[str]) -> str:
    for line in (text or "").strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def get(name: str) -> Optional[GeneratorSpec]:
    return REGISTRY.get(name)


def exists(name: Any) -> bool:
    return isinstance(name, str) and name in REGISTRY


def available() -> List[GeneratorSpec]:
    """Registered generators, without repeating aliases."""
    seen: Dict[int, GeneratorSpec] = {}
    for spec in REGISTRY.values():
        seen.setdefault(id(spec), spec)
    return sorted(seen.values(), key=lambda s: (s.category, s.name))


# ---------------------------------------------------------------------------
# Conversion of parameters coming from JSON
# ---------------------------------------------------------------------------

_TRUE = {"1", "true", "yes", "on", "y"}
_FALSE = {"0", "false", "no", "off", "n"}


def _convert(value: Any, annotation: Any, generator_name: str, param: str) -> Any:
    if annotation is inspect.Parameter.empty or annotation is None or value is None:
        return value
    text_annotation = str(annotation)
    try:
        if annotation is bool or "bool" in text_annotation:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in _TRUE:
                    return True
                if lowered in _FALSE:
                    return False
            if isinstance(value, (int, float)):
                return bool(value)
            return value
        if annotation is int or ("int" in text_annotation and "float" not in text_annotation):
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                return value
            return int(float(value))
        if annotation is float or "float" in text_annotation:
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                return value
            return float(value)
    except (TypeError, ValueError):
        raise GeneratorError(
            f"Parameter '{param}' of generator '{generator_name}' got {value!r}, "
            f"incompatible with {text_annotation}"
        )
    return value


# ---------------------------------------------------------------------------
# Helpers shared by several generators
# ---------------------------------------------------------------------------


def load_data(ctx: GenContext, data: Any, *, param: str = "data") -> List[Any]:
    """Normalize the ``data`` parameter.

    Accepts a literal list, the path of a text file (one value per line) or
    the already resolved result of a cross-database reference.
    """
    if data is None:
        raise GeneratorError(f"Parameter '{param}' is required")
    if isinstance(data, (list, tuple)):
        return list(data)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, str):
        return read_lines(ctx, data)
    return [data]


def read_lines(ctx: GenContext, path: str) -> List[str]:
    """Read (with cache) a text file as a list of values."""
    cache: Dict[str, List[str]] = ctx.shared().setdefault("files", {})
    if path in cache:
        return list(cache[path])
    resolved = resolve_path(ctx.base_dir, path)
    if not resolved.is_file():
        raise GeneratorError(f"Data file not found: {path}")
    lines = [line.strip() for line in resolved.read_text(encoding="utf-8").splitlines()]
    values = [line for line in lines if line]
    cache[path] = values
    return list(values)


def resolve_path(base_dir: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    relative = base_dir / candidate
    if relative.exists():
        return relative
    return candidate


def data_length(data: Any, base_dir: Path) -> Optional[int]:
    """Length of ``data`` without needing a context (used for limits)."""
    if isinstance(data, (list, tuple)):
        return len(data)
    if isinstance(data, str):
        if data.startswith("@"):  # cross-database reference: only known at runtime
            return None
        resolved = resolve_path(base_dir, data)
        if resolved.is_file():
            return sum(
                1 for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip()
            )
    return None


def no_repeat_limit(params: Mapping[str, Any], base_dir: Path) -> Optional[int]:
    """Row limit when the generator cannot repeat values."""
    repeat = params.get("repeat", True)
    if isinstance(repeat, str):
        repeat = repeat.strip().lower() not in _FALSE
    if repeat:
        return None
    return data_length(params.get("data"), base_dir)


def pick_pool(ctx: GenContext, data: Iterable[Any]) -> List[Any]:
    """Persistent pool per field, used when ``repeat`` is ``false``.

    If the state carries an ``exclude`` set (values already stored in the
    database), they are left out — this keeps the "no repetition" promise
    when new documents are appended later.
    """
    local = ctx.local()
    if "pool" not in local:
        excluded = local.get("exclude") or set()
        local["pool"] = [value for value in data if not _is_excluded(value, excluded)]
    return local["pool"]


def _is_excluded(value: Any, excluded: Any) -> bool:
    try:
        return value in excluded
    except TypeError:  # unhashable values (lists, dicts)
        return False
