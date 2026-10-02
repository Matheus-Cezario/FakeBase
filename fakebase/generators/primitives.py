"""Primitive generators: numbers, booleans, identifiers and structures."""

from __future__ import annotations

import re
import uuid as uuid_module
from typing import Any, Dict, List, Optional, Union

from ..errors import GeneratorError
from .base import GenContext, generator

_HEX = "0123456789abcdef"
_DEC = "0123456789"
_ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


@generator(
    "number",
    category="numbers",
    doc="Random number between start and stop.",
    params={
        "start": "lowest value (default -1000)",
        "stop": "highest value (default 1000)",
        "numberType": "float | int (default float)",
        "precision": "decimal places (default 10)",
        "step": "multiple the value is snapped to (optional)",
    },
)
def number(
    ctx: GenContext,
    start: float = -1000.0,
    stop: float = 1000.0,
    numberType: str = "float",
    precision: int = 10,
    step: Optional[float] = None,
) -> Union[int, float]:
    if stop < start:
        start, stop = stop, start
    value = ctx.rng.uniform(start, stop)
    if step:
        value = start + round((value - start) / step) * step
        value = min(max(value, start), stop)
    if str(numberType).lower() in ("int", "integer"):
        return int(round(value))
    return round(value, precision)


@generator(
    "integer",
    category="numbers",
    doc="Random integer (shortcut for number/numberType=int).",
    params={"start": "lowest value (default 0)", "stop": "highest value (default 100)", "step": "step"},
    aliases=("int",),
)
def integer(ctx: GenContext, start: int = 0, stop: int = 100, step: int = 1) -> int:
    if stop < start:
        start, stop = stop, start
    return ctx.rng.randrange(start, stop + 1, max(step, 1))


@generator(
    "boolean",
    category="numbers",
    doc="True or false.",
    params={"chance": "probability of being true, from 0 to 1 (default 0.5)"},
    aliases=("bool",),
)
def boolean(ctx: GenContext, chance: float = 0.5) -> bool:
    return ctx.rng.random() < chance


@generator(
    "randID",
    category="identifiers",
    doc="Random identifier.",
    params={
        "IDType": "hex | dec | alnum (default hex)",
        "size": "number of characters (default 16)",
        "prefix": "text placed before the id",
    },
)
def rand_id(ctx: GenContext, IDType: str = "hex", size: int = 16, prefix: str = "") -> str:
    alphabets = {"hex": _HEX, "dec": _DEC, "alnum": _ALNUM}
    alphabet = alphabets.get(str(IDType).lower())
    if alphabet is None:
        raise GeneratorError(f"Invalid IDType '{IDType}'. Use hex, dec or alnum.")
    return prefix + "".join(ctx.rng.choice(alphabet) for _ in range(max(size, 1)))


@generator(
    "uuid",
    category="identifiers",
    doc="Version 4 UUID.",
    params={"upper": "upper case (default false)", "dashes": "keep dashes (default true)"},
)
def uuid4(ctx: GenContext, upper: bool = False, dashes: bool = True) -> str:
    value = str(uuid_module.UUID(int=ctx.rng.getrandbits(128), version=4))
    if not dashes:
        value = value.replace("-", "")
    return value.upper() if upper else value


@generator(
    "objectId",
    category="identifiers",
    doc="24-character identifier in the format used by MongoDB.",
)
def object_id(ctx: GenContext) -> str:
    return "".join(ctx.rng.choice(_HEX) for _ in range(24))


@generator(
    "autoIncrement",
    category="identifiers",
    doc="Sequential counter, restarted on every generation of the database.",
    params={"start": "initial value (default 1)", "step": "increment (default 1)"},
    aliases=("counter",),
)
def auto_increment(ctx: GenContext, start: int = 1, step: int = 1) -> int:
    local = ctx.local()
    current = local.get("counter", start - step)
    value = current + step
    local["counter"] = value
    return value


@generator(
    "constant",
    category="general",
    doc="Always returns the same value.",
    params={"value": "returned value"},
    aliases=("const",),
)
def constant(ctx: GenContext, value: Any = None) -> Any:
    return value


@generator(
    "template",
    category="text",
    doc="Interpolate fields already generated for the row: '{name} <{email}>'.",
    params={
        "pattern": "text with {field}",
        "default": "value used when the field does not exist (default empty)",
    },
    aliases=("format",),
)
def template(ctx: GenContext, pattern: str = "", default: str = "") -> str:
    def replace(match: "re.Match[str]") -> str:
        key = match.group(1).strip()
        if key not in ctx.row:
            return default
        return str(ctx.row[key])

    return re.sub(r"\{([^{}]+)\}", replace, str(pattern))


@generator(
    "pattern",
    category="text",
    doc="Fill a mask: # becomes a digit, ? becomes a letter.",
    params={"mask": "mask, for example 'AB-####-??'"},
    aliases=("mask",),
)
def pattern(ctx: GenContext, mask: str = "###") -> str:
    out = []
    for char in str(mask):
        if char == "#":
            out.append(ctx.rng.choice(_DEC))
        elif char == "?":
            out.append(ctx.rng.choice("abcdefghijklmnopqrstuvwxyz"))
        elif char == "!":
            out.append(ctx.rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        else:
            out.append(char)
    return "".join(out)


@generator(
    "object",
    category="structures",
    doc="Nested object; each key of 'fields' is a field with its generator.",
    params={"fields": "dictionary field -> generator specification"},
    aliases=("nested",),
)
def nested_object(ctx: GenContext, fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not fields:
        return {}
    if ctx.render is None:  # pragma: no cover - always injected by Schematic
        raise GeneratorError("Generator 'object' must run inside a schematic")
    return {key: ctx.render(spec) for key, spec in fields.items()}


@generator(
    "array",
    category="structures",
    doc="List of values generated by the 'of' specification.",
    params={
        "of": "generator specification applied to each item",
        "min": "minimum length (default 1)",
        "max": "maximum length (default 3)",
        "size": "fixed length (ignores min/max)",
    },
    aliases=("list",),
)
def array(
    ctx: GenContext,
    of: Any = None,
    min: int = 1,
    max: int = 3,
    size: Optional[int] = None,
) -> List[Any]:
    if of is None:
        raise GeneratorError("Parameter 'of' is required by generator 'array'")
    if ctx.render is None:  # pragma: no cover
        raise GeneratorError("Generator 'array' must run inside a schematic")
    if size is None:
        low, high = (min, max) if min <= max else (max, min)
        size = ctx.rng.randint(low, high)
    return [ctx.render(of) for _ in range(builtins_max(size, 0))]


def builtins_max(value: int, floor: int) -> int:
    """Built-in ``max``, kept because the generator parameter shadows it."""
    return value if value > floor else floor
