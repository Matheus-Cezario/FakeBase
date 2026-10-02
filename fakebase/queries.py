"""Queries customizadas: arquivos ``.sql`` que viram endpoints da API.

Cada arquivo dentro da pasta de queries (``Settings.queriesPath``) vira uma
rota; as subpastas entram na URL::

    queries/
      relatorios/caros.sql        GET    /queries/relatorios/caros
      users/index.sql             GET    /queries/users
      users/index.create.sql      POST   /queries/users
      users/[id].sql              GET    /queries/users/{id}

A primeira linha do arquivo é um comentário com o método HTTP (``-- GET``,
``-- POST``, ``-- PUT`` ou ``-- DELETE``). Os demais comentários do topo
viram a descrição da rota no Swagger, exceto as diretivas:

* ``-- @param nome [tipo] [= padrão]`` declara tipo e/ou valor padrão;
* ``-- @one`` devolve só o primeiro documento (ou 404) em vez de uma lista;
* ``-- @fill false`` faz o ``INSERT`` gravar só as colunas informadas.

Os parâmetros (``:nome``) vêm, em ordem de prioridade, do caminho da URL,
do corpo JSON e da query string.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .errors import ConfigError, NotFoundError, QueryError
from .query import ListOptions, coerce, coerce_bool, _split_list
from .sql import Insert, ParsedQuery, Select, Update, build_filter, parse, resolve

METHODS = ("GET", "POST", "PUT", "DELETE")

PARAM_TYPES = ("auto", "string", "int", "float", "number", "bool", "list", "json")

_DIRECTIVE_RE = re.compile(r"^@(\w+)\s*(.*)$")
_PARAM_RE = re.compile(r"^([A-Za-z_]\w*)(?:\s+([A-Za-z]+))?\s*(?:=\s*(.*))?$")
_SEGMENT_RE = re.compile(r"^[\w\-~]+$")
_PATH_PARAM_RE = re.compile(r"^\[([A-Za-z_]\w*)\]$")

_OPENAPI_TYPES = {
    "string": "string",
    "int": "integer",
    "float": "number",
    "number": "number",
    "bool": "boolean",
    "list": "array",
    "json": "object",
}

_MISSING = object()


@dataclass
class ParamSpec:
    """Parâmetro declarado com ``-- @param``."""

    name: str
    type: str = "auto"
    default: Any = _MISSING

    @property
    def required(self) -> bool:
        return self.default is _MISSING


@dataclass
class QueryEndpoint:
    """Uma query carregada de arquivo, pronta para virar rota."""

    file: Path
    relative: str
    method: str
    route: str
    query: ParsedQuery
    summary: str = ""
    description: str = ""
    one: bool = False
    fill: bool = True
    declared: Dict[str, ParamSpec] = field(default_factory=dict)
    path_params: List[str] = field(default_factory=list)

    @property
    def collection(self) -> str:
        return self.query.statement.collection

    @property
    def params(self) -> List[ParamSpec]:
        """Todos os parâmetros usados pela query, na ordem em que aparecem."""
        names = [*self.path_params]
        names += [name for name in self.query.params if name not in names]
        return [self.declared.get(name, ParamSpec(name)) for name in names]

    # ------------------------------------------------------------------
    def bind(
        self,
        path: Mapping[str, Any] = None,
        query: Mapping[str, Any] = None,
        body: Mapping[str, Any] = None,
    ) -> Dict[str, Any]:
        """Junta e converte os valores dos parâmetros vindos da requisição.

        Valores da URL (caminho e query string) chegam como texto e passam
        pela conversão; os do corpo JSON já vêm tipados.
        """
        values: Dict[str, Any] = {}
        missing: List[str] = []
        for spec in self.params:
            raw, from_text = _MISSING, False
            for source, textual in ((path, True), (body, False), (query, True)):
                if source and spec.name in source:
                    raw, from_text = source[spec.name], textual
                    break
            if raw is _MISSING:
                if spec.required:
                    missing.append(spec.name)
                    continue
                values[spec.name] = spec.default
                continue
            values[spec.name] = convert(raw, spec.type, spec.name, from_text=from_text)
        if missing:
            raise QueryError(
                f"Parâmetro(s) obrigatório(s) ausente(s): {', '.join(missing)}"
            )
        return values

    def execute(self, fakebase, params: Mapping[str, Any]) -> Tuple[int, Any]:
        """Roda a query e devolve ``(status HTTP, corpo da resposta)``."""
        statement = self.query.statement
        name = statement.collection

        if isinstance(statement, Select):
            filter = build_filter(statement.where, params)
            if statement.count:
                return 200, {statement.count: fakebase.count(name, filter)}
            options = ListOptions(
                filter=filter,
                sort=list(statement.order),
                projection=_projection(statement),
                skip=_int_value(statement.offset, params, "OFFSET") or 0,
                limit=1 if self.one else _int_value(statement.limit, params, "LIMIT"),
            )
            documents, _ = fakebase.list(name, options)
            if statement.columns:
                documents = [_shape(document, statement.columns) for document in documents]
            if self.one:
                if not documents:
                    raise NotFoundError(f"Nenhum documento encontrado em '{name}'")
                return 200, documents[0]
            return 200, documents

        if isinstance(statement, Insert):
            created = []
            for row in statement.rows:
                document: Dict[str, Any] = {}
                for column, value in zip(statement.columns, row):
                    _set_path(document, column, resolve(value, params))
                created.append(fakebase.create(name, document, fill=self.fill))
            if self.one:
                return 201, created[0]
            return 201, {"database": name, "inserted": len(created), "value": created}

        filter = build_filter(statement.where, params)
        if isinstance(statement, Update):
            changes: Dict[str, Dict[str, Any]] = {}
            for item in statement.assignments:
                value = resolve(item.value, params)
                if item.kind == "inc":
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        raise QueryError(f"Incremento de '{item.path}' precisa ser um número")
                    changes.setdefault("$inc", {})[item.path] = value * item.sign
                else:
                    changes.setdefault("$set", {})[item.path] = value
            updated = fakebase.update(name, filter, changes, every=True)
            return self._result(name, "updated", updated)

        deleted = fakebase.delete(name, filter, every=True)
        return self._result(name, "deleted", deleted)

    def _result(self, name: str, key: str, documents: List[Dict[str, Any]]) -> Tuple[int, Any]:
        if self.one:
            if not documents:
                raise NotFoundError(f"Nenhum documento encontrado em '{name}'")
            return 200, documents[0]
        return 200, {"database": name, key: len(documents), "value": documents}

    # ------------------------------------------------------------------
    def openapi(self) -> Dict[str, Any]:
        """Parâmetros e corpo da rota para a documentação do Swagger."""
        parameters: List[Dict[str, Any]] = []
        body: Dict[str, Any] = {}
        required_body: List[str] = []
        for spec in self.params:
            schema: Dict[str, Any] = {}
            if spec.type in _OPENAPI_TYPES:
                schema["type"] = _OPENAPI_TYPES[spec.type]
            if not spec.required and spec.default is not None:
                schema["default"] = spec.default
            if spec.name in self.path_params:
                parameters.append({"name": spec.name, "in": "path", "required": True, "schema": schema})
            elif self.method in ("POST", "PUT"):
                body[spec.name] = schema
                if spec.required:
                    required_body.append(spec.name)
            else:
                parameters.append(
                    {"name": spec.name, "in": "query", "required": spec.required, "schema": schema}
                )
        extra: Dict[str, Any] = {"parameters": parameters}
        if body:
            schema = {"type": "object", "properties": body}
            if required_body:
                schema["required"] = required_body
            extra["requestBody"] = {"content": {"application/json": {"schema": schema}}}
        return extra

    def describe(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "url": self.route,
            "file": self.relative,
            "database": self.collection,
            "statement": self.query.statement.kind.upper(),
            "summary": self.summary,
            "params": [
                {
                    "name": spec.name,
                    "type": spec.type,
                    "required": spec.required,
                    **({} if spec.required else {"default": spec.default}),
                    "in": "path" if spec.name in self.path_params else (
                        "body" if self.method in ("POST", "PUT") else "query"
                    ),
                }
                for spec in self.params
            ],
        }


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------


def load_queries(
    folder: Path, *, prefix: str = "/queries", databases: Optional[Sequence[str]] = None
) -> List[QueryEndpoint]:
    """Lê todos os ``.sql`` da pasta (recursivamente) e monta os endpoints.

    Uma pasta inexistente simplesmente não gera rotas. Qualquer arquivo
    inválido levanta :class:`ConfigError` dizendo qual é e o que está errado.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return []
    endpoints: List[QueryEndpoint] = []
    seen: Dict[Tuple[str, str], QueryEndpoint] = {}
    for file in sorted(folder.rglob("*.sql")):
        endpoint = load_query(file, folder, prefix=prefix)
        if databases is not None and endpoint.collection not in databases:
            raise ConfigError(
                f"{endpoint.relative}: o banco '{endpoint.collection}' não existe. "
                f"Disponíveis: {', '.join(databases)}"
            )
        key = (endpoint.method, _route_shape(endpoint.route))
        if key in seen:
            raise ConfigError(
                f"{endpoint.relative} e {seen[key].relative} atendem a mesma rota: "
                f"{endpoint.method} {endpoint.route}"
            )
        seen[key] = endpoint
        endpoints.append(endpoint)
    # rotas fixas antes das com parâmetro, para '/users/ativos' vencer '/users/{id}'
    endpoints.sort(key=lambda e: (_route_shape(e.route).count("{}"), e.route, e.method))
    return endpoints


def load_query(file: Path, root: Path, *, prefix: str = "/queries") -> QueryEndpoint:
    relative = file.relative_to(root).as_posix()
    try:
        text = file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"{relative}: não foi possível ler o arquivo ({exc})") from exc

    header = _header_lines(text)
    if not header or header[0].split()[0].upper() not in METHODS:
        raise ConfigError(
            f"{relative}: a primeira linha precisa ser um comentário com o método HTTP "
            f"(-- {', -- '.join(METHODS)})"
        )
    first = header[0].split(None, 1)
    method = first[0].upper()
    notes = [first[1]] if len(first) > 1 else []

    endpoint_kwargs: Dict[str, Any] = {"declared": {}}
    for line in header[1:]:
        match = _DIRECTIVE_RE.match(line)
        if not match:
            notes.append(line)
            continue
        _apply_directive(relative, match.group(1), match.group(2).strip(), endpoint_kwargs)

    try:
        query = parse(text)
    except QueryError as exc:
        raise ConfigError(f"{relative}: {exc}") from exc

    route, path_params = route_for(relative, prefix)
    notes = [note for note in notes if note]
    endpoint = QueryEndpoint(
        file=file,
        relative=relative,
        method=method,
        route=route,
        query=query,
        summary=notes[0] if notes else relative,
        description="\n".join(notes[1:]),
        path_params=path_params,
        **endpoint_kwargs,
    )
    unknown = set(endpoint.declared) - {spec.name for spec in endpoint.params}
    if unknown:
        raise ConfigError(
            f"{relative}: @param declarado mas não usado na query: {', '.join(sorted(unknown))}"
        )
    return endpoint


def route_for(relative: str, prefix: str = "/queries") -> Tuple[str, List[str]]:
    """``'users/[id].sql'`` -> ``('/queries/users/{id}', ['id'])``.

    O que vem depois do primeiro ponto do nome do arquivo é ignorado, o que
    permite ``index.sql`` e ``index.create.sql`` na mesma URL com métodos
    diferentes; ``index`` representa a própria pasta.
    """
    parts = relative.split("/")
    parts[-1] = parts[-1].split(".", 1)[0]
    if parts[-1] == "index":
        parts.pop()
    segments: List[str] = []
    path_params: List[str] = []
    for part in parts:
        match = _PATH_PARAM_RE.match(part)
        if match:
            name = match.group(1)
            if name in path_params:
                raise ConfigError(f"{relative}: parâmetro de caminho '{name}' repetido")
            path_params.append(name)
            segments.append("{" + name + "}")
        elif _SEGMENT_RE.match(part):
            segments.append(part)
        else:
            raise ConfigError(
                f"{relative}: '{part}' não pode virar parte da URL "
                "(use letras, números, '-', '_' ou [parametro])"
            )
    base = "/" + prefix.strip("/") if prefix.strip("/") else ""
    route = base + ("/" + "/".join(segments) if segments else "")
    return route or "/", path_params


def _route_shape(route: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", route)


def _header_lines(text: str) -> List[str]:
    """Comentários ``--`` do topo do arquivo, sem o prefixo."""
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if lines:
                lines.append("")
            continue
        if not line.startswith("--"):
            break
        lines.append(line[2:].strip())
    while lines and not lines[0]:
        lines.pop(0)
    return lines


def _apply_directive(relative: str, name: str, value: str, target: Dict[str, Any]) -> None:
    if name == "one":
        target["one"] = coerce_bool(value or "true")
    elif name == "fill":
        target["fill"] = coerce_bool(value or "true")
    elif name == "param":
        match = _PARAM_RE.match(value)
        if not match:
            raise ConfigError(
                f"{relative}: @param inválido {value!r} (esperado '@param nome [tipo] [= padrão]')"
            )
        param, kind, default = match.groups()
        kind = (kind or "auto").lower()
        if kind not in PARAM_TYPES:
            raise ConfigError(
                f"{relative}: tipo '{kind}' do parâmetro '{param}' é inválido. "
                f"Aceitos: {', '.join(PARAM_TYPES)}"
            )
        spec = ParamSpec(param, kind)
        if default is not None:
            spec.default = convert(default.strip(), kind, param, from_text=True)
        target["declared"][param] = spec
    else:
        raise ConfigError(
            f"{relative}: diretiva '@{name}' desconhecida (aceitas: @param, @one, @fill)"
        )


# ---------------------------------------------------------------------------
# Conversão de valores
# ---------------------------------------------------------------------------


def convert(value: Any, kind: str, name: str, *, from_text: bool) -> Any:
    """Converte o valor de um parâmetro para o tipo declarado."""
    if kind == "list":
        if isinstance(value, (list, tuple)):
            return [coerce(item) if from_text else item for item in value]
        if isinstance(value, str):
            return _split_list(value)
        return [value]
    if isinstance(value, list) and from_text:
        # chave repetida na query string (?id=1&id=2)
        return [convert(item, kind, name, from_text=True) for item in value]
    if value is None:
        return None
    try:
        if kind == "auto":
            return coerce(value) if from_text else value
        if kind == "string":
            text = str(value)
            if from_text and len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
                text = text[1:-1]
            return text
        if kind in ("int", "float", "number"):
            number = coerce(value) if isinstance(value, str) else value
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ValueError
            if kind == "int":
                if isinstance(number, float) and not number.is_integer():
                    raise ValueError
                return int(number)
            return float(number) if kind == "float" else number
        if kind == "bool":
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in ("1", "true", "yes", "on", "y"):
                return True
            if text in ("0", "false", "no", "off", "n", ""):
                return False
            raise ValueError
        if kind == "json":
            return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        pass
    raise QueryError(f"Parâmetro '{name}': {value!r} não é um valor do tipo {kind}")


def _int_value(node, params: Mapping[str, Any], clause: str) -> Optional[int]:
    if node is None:
        return None
    value = resolve(node, params)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            value = int(str(value))
        except ValueError:
            raise QueryError(f"{clause} precisa ser um número inteiro, recebeu {value!r}")
    if value < 0:
        raise QueryError(f"{clause} não pode ser negativo")
    return value


# ---------------------------------------------------------------------------
# Projeção das colunas do SELECT
# ---------------------------------------------------------------------------


def _projection(statement: Select) -> Optional[Dict[str, int]]:
    if not statement.columns:
        return None
    projection = {column.path: 1 for column in statement.columns}
    if "_id" not in projection:
        projection["_id"] = 0
    return projection


def _shape(document: Mapping[str, Any], columns) -> Dict[str, Any]:
    """Monta o documento na ordem das colunas, aplicando os apelidos (AS)."""
    shaped: Dict[str, Any] = {}
    for column in columns:
        value = _get_path(document, column.path)
        if column.alias:
            shaped[column.alias] = value
        else:
            _set_path(shaped, column.path, value)
    return shaped


def _get_path(document: Any, path: str) -> Any:
    current = document
    for key in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            return None
    return current


def _set_path(document: Dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    current = document
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value
