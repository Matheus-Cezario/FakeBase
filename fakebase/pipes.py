"""Pipes: transformations applied to a value after it is generated.

In a *schematic*, ``transform`` accepts a name, an object with parameters or
a list, which is applied in sequence::

    "price": {
        "method": "number", "start": 10, "stop": 90,
        "transform": [{"method": "round", "digits": 2}, "currency"]
    }
"""

from __future__ import annotations

import inspect
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from .errors import TransformError

TransformFunc = Callable[..., Any]


@dataclass
class PipeSpec:
    name: str
    func: TransformFunc
    doc: str = ""
    params: Dict[str, str] = field(default_factory=dict)
    aliases: Sequence[str] = ()

    def accepted_params(self) -> List[str]:
        return [p for p in inspect.signature(self.func).parameters if p != "value"]

    def call(self, value: Any, params: Mapping[str, Any]) -> Any:
        accepted = set(self.accepted_params())
        unknown = set(params) - accepted
        if unknown:
            raise TransformError(
                f"Parameter(s) {', '.join(sorted(unknown))} do not exist in transform "
                f"'{self.name}'. Available: {', '.join(sorted(accepted)) or 'none'}"
            )
        try:
            return self.func(value, **params)
        except TransformError:
            raise
        except Exception as exc:
            raise TransformError(f"Transform '{self.name}' failed: {exc}") from exc


REGISTRY: Dict[str, PipeSpec] = {}


def pipe(name: str, *, doc: str = "", params: Optional[Dict[str, str]] = None, aliases: Sequence[str] = ()):
    def decorator(func: TransformFunc) -> TransformFunc:
        spec = PipeSpec(name=name, func=func, doc=doc, params=params or {}, aliases=tuple(aliases))
        REGISTRY[name] = spec
        for alias in aliases:
            REGISTRY[alias] = spec
        return func

    return decorator


def available() -> List[PipeSpec]:
    seen: Dict[int, PipeSpec] = {}
    for spec in REGISTRY.values():
        seen.setdefault(id(spec), spec)
    return sorted(seen.values(), key=lambda s: s.name)


def exists(name: Any) -> bool:
    return isinstance(name, str) and name in REGISTRY


def normalize(transform: Any) -> List[Dict[str, Any]]:
    """Normalize a ``transform`` declaration into a list of steps."""
    if transform is None:
        return []
    if isinstance(transform, str):
        return [{"method": transform}]
    if isinstance(transform, dict):
        if "method" not in transform:
            raise TransformError("Every transform needs a 'method' field")
        return [dict(transform)]
    if isinstance(transform, (list, tuple)):
        steps: List[Dict[str, Any]] = []
        for item in transform:
            steps.extend(normalize(item))
        return steps
    raise TransformError(f"Invalid transform: {transform!r}")


def apply(value: Any, transform: Any) -> Any:
    """Apply one or more transforms to ``value``."""
    for step in normalize(transform):
        params = dict(step)
        name = params.pop("method")
        spec = REGISTRY.get(name)
        if spec is None:
            raise TransformError(
                f"Transform '{name}' does not exist. Available: "
                f"{', '.join(sorted(s.name for s in available()))}"
            )
        value = spec.call(value, params)
    return value


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


@pipe("upper", doc="Convert to upper case.")
def upper(value: Any) -> Any:
    return str(value).upper() if value is not None else value


@pipe("lower", doc="Convert to lower case.")
def lower(value: Any) -> Any:
    return str(value).lower() if value is not None else value


@pipe("title", doc="Capitalize the first letter of each word.")
def title(value: Any) -> Any:
    return str(value).title() if value is not None else value


@pipe("capitalize", doc="Capitalize the first letter.")
def capitalize(value: Any) -> Any:
    return str(value).capitalize() if value is not None else value


@pipe("trim", doc="Remove leading and trailing whitespace.", aliases=("strip",))
def trim(value: Any) -> Any:
    return str(value).strip() if value is not None else value


@pipe(
    "prefix",
    doc="Add text before the value.",
    params={"text": "text to add"},
)
def prefix(value: Any, text: str = "") -> str:
    return f"{text}{value}"


@pipe("suffix", doc="Add text after the value.", params={"text": "text to add"})
def suffix(value: Any, text: str = "") -> str:
    return f"{value}{text}"


@pipe(
    "replace",
    doc="Replace parts of the text.",
    params={"old": "text to find", "new": "replacement text", "regex": "treat 'old' as a regex"},
)
def replace(value: Any, old: str = "", new: str = "", regex: bool = False) -> str:
    text = str(value)
    return re.sub(old, new, text) if regex else text.replace(old, new)


@pipe(
    "truncate",
    doc="Cut the text at a maximum length.",
    params={"length": "maximum length (default 20)", "ellipsis": "suffix when cut (default ...)"},
)
def truncate(value: Any, length: int = 20, ellipsis: str = "...") -> str:
    text = str(value)
    return text if len(text) <= length else text[:length] + ellipsis


@pipe(
    "pad",
    doc="Pad the text up to a length.",
    params={"length": "final length", "char": "padding character (default 0)", "side": "left | right"},
)
def pad(value: Any, length: int = 2, char: str = "0", side: str = "left") -> str:
    text = str(value)
    return text.rjust(length, char) if side == "left" else text.ljust(length, char)


@pipe(
    "hide",
    doc="Mask part of the value, useful for ID numbers and cards.",
    params={"keep": "how many trailing characters stay visible (default 4)", "char": "mask character (default *)"},
    aliases=("maskValue",),
)
def hide(value: Any, keep: int = 4, char: str = "*") -> str:
    text = str(value)
    if keep >= len(text):
        return text
    return char * (len(text) - keep) + text[len(text) - keep :]


@pipe("slug", doc="Turn into a URL slug.", params={"separator": "separator (default -)"})
def slug(value: Any, separator: str = "-") -> str:
    from .generators.people import slugify

    return slugify(value, separator)


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


@pipe("round", doc="Round the number.", params={"digits": "decimal places (default 2)"})
def round_value(value: Any, digits: int = 2) -> Any:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


@pipe("floor", doc="Round down.")
def floor(value: Any) -> Any:
    return math.floor(float(value))


@pipe("ceil", doc="Round up.")
def ceil(value: Any) -> Any:
    return math.ceil(float(value))


@pipe("abs", doc="Absolute value.")
def absolute(value: Any) -> Any:
    return abs(float(value))


@pipe(
    "multiply",
    doc="Multiply the number by a factor.",
    params={"factor": "factor (default 1)"},
)
def multiply(value: Any, factor: float = 1.0) -> Any:
    return float(value) * factor


@pipe(
    "currency",
    doc="Format as currency.",
    params={
        "prefix": "symbol (default 'R$ ')",
        "brSeparator": "use a decimal comma and a thousands dot (default true)",
        "digits": "decimal places (default 2)",
    },
    aliases=("money",),
)
def currency(value: Any, prefix: str = "R$ ", brSeparator: bool = True, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise TransformError(f"'currency' expects a number, got {value!r}")
    text = f"{number:,.{digits}f}"
    if brSeparator:
        text = text.translate(str.maketrans({",": ".", ".": ","}))
    return f"{prefix}{text}"


@pipe("toInt", doc="Convert to integer.", aliases=("int",))
def to_int(value: Any) -> int:
    return int(float(value))


@pipe("toFloat", doc="Convert to decimal number.", aliases=("float",))
def to_float(value: Any) -> float:
    return float(value)


@pipe("toString", doc="Convert to string.", aliases=("str",))
def to_string(value: Any) -> str:
    return str(value)


@pipe("toBool", doc="Convert to boolean.", aliases=("bool",))
def to_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "y")
    return bool(value)


# ---------------------------------------------------------------------------
# Dates and collections
# ---------------------------------------------------------------------------


@pipe(
    "dateFormat",
    doc="Reformat a date string.",
    params={"source": "input format (default %d/%m/%Y %H:%M:%S)", "target": "output format"},
)
def date_format(
    value: Any, source: str = "%d/%m/%Y %H:%M:%S", target: str = "%Y-%m-%d"
) -> str:
    return datetime.strptime(str(value), source).strftime(target)


@pipe("join", doc="Join a list into a string.", params={"separator": "separator (default ', ')"})
def join(value: Any, separator: str = ", ") -> str:
    if isinstance(value, (list, tuple)):
        return separator.join(str(item) for item in value)
    return str(value)


@pipe("split", doc="Split a string into a list.", params={"separator": "separator (default ',')"})
def split(value: Any, separator: str = ",") -> List[str]:
    return [part.strip() for part in str(value).split(separator)]


@pipe("unique", doc="Remove repeated items from a list, keeping the order.")
def unique(value: Any) -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    seen: List[Any] = []
    for item in value:
        if item not in seen:
            seen.append(item)
    return seen


@pipe("sort", doc="Sort a list.", params={"reverse": "descending order (default false)"})
def sort_value(value: Any, reverse: bool = False) -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    return sorted(value, key=lambda item: (str(type(item)), str(item)), reverse=reverse)


@pipe("length", doc="Length of the value.", aliases=("count",))
def length(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (str, list, tuple, dict)):
        return len(value)
    return len(str(value))


@pipe("pluck", doc="Extract a field from each item of a list.", params={"field": "field to extract"})
def pluck(value: Any, field: str = "") -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    return [item.get(field) if isinstance(item, dict) else item for item in value]


@pipe("sum", doc="Sum the numbers of a list.")
def sum_values(value: Any) -> float:
    if not isinstance(value, (list, tuple)):
        return value
    total = 0.0
    for item in value:
        try:
            total += float(item)
        except (TypeError, ValueError):
            continue
    return round(total, 10)


@pipe("jsonString", doc="Serialize the value as a JSON string.")
def json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def describe() -> Iterable[PipeSpec]:
    return available()
