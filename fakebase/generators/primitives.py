"""Geradores primitivos: números, booleanos, identificadores e estruturas."""

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
    category="números",
    doc="Número aleatório entre start e stop.",
    params={
        "start": "menor valor (padrão -1000)",
        "stop": "maior valor (padrão 1000)",
        "numberType": "float | int (padrão float)",
        "precision": "casas decimais (padrão 10)",
        "step": "múltiplo ao qual o valor é ajustado (opcional)",
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
    category="números",
    doc="Número inteiro aleatório (atalho para number/numberType=int).",
    params={"start": "menor valor (padrão 0)", "stop": "maior valor (padrão 100)", "step": "passo"},
    aliases=("int",),
)
def integer(ctx: GenContext, start: int = 0, stop: int = 100, step: int = 1) -> int:
    if stop < start:
        start, stop = stop, start
    return ctx.rng.randrange(start, stop + 1, max(step, 1))


@generator(
    "boolean",
    category="números",
    doc="Verdadeiro ou falso.",
    params={"chance": "probabilidade de ser verdadeiro, de 0 a 1 (padrão 0.5)"},
    aliases=("bool",),
)
def boolean(ctx: GenContext, chance: float = 0.5) -> bool:
    return ctx.rng.random() < chance


@generator(
    "randID",
    category="identificadores",
    doc="Identificador aleatório.",
    params={
        "IDType": "hex | dec | alnum (padrão hex)",
        "size": "quantidade de caracteres (padrão 16)",
        "prefix": "texto colocado antes do id",
    },
)
def rand_id(ctx: GenContext, IDType: str = "hex", size: int = 16, prefix: str = "") -> str:
    alphabets = {"hex": _HEX, "dec": _DEC, "alnum": _ALNUM}
    alphabet = alphabets.get(str(IDType).lower())
    if alphabet is None:
        raise GeneratorError(f"IDType '{IDType}' inválido. Use hex, dec ou alnum.")
    return prefix + "".join(ctx.rng.choice(alphabet) for _ in range(max(size, 1)))


@generator(
    "uuid",
    category="identificadores",
    doc="UUID versão 4.",
    params={"upper": "maiúsculas (padrão false)", "dashes": "manter hífens (padrão true)"},
)
def uuid4(ctx: GenContext, upper: bool = False, dashes: bool = True) -> str:
    value = str(uuid_module.UUID(int=ctx.rng.getrandbits(128), version=4))
    if not dashes:
        value = value.replace("-", "")
    return value.upper() if upper else value


@generator(
    "objectId",
    category="identificadores",
    doc="Identificador de 24 caracteres no formato usado pelo MongoDB.",
)
def object_id(ctx: GenContext) -> str:
    return "".join(ctx.rng.choice(_HEX) for _ in range(24))


@generator(
    "autoIncrement",
    category="identificadores",
    doc="Contador sequencial, reiniciado a cada geração do banco.",
    params={"start": "valor inicial (padrão 1)", "step": "incremento (padrão 1)"},
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
    category="geral",
    doc="Sempre devolve o mesmo valor.",
    params={"value": "valor devolvido"},
    aliases=("const",),
)
def constant(ctx: GenContext, value: Any = None) -> Any:
    return value


@generator(
    "template",
    category="texto",
    doc="Interpola campos já gerados da linha: '{name} <{email}>'.",
    params={
        "pattern": "texto com {campo}",
        "default": "valor usado quando o campo não existe (padrão vazio)",
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
    category="texto",
    doc="Preenche uma máscara: # vira dígito, ? vira letra.",
    params={"mask": "máscara, por exemplo 'AB-####-??'"},
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
    category="estruturas",
    doc="Objeto aninhado; cada chave de 'fields' é um campo com seu gerador.",
    params={"fields": "dicionário campo -> especificação de gerador"},
    aliases=("nested",),
)
def nested_object(ctx: GenContext, fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not fields:
        return {}
    if ctx.render is None:  # pragma: no cover - sempre injetado pelo Schematic
        raise GeneratorError("Gerador 'object' precisa ser executado dentro de um schematic")
    return {key: ctx.render(spec) for key, spec in fields.items()}


@generator(
    "array",
    category="estruturas",
    doc="Lista de valores gerados pela especificação 'of'.",
    params={
        "of": "especificação de gerador aplicada a cada item",
        "min": "tamanho mínimo (padrão 1)",
        "max": "tamanho máximo (padrão 3)",
        "size": "tamanho fixo (ignora min/max)",
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
        raise GeneratorError("O parâmetro 'of' é obrigatório no gerador 'array'")
    if ctx.render is None:  # pragma: no cover
        raise GeneratorError("Gerador 'array' precisa ser executado dentro de um schematic")
    if size is None:
        low, high = (min, max) if min <= max else (max, min)
        size = ctx.rng.randint(low, high)
    return [ctx.render(of) for _ in range(builtins_max(size, 0))]


def builtins_max(value: int, floor: int) -> int:
    """``max`` embutido, preservado porque o parâmetro do gerador o sombreia."""
    return value if value > floor else floor
