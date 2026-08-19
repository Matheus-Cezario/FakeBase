"""Referências entre bancos: ``@banco:campos:condições:quantidade@``.

Exemplos::

    "@products@"                      todos os documentos de products
    "@products:name@"                 só o campo name, como lista de textos
    "@products:[name,price]@"         lista de objetos com dois campos
    "@products:name:price<50@"        filtrando por preço
    "@products:_id::3@"               três ids sorteados por linha
    "@products:_id::[1,4]@"           entre um e quatro ids por linha
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .errors import LinkError
from .query import parse_conditions

CountSpec = Union[None, str, int, Tuple[int, int]]


@dataclass
class Reference:
    """Uma referência já interpretada."""

    raw: str
    database: str
    fields: Optional[List[str]] = None
    single_field: Optional[str] = None
    conditions: Optional[str] = None
    count: CountSpec = None

    @property
    def filter(self) -> Dict[str, Any]:
        return parse_conditions(self.conditions)

    @property
    def projection(self) -> Optional[Dict[str, int]]:
        if self.single_field:
            return {self.single_field: 1, "_id": 1}
        if self.fields:
            projection = {name: 1 for name in self.fields}
            projection.setdefault("_id", 1)
            return projection
        return None


def parse_reference(raw: str) -> Reference:
    """Interpreta o texto de uma referência."""
    if not (isinstance(raw, str) and raw.startswith("@") and raw.endswith("@")):
        raise LinkError(f"Referência inválida: {raw!r} (esperado @banco:campos:condições:qtd@)")
    body = raw[1:-1].strip()
    if not body:
        raise LinkError(f"Referência vazia: {raw!r}")

    parts = [part.strip() for part in body.split(":")]
    database = parts[0]
    if not database:
        raise LinkError(f"Referência {raw!r} não indica o banco de dados")

    fields_part = parts[1] if len(parts) > 1 else ""
    conditions_part = parts[2] if len(parts) > 2 else ""
    count_part = parts[3] if len(parts) > 3 else ""
    if len(parts) > 4:
        raise LinkError(
            f"Referência {raw!r} tem partes demais. "
            "O formato é @banco:campos:condições:quantidade@"
        )

    fields, single = _parse_fields(fields_part)
    return Reference(
        raw=raw,
        database=database,
        fields=fields,
        single_field=single,
        conditions=conditions_part or None,
        count=_parse_count(count_part, raw),
    )


def _parse_fields(text: str) -> Tuple[Optional[List[str]], Optional[str]]:
    value = text.strip()
    if not value or value.lower() in ("none", "null", "*"):
        return None, None
    if value.startswith("[") and value.endswith("]"):
        names = [name.strip() for name in value[1:-1].split(",") if name.strip()]
        return (names or None), None
    return None, value


def _parse_count(text: str, raw: str) -> CountSpec:
    value = text.strip()
    if value.lower() == "all":
        return "all"
    if not value or value.lower() in ("none", "null"):
        return None
    if value.startswith("[") and value.endswith("]"):
        numbers = [part.strip() for part in value[1:-1].split(",") if part.strip()]
        if len(numbers) != 2:
            raise LinkError(f"Referência {raw!r}: a quantidade em lista precisa ser [min,max]")
        try:
            low, high = int(numbers[0]), int(numbers[1])
        except ValueError:
            raise LinkError(f"Referência {raw!r}: quantidade [min,max] precisa ser numérica")
        return (min(low, high), max(low, high))
    try:
        return int(value)
    except ValueError:
        raise LinkError(
            f"Referência {raw!r}: quantidade {value!r} inválida (use um número, 'all' ou [min,max])"
        )


class ReferenceResolver:
    """Resolve referências consultando o banco já gerado.

    Os documentos filtrados ficam em cache durante um lote de geração; a
    amostragem indicada pela quantidade acontece a cada linha, de modo que
    cada registro receba uma seleção diferente.
    """

    def __init__(self, storage: Any, rng: Optional[random.Random] = None):
        self.storage = storage
        self.rng = rng or random.Random()
        self._cache: Dict[str, List[Any]] = {}
        self._parsed: Dict[str, Reference] = {}

    def clear(self) -> None:
        self._cache.clear()

    def __call__(self, raw: str) -> List[Any]:
        return self.resolve(raw)

    def resolve(self, raw: str) -> List[Any]:
        reference = self._parsed.get(raw)
        if reference is None:
            reference = parse_reference(raw)
            self._parsed[raw] = reference
        values = self._cache.get(raw)
        if values is None:
            documents = self.storage.find(
                reference.database, reference.filter, projection=reference.projection
            )
            values = _shape(documents, reference)
            self._cache[raw] = values
        return self._sample(values, reference.count)

    def _sample(self, values: Sequence[Any], count: CountSpec) -> List[Any]:
        pool = list(values)
        if count is None or count == "all":
            return pool
        if isinstance(count, tuple):
            wanted = self.rng.randint(count[0], count[1])
        else:
            wanted = int(count)
        wanted = max(min(wanted, len(pool)), 0)
        return self.rng.sample(pool, wanted)


def _shape(documents: Sequence[Dict[str, Any]], reference: Reference) -> List[Any]:
    if reference.single_field:
        name = reference.single_field
        return [doc[name] for doc in documents if name in doc]
    if reference.fields:
        wanted = set(reference.fields)
        return [{k: v for k, v in doc.items() if k in wanted} for doc in documents]
    return [dict(doc) for doc in documents]
