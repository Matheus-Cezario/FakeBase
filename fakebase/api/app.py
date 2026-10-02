"""FakeBase HTTP API (FastAPI).

Besides the new REST routes (``/users``, ``/users/{id}``, ...) the version
1.x routes keep working: ``/list/users``, ``/get/users``, ``/update/users``,
``/set/users`` and ``/delete/users``.

Custom queries (``.sql`` files in the queries folder) become routes of their
own, registered before the generic REST routes.
"""

from __future__ import annotations

import asyncio
from math import ceil
from typing import Any, Dict, List

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .. import __version__
from ..errors import (
    ConfigError,
    FakeBaseError,
    GeneratorError,
    NotFoundError,
    QueryError,
    SchemaError,
)
from ..generators import available as available_generators
from ..manager import FakeBase
from ..pipes import available as available_pipes
from ..queries import QueryEndpoint
from ..query import ListOptions, build_filter, coerce_bool, coerce_int

STATUS_BY_ERROR = {
    NotFoundError: 404,
    QueryError: 400,
    SchemaError: 400,
    GeneratorError: 400,
    ConfigError: 500,
}


def query_dict(request: Request) -> Dict[str, Any]:
    """Query string as a dict, grouping repeated keys into lists."""
    params: Dict[str, Any] = {}
    for key, value in request.query_params.multi_items():
        if key in params:
            current = params[key]
            params[key] = [*current, value] if isinstance(current, list) else [current, value]
        else:
            params[key] = value
    return params


async def json_body(request: Request) -> Any:
    try:
        raw = await request.body()
        if not raw:
            return {}
        return await request.json()
    except Exception:
        raise QueryError("The request body must be valid JSON")


def envelope(documents: List[Dict[str, Any]], total: int, options: ListOptions) -> Dict[str, Any]:
    """Response format with pagination metadata."""
    payload: Dict[str, Any] = {"value": documents, "totalItens": total, "totalItems": total}
    if options.paginate:
        payload.update(
            {
                "page": options.page,
                "pageCount": options.page_size,
                "totalPages": ceil(total / options.page_size) if options.page_size else 0,
            }
        )
    return payload


def create_app(fakebase: FakeBase) -> FastAPI:
    settings = fakebase.settings
    app = FastAPI(
        title="FakeBase",
        version=__version__,
        description=(
            "Fake database served through CRUD routes. "
            "The data lives in an embedded NoSQL store (MontyDB) and queries use "
            "MongoDB-style operators."
        ),
    )
    app.state.fakebase = fakebase
    queries = fakebase.load_queries()
    app.state.queries = queries

    if settings.cors:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Total-Count"],
        )

    if settings.latency:
        @app.middleware("http")
        async def simulate_latency(request: Request, call_next):
            await asyncio.sleep(settings.latency / 1000)
            return await call_next(request)

    @app.exception_handler(FakeBaseError)
    async def handle_error(request: Request, exc: FakeBaseError):
        status = STATUS_BY_ERROR.get(type(exc), 400)
        return JSONResponse(status_code=status, content={"error": str(exc), "type": type(exc).__name__})

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    @app.get("/", tags=["meta"], summary="Available databases")
    def index() -> Dict[str, Any]:
        stored = fakebase.storage.stats()
        return {
            "name": "FakeBase",
            "version": __version__,
            "storage": {"backend": fakebase.storage.backend, "path": fakebase.storage.path},
            "docs": "/docs",
            "dataBase": fakebase.database_names(),
            "databases": [
                {
                    "name": name,
                    "count": stored.get(name, 0),
                    "schema": fakebase.config.database(name).schema,
                    "url": f"/{name}",
                }
                for name in fakebase.database_names()
            ],
            "queries": [{"method": q.method, "url": q.route} for q in queries],
        }

    @app.get("/_schema", tags=["meta"], summary="Configuration schematics")
    def schema_all() -> Dict[str, Any]:
        return {name: s.describe() for name, s in fakebase.config.schematics.items()}

    @app.get("/_schema/{name}", tags=["meta"], summary="Schematic of a database")
    def schema_one(name: str) -> Dict[str, Any]:
        schematic = fakebase.schematic_of(name)
        return {"database": name, "schema": schematic.name, "fields": schematic.describe()}

    @app.get("/_stats", tags=["meta"], summary="Document count per database")
    def stats() -> Dict[str, Any]:
        return fakebase.stats()

    @app.get("/_generators", tags=["meta"], summary="Available generators and transforms")
    def generators() -> Dict[str, Any]:
        return {
            "generators": [
                {
                    "name": spec.name,
                    "category": spec.category,
                    "doc": spec.doc,
                    "aliases": list(spec.aliases),
                    "params": spec.params,
                }
                for spec in available_generators()
            ],
            "transforms": [
                {"name": spec.name, "doc": spec.doc, "params": spec.params} for spec in available_pipes()
            ],
        }

    @app.get("/_queries", tags=["meta"], summary="Loaded custom queries")
    def list_queries() -> List[Dict[str, Any]]:
        return [endpoint.describe() for endpoint in queries]

    # ------------------------------------------------------------------
    # Custom queries (before the generic routes, which would capture the URL)
    # ------------------------------------------------------------------
    for endpoint in queries:
        app.add_api_route(
            endpoint.route,
            _query_route(fakebase, endpoint),
            methods=[endpoint.method],
            tags=["queries"],
            summary=endpoint.summary,
            description=endpoint.description or f"File `{endpoint.relative}`",
            openapi_extra=endpoint.openapi(),
            name=f"{endpoint.method} {endpoint.route}",
        )

    # ------------------------------------------------------------------
    # Routes compatible with version 1.x
    # ------------------------------------------------------------------
    @app.get("/list/{key}", tags=["compatibility"], summary="List items (1.x format)")
    def legacy_list(key: str, request: Request) -> Dict[str, Any]:
        options = ListOptions.from_query(query_dict(request))
        documents, total = fakebase.list(key, options)
        return envelope(documents, total, options)

    @app.get("/get/{key}", tags=["compatibility"], summary="First item matching the filter")
    def legacy_get(key: str, request: Request) -> Any:
        options = ListOptions.from_query(query_dict(request))
        return fakebase.get(key, options) or {}

    @app.get("/update/{key}", tags=["compatibility"], summary="Update fields of the filtered items")
    @app.api_route(
        "/update/{key}", methods=["POST", "PUT", "PATCH"], include_in_schema=False
    )
    async def legacy_update(key: str, request: Request) -> List[Dict[str, Any]]:
        params = query_dict(request)
        options = ListOptions.from_query(params)
        _require_filter(options, "update")
        changes = await json_body(request)
        return fakebase.update(key, options.filter, changes, every=options.every)

    @app.get("/set/{key}", tags=["compatibility"], summary="Replace the filtered items")
    @app.api_route("/set/{key}", methods=["POST", "PUT"], include_in_schema=False)
    async def legacy_set(key: str, request: Request) -> List[Dict[str, Any]]:
        params = query_dict(request)
        options = ListOptions.from_query(params)
        _require_filter(options, "replace")
        document = await json_body(request)
        return fakebase.replace(key, options.filter, document, every=options.every)

    @app.get("/delete/{key}", tags=["compatibility"], summary="Delete the filtered items")
    @app.api_route("/delete/{key}", methods=["DELETE"], include_in_schema=False)
    def legacy_delete(key: str, request: Request) -> List[Dict[str, Any]]:
        options = ListOptions.from_query(query_dict(request))
        _require_filter(options, "delete")
        return fakebase.delete(key, options.filter, every=options.every)

    # ------------------------------------------------------------------
    # REST routes
    # ------------------------------------------------------------------
    @app.get("/{database}", tags=["crud"], summary="List documents")
    def list_documents(database: str, request: Request, response: Response) -> Any:
        options = ListOptions.from_query(query_dict(request))
        documents, total = fakebase.list(database, options)
        response.headers["X-Total-Count"] = str(total)
        if options.paginate:
            return envelope(documents, total, options)
        return documents

    @app.post("/{database}", status_code=201, tags=["crud"], summary="Create a document")
    async def create_document(database: str, request: Request) -> Any:
        body = await json_body(request)
        fill = coerce_bool(request.query_params.get("fill"), True)
        if isinstance(body, list):
            return [fakebase.create(database, item, fill=fill) for item in body]
        return fakebase.create(database, body, fill=fill)

    @app.get("/{database}/_count", tags=["crud"], summary="Count documents")
    def count_documents(database: str, request: Request) -> Dict[str, Any]:
        filter = build_filter(query_dict(request))
        return {"database": database, "count": fakebase.count(database, filter)}

    @app.get("/{database}/_distinct/{field}", tags=["crud"], summary="Distinct values of a field")
    def distinct_values(database: str, field: str, request: Request) -> Dict[str, Any]:
        filter = build_filter(query_dict(request))
        values = fakebase.distinct(database, field, filter)
        return {"database": database, "field": field, "values": values, "count": len(values)}

    @app.post("/{database}/_generate", tags=["crud"], summary="Generate new fake documents")
    def generate_documents(database: str, request: Request) -> Dict[str, Any]:
        count = coerce_int(request.query_params.get("count"), 1) or 1
        documents = fakebase.append(database, max(count, 1))
        return {"database": database, "created": len(documents), "value": documents}

    @app.post("/{database}/_reset", tags=["crud"], summary="Regenerate the database from scratch")
    def reset_database(database: str) -> Dict[str, Any]:
        report = fakebase.generate(only=[database])
        return report.as_dict()

    @app.get("/{database}/{item_id}", tags=["crud"], summary="Get a document by _id")
    def get_document(database: str, item_id: str) -> Any:
        document = fakebase.get_by_id(database, item_id)
        if document is None:
            raise NotFoundError(f"Document '{item_id}' does not exist in '{database}'")
        return document

    @app.patch("/{database}/{item_id}", tags=["crud"], summary="Update fields of a document")
    async def patch_document(database: str, item_id: str, request: Request) -> Any:
        changes = await json_body(request)
        updated = fakebase.update(database, {"_id": item_id}, changes)
        if not updated:
            raise NotFoundError(f"Document '{item_id}' does not exist in '{database}'")
        return updated[0]

    @app.put("/{database}/{item_id}", tags=["crud"], summary="Replace a document")
    async def put_document(database: str, item_id: str, request: Request) -> Any:
        document = await json_body(request)
        replaced = fakebase.replace(database, {"_id": item_id}, document)
        if not replaced:
            raise NotFoundError(f"Document '{item_id}' does not exist in '{database}'")
        return replaced[0]

    @app.delete("/{database}/{item_id}", tags=["crud"], summary="Delete a document")
    def delete_document(database: str, item_id: str) -> Any:
        deleted = fakebase.delete(database, {"_id": item_id})
        if not deleted:
            raise NotFoundError(f"Document '{item_id}' does not exist in '{database}'")
        return deleted[0]

    @app.patch("/{database}", tags=["crud"], summary="Update several documents by filter")
    async def patch_many(database: str, request: Request) -> List[Dict[str, Any]]:
        options = ListOptions.from_query(query_dict(request))
        _require_filter(options, "update")
        changes = await json_body(request)
        return fakebase.update(database, options.filter, changes, every=True)

    @app.delete("/{database}", tags=["crud"], summary="Delete several documents by filter")
    def delete_many(database: str, request: Request) -> List[Dict[str, Any]]:
        options = ListOptions.from_query(query_dict(request))
        _require_filter(options, "delete")
        return fakebase.delete(database, options.filter, every=True)

    return app


def _query_route(fakebase: FakeBase, endpoint: QueryEndpoint):
    async def run_query(request: Request) -> Response:
        body: Any = {}
        if endpoint.method != "GET":
            body = await json_body(request)
            if not isinstance(body, dict):
                raise QueryError("The request body must be a JSON object with the parameters")
        values = endpoint.bind(path=request.path_params, query=query_dict(request), body=body)
        status, payload = endpoint.execute(fakebase, values)
        return JSONResponse(status_code=status, content=jsonable_encoder(payload))

    return run_query


def _require_filter(options: ListOptions, action: str) -> None:
    if not options.filter:
        raise QueryError(
            f"Provide at least one filter in the query string to {action} "
            "(for safety, no document is affected without a filter)"
        )
