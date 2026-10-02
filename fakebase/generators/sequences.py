"""Generators that work on lists: choices, samples and sequences."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Union

from ..errors import GeneratorError
from .base import GenContext, generator, load_data, no_repeat_limit, pick_pool


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    return value


@generator(
    "choice",
    category="lists",
    doc="Pick a value from a list, a file or a reference to another database.",
    params={
        "data": "list, file path (one value per line) or @database:field@",
        "repeat": "allow repeating values across rows (default true)",
        "weights": "relative weights, in the same order as data (optional)",
    },
    size_limit=no_repeat_limit,
)
def choice(
    ctx: GenContext,
    data: Union[str, Sequence[Any], None] = None,
    repeat: bool = True,
    weights: Optional[Sequence[float]] = None,
) -> Any:
    values = load_data(ctx, data)
    if not values:
        return None
    if repeat:
        if weights:
            if len(weights) != len(values):
                raise GeneratorError(
                    f"'weights' has {len(weights)} items and 'data' has {len(values)}"
                )
            return _normalize(ctx.rng.choices(values, weights=list(weights), k=1)[0])
        return _normalize(ctx.rng.choice(values))

    pool = pick_pool(ctx, values)
    if not pool:
        raise GeneratorError(
            f"Field '{ctx.field_name}' uses 'choice' with repeat=false and all "
            f"{len(values)} available values were already used. Grow the data "
            "list or reduce the number of documents."
        )
    value = pool.pop(ctx.rng.randrange(len(pool)))
    return _normalize(value)


@generator(
    "chooseSeveral",
    category="lists",
    doc="Pick several values from a list.",
    params={
        "data": "list, file path or @database:field@",
        "repeat": "allow repeating values within the result (default true)",
        "minValue": "minimum count (default 0)",
        "maxValue": "maximum count (default the length of data)",
        "size": "fixed count (ignores minValue/maxValue)",
    },
    aliases=("sample",),
)
def choose_several(
    ctx: GenContext,
    data: Union[str, Sequence[Any], None] = None,
    repeat: bool = True,
    minValue: int = 0,
    maxValue: Optional[int] = None,
    size: Optional[int] = None,
) -> List[Any]:
    values = load_data(ctx, data)
    if not values:
        return []
    upper = len(values) if maxValue is None else maxValue
    if not repeat:
        upper = min(upper, len(values))
    lower = max(minValue, 0)
    if size is not None:
        count = size
    else:
        if upper < lower:
            lower, upper = upper, lower
        count = ctx.rng.randint(lower, upper)
    if not repeat:
        count = min(count, len(values))
        return [_normalize(v) for v in ctx.rng.sample(values, count)]
    return [_normalize(ctx.rng.choice(values)) for _ in range(max(count, 0))]


@generator(
    "sequence",
    category="lists",
    doc="Walk the list in order, one position per row.",
    params={
        "data": "list, file path or @database:field@",
        "repeat": "start over when the list ends (default true)",
    },
    size_limit=no_repeat_limit,
)
def sequence(
    ctx: GenContext, data: Union[str, Sequence[Any], None] = None, repeat: bool = True
) -> Any:
    values = load_data(ctx, data)
    if not values:
        return None
    local = ctx.local()
    index = local.get("index", 0)
    if index >= len(values):
        if not repeat:
            raise GeneratorError(
                f"Field '{ctx.field_name}' uses 'sequence' with repeat=false and the "
                f"list of {len(values)} values ran out. Grow the data list or "
                "reduce the number of documents."
            )
        index = index % len(values)
    local["index"] = index + 1
    return _normalize(values[index])


@generator(
    "numericSequence",
    category="lists",
    doc="List of numbers in arithmetic progression.",
    params={"start": "start (default 0)", "stop": "end, exclusive (default 10)", "step": "step (default 1)"},
)
def numeric_sequence(ctx: GenContext, start: int = 0, stop: int = 10, step: int = 1) -> List[int]:
    if step == 0:
        raise GeneratorError("Parameter 'step' cannot be zero")
    return list(range(start, stop, step))


@generator(
    "randomSequence",
    category="lists",
    doc="Random contiguous slice of a list.",
    params={
        "data": "list, file path or @database:field@",
        "size": "slice length (default a third of the list)",
    },
)
def random_sequence(
    ctx: GenContext, data: Union[str, Sequence[Any], None] = None, size: Optional[int] = None
) -> List[Any]:
    values = load_data(ctx, data)
    if not values:
        return []
    length = size if size else max(len(values) // 3, 1)
    length = min(length, len(values))
    start = ctx.rng.randint(0, len(values) - length)
    return [_normalize(v) for v in values[start : start + length]]


@generator(
    "shuffle",
    category="lists",
    doc="Return the whole list shuffled.",
    params={"data": "list, file path or @database:field@"},
)
def shuffle(ctx: GenContext, data: Union[str, Sequence[Any], None] = None) -> List[Any]:
    values = [_normalize(v) for v in load_data(ctx, data)]
    ctx.rng.shuffle(values)
    return values
