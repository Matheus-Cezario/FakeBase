"""Contrato da camada de persistência.

A API e o gerador só conversam com esta interface, o que permite trocar o
banco embutido (MontyDB) por um MongoDB real sem tocar no resto do código.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

Document = Dict[str, Any]
Sort = Sequence[Tuple[str, int]]


class Storage(Protocol):  # pragma: no cover - apenas contrato
    """Operações mínimas de um backend de documentos."""

    def collections(self) -> List[str]:
        ...

    def count(self, collection: str, filter: Optional[Document] = None) -> int:
        ...

    def find(
        self,
        collection: str,
        filter: Optional[Document] = None,
        *,
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[Sort] = None,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[Document]:
        ...

    def find_one(
        self,
        collection: str,
        filter: Optional[Document] = None,
        *,
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[Sort] = None,
    ) -> Optional[Document]:
        ...

    def insert(self, collection: str, documents: Iterable[Document]) -> List[Any]:
        ...

    def update(
        self, collection: str, filter: Document, changes: Document, *, every: bool = False
    ) -> List[Document]:
        ...

    def replace(
        self, collection: str, filter: Document, document: Document, *, every: bool = False
    ) -> List[Document]:
        ...

    def delete(self, collection: str, filter: Document, *, every: bool = False) -> List[Document]:
        ...

    def distinct(self, collection: str, field: str, filter: Optional[Document] = None) -> List[Any]:
        ...

    def drop(self, collection: str) -> None:
        ...

    def close(self) -> None:
        ...
