"""Pipes: transformações aplicadas ao valor depois que ele é gerado.

No *schematic*, ``transform`` aceita um nome, um objeto com parâmetros ou
uma lista, que é aplicada em sequência::

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
                f"Parâmetro(s) {', '.join(sorted(unknown))} não existem no transform "
                f"'{self.name}'. Disponíveis: {', '.join(sorted(accepted)) or 'nenhum'}"
            )
        try:
            return self.func(value, **params)
        except TransformError:
            raise
        except Exception as exc:
            raise TransformError(f"Falha no transform '{self.name}': {exc}") from exc


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
    """Normaliza a declaração de ``transform`` para uma lista de passos."""
    if transform is None:
        return []
    if isinstance(transform, str):
        return [{"method": transform}]
    if isinstance(transform, dict):
        if "method" not in transform:
            raise TransformError("Cada transform precisa de um campo 'method'")
        return [dict(transform)]
    if isinstance(transform, (list, tuple)):
        steps: List[Dict[str, Any]] = []
        for item in transform:
            steps.extend(normalize(item))
        return steps
    raise TransformError(f"Transform inválido: {transform!r}")


def apply(value: Any, transform: Any) -> Any:
    """Aplica um ou mais transforms a ``value``."""
    for step in normalize(transform):
        params = dict(step)
        name = params.pop("method")
        spec = REGISTRY.get(name)
        if spec is None:
            raise TransformError(
                f"Transform '{name}' não existe. Disponíveis: "
                f"{', '.join(sorted(s.name for s in available()))}"
            )
        value = spec.call(value, params)
    return value


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------


@pipe("upper", doc="Converte para maiúsculas.")
def upper(value: Any) -> Any:
    return str(value).upper() if value is not None else value


@pipe("lower", doc="Converte para minúsculas.")
def lower(value: Any) -> Any:
    return str(value).lower() if value is not None else value


@pipe("title", doc="Coloca a primeira letra de cada palavra em maiúscula.")
def title(value: Any) -> Any:
    return str(value).title() if value is not None else value


@pipe("capitalize", doc="Coloca a primeira letra em maiúscula.")
def capitalize(value: Any) -> Any:
    return str(value).capitalize() if value is not None else value


@pipe("trim", doc="Remove espaços nas pontas.", aliases=("strip",))
def trim(value: Any) -> Any:
    return str(value).strip() if value is not None else value


@pipe(
    "prefix",
    doc="Coloca um texto antes do valor.",
    params={"text": "texto adicionado"},
)
def prefix(value: Any, text: str = "") -> str:
    return f"{text}{value}"


@pipe("suffix", doc="Coloca um texto depois do valor.", params={"text": "texto adicionado"})
def suffix(value: Any, text: str = "") -> str:
    return f"{value}{text}"


@pipe(
    "replace",
    doc="Substitui trechos do texto.",
    params={"old": "texto procurado", "new": "texto novo", "regex": "tratar 'old' como regex"},
)
def replace(value: Any, old: str = "", new: str = "", regex: bool = False) -> str:
    text = str(value)
    return re.sub(old, new, text) if regex else text.replace(old, new)


@pipe(
    "truncate",
    doc="Corta o texto em um tamanho máximo.",
    params={"length": "tamanho máximo (padrão 20)", "ellipsis": "sufixo quando corta (padrão ...)"},
)
def truncate(value: Any, length: int = 20, ellipsis: str = "...") -> str:
    text = str(value)
    return text if len(text) <= length else text[:length] + ellipsis


@pipe(
    "pad",
    doc="Completa o texto até um tamanho.",
    params={"length": "tamanho final", "char": "caractere de preenchimento (padrão 0)", "side": "left | right"},
)
def pad(value: Any, length: int = 2, char: str = "0", side: str = "left") -> str:
    text = str(value)
    return text.rjust(length, char) if side == "left" else text.ljust(length, char)


@pipe(
    "hide",
    doc="Esconde parte do valor, útil para documentos e cartões.",
    params={"keep": "quantos caracteres finais permanecem (padrão 4)", "char": "caractere usado (padrão *)"},
    aliases=("maskValue",),
)
def hide(value: Any, keep: int = 4, char: str = "*") -> str:
    text = str(value)
    if keep >= len(text):
        return text
    return char * (len(text) - keep) + text[len(text) - keep :]


@pipe("slug", doc="Transforma em identificador de URL.", params={"separator": "separador (padrão -)"})
def slug(value: Any, separator: str = "-") -> str:
    from .generators.people import slugify

    return slugify(value, separator)


# ---------------------------------------------------------------------------
# Números
# ---------------------------------------------------------------------------


@pipe("round", doc="Arredonda o número.", params={"digits": "casas decimais (padrão 2)"})
def round_value(value: Any, digits: int = 2) -> Any:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


@pipe("floor", doc="Arredonda para baixo.")
def floor(value: Any) -> Any:
    return math.floor(float(value))


@pipe("ceil", doc="Arredonda para cima.")
def ceil(value: Any) -> Any:
    return math.ceil(float(value))


@pipe("abs", doc="Valor absoluto.")
def absolute(value: Any) -> Any:
    return abs(float(value))


@pipe(
    "multiply",
    doc="Multiplica o número por um fator.",
    params={"factor": "fator (padrão 1)"},
)
def multiply(value: Any, factor: float = 1.0) -> Any:
    return float(value) * factor


@pipe(
    "currency",
    doc="Formata como moeda.",
    params={
        "prefix": "símbolo (padrão 'R$ ')",
        "brSeparator": "usa vírgula decimal e ponto de milhar (padrão true)",
        "digits": "casas decimais (padrão 2)",
    },
    aliases=("money",),
)
def currency(value: Any, prefix: str = "R$ ", brSeparator: bool = True, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise TransformError(f"'currency' espera um número, recebeu {value!r}")
    text = f"{number:,.{digits}f}"
    if brSeparator:
        text = text.translate(str.maketrans({",": ".", ".": ","}))
    return f"{prefix}{text}"


@pipe("toInt", doc="Converte para inteiro.", aliases=("int",))
def to_int(value: Any) -> int:
    return int(float(value))


@pipe("toFloat", doc="Converte para número decimal.", aliases=("float",))
def to_float(value: Any) -> float:
    return float(value)


@pipe("toString", doc="Converte para texto.", aliases=("str",))
def to_string(value: Any) -> str:
    return str(value)


@pipe("toBool", doc="Converte para booleano.", aliases=("bool",))
def to_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "y")
    return bool(value)


# ---------------------------------------------------------------------------
# Datas e coleções
# ---------------------------------------------------------------------------


@pipe(
    "dateFormat",
    doc="Reformata uma data textual.",
    params={"source": "formato de entrada (padrão %d/%m/%Y %H:%M:%S)", "target": "formato de saída"},
)
def date_format(
    value: Any, source: str = "%d/%m/%Y %H:%M:%S", target: str = "%Y-%m-%d"
) -> str:
    return datetime.strptime(str(value), source).strftime(target)


@pipe("join", doc="Junta uma lista em texto.", params={"separator": "separador (padrão ', ')"})
def join(value: Any, separator: str = ", ") -> str:
    if isinstance(value, (list, tuple)):
        return separator.join(str(item) for item in value)
    return str(value)


@pipe("split", doc="Divide um texto em lista.", params={"separator": "separador (padrão ',')"})
def split(value: Any, separator: str = ",") -> List[str]:
    return [part.strip() for part in str(value).split(separator)]


@pipe("unique", doc="Remove itens repetidos de uma lista, preservando a ordem.")
def unique(value: Any) -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    seen: List[Any] = []
    for item in value:
        if item not in seen:
            seen.append(item)
    return seen


@pipe("sort", doc="Ordena uma lista.", params={"reverse": "ordem decrescente (padrão false)"})
def sort_value(value: Any, reverse: bool = False) -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    return sorted(value, key=lambda item: (str(type(item)), str(item)), reverse=reverse)


@pipe("length", doc="Tamanho do valor.", aliases=("count",))
def length(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (str, list, tuple, dict)):
        return len(value)
    return len(str(value))


@pipe("pluck", doc="Extrai um campo de cada item de uma lista.", params={"field": "campo extraído"})
def pluck(value: Any, field: str = "") -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    return [item.get(field) if isinstance(item, dict) else item for item in value]


@pipe("sum", doc="Soma os números de uma lista.")
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


@pipe("jsonString", doc="Serializa o valor como texto JSON.")
def json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def describe() -> Iterable[PipeSpec]:
    return available()
