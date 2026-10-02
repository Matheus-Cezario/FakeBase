"""Persistência em NoSQL embutido, usando MontyDB.

MontyDB implementa a API e a linguagem de consulta do MongoDB sobre um
arquivo local (SQLite por padrão) — sem servidor, sem daemon, só uma pasta.
O mesmo código roda contra um MongoDB de verdade trocando o cliente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..errors import NotFoundError, StorageError

Document = Dict[str, Any]
Sort = Sequence[Tuple[str, int]]

MEMORY = ":memory:"
STORAGE_BACKENDS = ("sqlite", "flatfile", "memory")


class MontyStorage:
    """Adaptador do MontyDB para o contrato :class:`~fakebase.storage.base.Storage`."""

    def __init__(
        self,
        path: str = "./.fakebase",
        *,
        database: str = "fakebase",
        backend: str = "sqlite",
        strict: bool = False,
    ):
        from montydb import MontyClient, set_storage

        if backend not in STORAGE_BACKENDS:
            raise StorageError(
                f"Backend '{backend}' inválido. Use um de: {', '.join(STORAGE_BACKENDS)}"
            )

        self.backend = backend
        self.database_name = database
        #: quando ``True``, consultar uma coleção inexistente levanta erro
        self.strict = strict

        if backend == "memory":
            self.path = MEMORY
            repository = MEMORY
        else:
            self.path = str(Path(path))
            Path(self.path).mkdir(parents=True, exist_ok=True)
            set_storage(self.path, storage=backend)
            repository = self.path

        try:
            self._client = MontyClient(repository)
        except Exception as exc:  # pragma: no cover - falha de ambiente
            raise StorageError(f"Não foi possível abrir o banco em {self.path}: {exc}") from exc
        self._db = self._client[database]

    # ------------------------------------------------------------------
    def _collection(self, name: str):
        if self.strict and name not in self.collections():
            raise NotFoundError(f"Banco de dados '{name}' não existe")
        return self._db[name]

    def collections(self) -> List[str]:
        return sorted(self._db.list_collection_names())

    def exists(self, collection: str) -> bool:
        return collection in self._db.list_collection_names()

    def count(self, collection: str, filter: Optional[Document] = None) -> int:
        return int(self._collection(collection).count_documents(filter or {}))

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
        cursor = self._collection(collection).find(filter or {}, projection or None)
        if sort:
            cursor = cursor.sort(list(sort))
        if skip:
            cursor = cursor.skip(int(skip))
        if limit is not None:
            cursor = cursor.limit(int(limit))
        return [dict(document) for document in cursor]

    def find_one(
        self,
        collection: str,
        filter: Optional[Document] = None,
        *,
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[Sort] = None,
    ) -> Optional[Document]:
        documents = self.find(collection, filter, projection=projection, sort=sort, limit=1)
        return documents[0] if documents else None

    def insert(self, collection: str, documents: Iterable[Document]) -> List[Any]:
        batch = [dict(document) for document in documents]
        if not batch:
            return []
        result = self._db[collection].insert_many(batch)
        return list(result.inserted_ids)

    def update(
        self, collection: str, filter: Document, changes: Document, *, every: bool = False
    ) -> List[Document]:
        """Atualiza apenas os campos informados e devolve os documentos novos.

        ``changes`` pode ser um documento simples (vira ``$set``) ou já usar
        operadores de atualização, como ``{"$set": {...}, "$inc": {...}}``.
        """
        targets = self._targets(collection, filter, every)
        if not targets:
            return []
        operators = changes if any(key.startswith("$") for key in changes) else {"$set": changes}
        payload = {}
        for operator, fields in operators.items():
            fields = {key: value for key, value in fields.items() if key != "_id"}
            if fields:
                payload[operator] = fields
        if not payload:
            return targets
        handle = self._collection(collection)
        ids = [document["_id"] for document in targets]
        handle.update_many({"_id": {"$in": ids}}, payload)
        return self.find(collection, {"_id": {"$in": ids}})

    def replace(
        self, collection: str, filter: Document, document: Document, *, every: bool = False
    ) -> List[Document]:
        """Troca o documento inteiro, preservando o ``_id`` original."""
        targets = self._targets(collection, filter, every)
        if not targets:
            return []
        handle = self._collection(collection)
        replaced: List[Document] = []
        for target in targets:
            payload = {key: value for key, value in document.items() if key != "_id"}
            payload["_id"] = target["_id"]
            handle.replace_one({"_id": target["_id"]}, payload)
            replaced.append(payload)
        return replaced

    def delete(self, collection: str, filter: Document, *, every: bool = False) -> List[Document]:
        targets = self._targets(collection, filter, every)
        if not targets:
            return []
        ids = [document["_id"] for document in targets]
        self._collection(collection).delete_many({"_id": {"$in": ids}})
        return targets

    def distinct(self, collection: str, field: str, filter: Optional[Document] = None) -> List[Any]:
        values = self._collection(collection).distinct(field, filter or {})
        return sorted(values, key=lambda value: (value is None, str(value)))

    def drop(self, collection: str) -> None:
        self._db[collection].drop()

    def replace_collection(self, collection: str, documents: Iterable[Document]) -> int:
        """Recria a coleção do zero (usado ao gerar os dados)."""
        self.drop(collection)
        return len(self.insert(collection, documents))

    def stats(self) -> Dict[str, int]:
        return {name: self.count(name) for name in self.collections()}

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # pragma: no cover - close é best effort
            pass

    # ------------------------------------------------------------------
    def _targets(self, collection: str, filter: Document, every: bool) -> List[Document]:
        limit = None if every else 1
        return self.find(collection, filter, limit=limit)

    def __repr__(self) -> str:  # pragma: no cover
        return f"MontyStorage(path={self.path!r}, backend={self.backend!r})"
