"""Tradução de parâmetros de consulta para filtros no dialeto MongoDB.

Usado em dois lugares:

* pela API HTTP, para transformar a *query string* em um filtro
  (``?price__gt=40&name__like=ba&sort=-price``);
* pelo resolvedor de referências entre bancos, para interpretar a parte de
  condições de ``@products:name:price<40:2@``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .errors import QueryError

#: Parâmetros que controlam a consulta e portanto nunca viram filtro.
RESERVED_QUERY_KEYS = frozenset(
    {
        "paginate",
        "page",
        "pageCount",
        "pagecount",
        "perPage",
        "per_page",
        "limit",
        "skip",
        "offset",
        "sort",
        "order",
        "fields",
        "select",
        "exclude",
        "every",
        "all",
        "count",
        "seed",
    }
)

#: Sufixo ``__op`` -> operador do MongoDB.
OPERATORS: Dict[str, str] = {
    "eq": "$eq",
    "ne": "$ne",
    "gt": "$gt",
    "gte": "$gte",
    "lt": "$lt",
    "lte": "$lte",
    "in": "$in",
    "nin": "$nin",
    "exists": "$exists",
    "regex": "$regex",
    "size": "$size",
    "all": "$all",
    "type": "$type",
    # açúcar sintático resolvido para regex
    "like": "$regex",
    "ilike": "$regex",
    "contains": "$regex",
    "start": "$regex",
    "startswith": "$regex",
    "end": "$regex",
    "endswith": "$regex",
}

_LIST_OPERATORS = {"$in", "$nin", "$all"}

_NUMBER_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")


def coerce(value: Any) -> Any:
    """Converte um valor textual para o tipo Python mais provável."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    lowered = text.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    if lowered in ("null", "none", "nil"):
        return None
    if _NUMBER_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def coerce_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise QueryError(f"Valor inteiro inválido: {value!r}")


def _split_list(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple)):
        return [coerce(v) for v in value]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [coerce(part) for part in text.split(",") if part != ""]


def _build_condition(op_name: str, raw_value: Any) -> Any:
    mongo_op = OPERATORS[op_name]
    if mongo_op in _LIST_OPERATORS:
        return {mongo_op: _split_list(raw_value)}
    if mongo_op == "$exists":
        return {mongo_op: coerce_bool(raw_value, True)}
    if mongo_op == "$size":
        return {mongo_op: coerce_int(raw_value, 0)}
    if mongo_op == "$regex":
        text = re.escape(str(raw_value))
        if op_name in ("start", "startswith"):
            pattern = f"^{text}"
        elif op_name in ("end", "endswith"):
            pattern = f"{text}$"
        elif op_name == "regex":
            pattern = str(raw_value)
        else:  # like / ilike / contains
            pattern = text
        return {"$regex": pattern, "$options": "i"}
    return {mongo_op: coerce(raw_value)}


def build_filter(params: Mapping[str, Any], *, reserved: Iterable[str] = ()) -> Dict[str, Any]:
    """Constrói um filtro a partir dos parâmetros de consulta.

    ``campo=valor`` vira igualdade; ``campo__op=valor`` usa o operador
    correspondente. Repetições do mesmo campo são combinadas com ``$and``.
    """
    ignored = set(RESERVED_QUERY_KEYS) | set(reserved)
    query: Dict[str, Any] = {}
    extra: List[Dict[str, Any]] = []

    for raw_key, raw_value in params.items():
        if raw_key in ignored:
            continue
        field_name, _, op_name = raw_key.partition("__")
        if op_name and op_name not in OPERATORS:
            raise QueryError(
                f"Operador '{op_name}' desconhecido. Disponíveis: {', '.join(sorted(OPERATORS))}"
            )
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        for value in values:
            condition = _build_condition(op_name, value) if op_name else coerce(value)
            if field_name not in query:
                query[field_name] = condition
            else:
                extra.append({field_name: condition})

    if extra:
        return {"$and": [query, *extra]}
    return query


def parse_sort(value: Any) -> List[Tuple[str, int]]:
    """``"-price,name"`` -> ``[("price", -1), ("name", 1)]``."""
    if not value:
        return []
    parts = list(value) if isinstance(value, (list, tuple)) else str(value).split(",")
    result: List[Tuple[str, int]] = []
    for part in parts:
        key = str(part).strip()
        if not key:
            continue
        if key.startswith("-"):
            result.append((key[1:], -1))
        elif key.startswith("+"):
            result.append((key[1:], 1))
        else:
            result.append((key, 1))
    return result


def parse_projection(include: Any = None, exclude: Any = None) -> Optional[Dict[str, int]]:
    """Monta a projeção do MongoDB a partir de ``fields``/``exclude``."""
    if include:
        fields = [f.strip() for f in str(include).split(",") if f.strip()]
        projection = {f: 1 for f in fields}
        projection.setdefault("_id", 1)
        return projection
    if exclude:
        fields = [f.strip() for f in str(exclude).split(",") if f.strip()]
        return {f: 0 for f in fields}
    return None


@dataclass
class ListOptions:
    """Opções normalizadas de uma consulta de listagem."""

    filter: Dict[str, Any] = field(default_factory=dict)
    sort: List[Tuple[str, int]] = field(default_factory=list)
    projection: Optional[Dict[str, int]] = None
    skip: int = 0
    limit: Optional[int] = None
    page: int = 1
    page_size: int = 10
    paginate: bool = False
    every: bool = False

    @classmethod
    def from_query(cls, params: Mapping[str, Any]) -> "ListOptions":
        get = params.get
        paginate = coerce_bool(get("paginate"), False)
        page = max(coerce_int(get("page"), 1) or 1, 1)
        page_size = coerce_int(get("pageCount") or get("perPage") or get("per_page"), 10) or 10
        page_size = max(page_size, 1)
        limit = coerce_int(get("limit"), None)
        skip = coerce_int(get("skip") or get("offset"), 0) or 0
        if paginate:
            limit, skip = page_size, page_size * (page - 1)
        return cls(
            filter=build_filter(params),
            sort=parse_sort(get("sort") or get("order")),
            projection=parse_projection(get("fields") or get("select"), get("exclude")),
            skip=skip,
            limit=limit,
            page=page,
            page_size=page_size,
            paginate=paginate,
            every=coerce_bool(get("every") or get("all"), False),
        )


# ---------------------------------------------------------------------------
# Condições usadas nas referências entre bancos: "price<40 and stock>0"
# ---------------------------------------------------------------------------

_CONDITION_RE = re.compile(r"^\s*([\w.]+)\s*(>=|<=|!=|==|~=|=|>|<)\s*(.*?)\s*$")

_CONDITION_OPS = {
    "=": "$eq",
    "==": "$eq",
    "!=": "$ne",
    ">": "$gt",
    ">=": "$gte",
    "<": "$lt",
    "<=": "$lte",
}

_OR_SPLIT = re.compile(r"\s+or\s+|\s*\|\|\s*", re.IGNORECASE)
_AND_SPLIT = re.compile(r"\s+and\s+|\s*&&\s*|\s*,\s*", re.IGNORECASE)


def parse_conditions(expression: Optional[str]) -> Dict[str, Any]:
    """Interpreta ``"price<40 and name~=bata"`` como filtro MongoDB.

    Suporta ``and``/``,``/``&&`` e ``or``/``||``; ``~=`` significa "contém"
    (regex sem diferenciar maiúsculas). Substitui o ``eval()`` da versão
    antiga, que executava a expressão vinda do arquivo de configuração.
    """
    if expression is None:
        return {}
    text = str(expression).strip()
    if not text or text.lower() in ("none", "null", "*"):
        return {}

    or_parts = [part for part in _OR_SPLIT.split(text) if part.strip()]
    clauses = [_parse_and_group(part) for part in or_parts]
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


def _parse_and_group(text: str) -> Dict[str, Any]:
    conditions: List[Dict[str, Any]] = []
    for atom in _AND_SPLIT.split(text):
        atom = atom.strip()
        if atom:
            conditions.append(_parse_atom(atom))
    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _parse_atom(atom: str) -> Dict[str, Any]:
    match = _CONDITION_RE.match(atom)
    if not match:
        raise QueryError(
            f"Condição inválida: {atom!r} (esperado algo como 'price<40' ou 'name==Batata')"
        )
    name, operator, raw_value = match.groups()
    if operator == "~=":
        return {name: {"$regex": re.escape(raw_value), "$options": "i"}}
    if operator in ("=", "==") and "," in raw_value:
        return {name: {"$in": _split_list(raw_value)}}
    return {name: {_CONDITION_OPS[operator]: coerce(raw_value)}}


def apply_sort(documents: Sequence[Dict[str, Any]], sort: Sequence[Tuple[str, int]]) -> List[Dict[str, Any]]:
    """Ordenação estável em memória (usada onde não há sort nativo)."""
    result = list(documents)
    for key, direction in reversed(list(sort)):
        result.sort(key=lambda doc: _sort_key(doc.get(key)), reverse=direction < 0)
    return result


def _sort_key(value: Any) -> Tuple[int, Any]:
    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (2, value)
    return (3, str(value))
