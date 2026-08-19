"""Geradores que trabalham sobre listas: escolhas, amostras e sequências."""

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
    category="listas",
    doc="Escolhe um valor de uma lista, arquivo ou referência a outro banco.",
    params={
        "data": "lista, caminho de arquivo (um valor por linha) ou @banco:campo@",
        "repeat": "permite repetir valores entre as linhas (padrão true)",
        "weights": "pesos relativos, na mesma ordem de data (opcional)",
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
                    f"'weights' tem {len(weights)} itens e 'data' tem {len(values)}"
                )
            return _normalize(ctx.rng.choices(values, weights=list(weights), k=1)[0])
        return _normalize(ctx.rng.choice(values))

    pool = pick_pool(ctx, values)
    if not pool:
        raise GeneratorError(
            f"O campo '{ctx.field_name}' usa 'choice' com repeat=false e os "
            f"{len(values)} valores disponíveis já foram usados. Aumente a lista "
            "de dados ou reduza a quantidade de documentos."
        )
    value = pool.pop(ctx.rng.randrange(len(pool)))
    return _normalize(value)


@generator(
    "chooseSeveral",
    category="listas",
    doc="Escolhe vários valores de uma lista.",
    params={
        "data": "lista, caminho de arquivo ou @banco:campo@",
        "repeat": "permite repetir valores dentro do resultado (padrão true)",
        "minValue": "quantidade mínima (padrão 0)",
        "maxValue": "quantidade máxima (padrão o tamanho de data)",
        "size": "quantidade fixa (ignora minValue/maxValue)",
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
    category="listas",
    doc="Percorre a lista em ordem, uma posição por linha.",
    params={
        "data": "lista, caminho de arquivo ou @banco:campo@",
        "repeat": "recomeça do início quando a lista acaba (padrão true)",
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
                f"O campo '{ctx.field_name}' usa 'sequence' com repeat=false e a "
                f"lista de {len(values)} valores chegou ao fim. Aumente a lista de "
                "dados ou reduza a quantidade de documentos."
            )
        index = index % len(values)
    local["index"] = index + 1
    return _normalize(values[index])


@generator(
    "numericSequence",
    category="listas",
    doc="Lista de números em progressão aritmética.",
    params={"start": "início (padrão 0)", "stop": "fim, exclusivo (padrão 10)", "step": "passo (padrão 1)"},
)
def numeric_sequence(ctx: GenContext, start: int = 0, stop: int = 10, step: int = 1) -> List[int]:
    if step == 0:
        raise GeneratorError("O parâmetro 'step' não pode ser zero")
    return list(range(start, stop, step))


@generator(
    "randomSequence",
    category="listas",
    doc="Fatia contígua e aleatória de uma lista.",
    params={
        "data": "lista, caminho de arquivo ou @banco:campo@",
        "size": "tamanho da fatia (padrão um terço da lista)",
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
    category="listas",
    doc="Devolve a lista inteira embaralhada.",
    params={"data": "lista, caminho de arquivo ou @banco:campo@"},
)
def shuffle(ctx: GenContext, data: Union[str, Sequence[Any], None] = None) -> List[Any]:
    values = [_normalize(v) for v in load_data(ctx, data)]
    ctx.rng.shuffle(values)
    return values
