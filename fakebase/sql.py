"""Subconjunto de SQL traduzido para o dialeto do MongoDB.

Usado pelas queries customizadas (arquivos ``.sql`` na pasta de queries).
Suporta uma instrução por arquivo:

* ``SELECT * | col [AS alias], ... | COUNT(*) [AS alias] FROM banco
  [WHERE ...] [ORDER BY col [ASC|DESC], ...] [LIMIT n] [OFFSET n]``
* ``INSERT INTO banco (col, ...) VALUES (valor, ...), (...)``
* ``UPDATE banco SET col = valor, col = col + valor [WHERE ...]``
* ``DELETE FROM banco [WHERE ...]``

No ``WHERE``: ``= != <> < <= > >=``, ``[NOT] LIKE`` / ``ILIKE`` (``%`` e
``_``), ``[NOT] IN (...)`` ou ``IN :lista``, ``[NOT] BETWEEN a AND b``,
``IS [NOT] NULL``, ``AND``, ``OR``, ``NOT`` e parênteses.

Parâmetros nomeados (``:nome``) são resolvidos antes da tradução, então
condições que só envolvem parâmetros viram constantes. Isso permite filtros
opcionais como ``(:nome IS NULL OR name = :nome)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .errors import QueryError

# ---------------------------------------------------------------------------
# Árvore sintática
# ---------------------------------------------------------------------------


@dataclass
class Const:
    value: Any


@dataclass
class Param:
    name: str


@dataclass
class Field:
    path: str


Operand = Union[Const, Param, Field]


@dataclass
class Compare:
    left: Operand
    op: str
    right: Operand


@dataclass
class Like:
    operand: Operand
    pattern: Operand
    negate: bool = False


@dataclass
class In:
    operand: Operand
    values: Union[List[Operand], Param]
    negate: bool = False


@dataclass
class Between:
    operand: Operand
    low: Operand
    high: Operand
    negate: bool = False


@dataclass
class IsNull:
    operand: Operand
    negate: bool = False


@dataclass
class And:
    items: List[Any]


@dataclass
class Or:
    items: List[Any]


@dataclass
class Not:
    item: Any


@dataclass
class Column:
    path: str
    alias: Optional[str] = None


@dataclass
class Assignment:
    path: str
    value: Operand
    #: ``"set"`` (``col = valor``) ou ``"inc"`` (``col = col + valor``)
    kind: str = "set"
    sign: int = 1


@dataclass
class Select:
    collection: str
    columns: Optional[List[Column]] = None  # None = SELECT *
    count: Optional[str] = None  # nome da chave de COUNT(*)
    where: Any = None
    order: List[Tuple[str, int]] = field(default_factory=list)
    limit: Optional[Operand] = None
    offset: Optional[Operand] = None
    kind: str = "select"


@dataclass
class Insert:
    collection: str
    columns: List[str]
    rows: List[List[Operand]]
    kind: str = "insert"


@dataclass
class Update:
    collection: str
    assignments: List[Assignment]
    where: Any = None
    kind: str = "update"


@dataclass
class Delete:
    collection: str
    where: Any = None
    kind: str = "delete"


Statement = Union[Select, Insert, Update, Delete]


@dataclass
class ParsedQuery:
    statement: Statement
    #: parâmetros na ordem em que aparecem, sem repetição
    params: List[str]


# ---------------------------------------------------------------------------
# Análise léxica
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>--[^\n]*|/\*.*?\*/)
  | (?P<string>'(?:[^']|'')*')
  | (?P<quoted>"(?:[^"]|"")*"|`[^`]*`)
  | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
  | (?P<param>:[A-Za-z_]\w*)
  | (?P<name>[A-Za-z_$][\w$]*(?:\.\w+)*)
  | (?P<op><=|>=|<>|!=|==|=|<|>|\(|\)|,|\*|\+|-|;)
    """,
    re.S | re.X,
)

KEYWORDS = frozenset(
    {
        "SELECT", "FROM", "WHERE", "ORDER", "BY", "ASC", "DESC", "LIMIT", "OFFSET",
        "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "AND", "OR", "NOT",
        "LIKE", "ILIKE", "IN", "BETWEEN", "IS", "NULL", "TRUE", "FALSE", "AS", "COUNT",
    }
)


@dataclass
class Token:
    kind: str  # name, quoted, string, number, param, op, eof
    value: Any
    pos: int

    @property
    def keyword(self) -> Optional[str]:
        if self.kind == "name" and self.value.upper() in KEYWORDS:
            return self.value.upper()
        return None


def tokenize(text: str) -> List[Token]:
    tokens: List[Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if not match:
            raise QueryError(f"Caractere inesperado {text[pos]!r} {_where(text, pos)}")
        kind = match.lastgroup
        raw = match.group()
        if kind == "string":
            tokens.append(Token("string", raw[1:-1].replace("''", "'"), pos))
        elif kind == "quoted":
            value = raw[1:-1].replace('""', '"') if raw[0] == '"' else raw[1:-1]
            tokens.append(Token("quoted", value, pos))
        elif kind == "number":
            number = float(raw) if any(c in raw for c in ".eE") else int(raw)
            tokens.append(Token("number", number, pos))
        elif kind == "param":
            tokens.append(Token("param", raw[1:], pos))
        elif kind in ("name", "op"):
            tokens.append(Token(kind, raw, pos))
        pos = match.end()
    tokens.append(Token("eof", None, len(text)))
    return tokens


def _where(text: str, pos: int) -> str:
    line = text.count("\n", 0, pos) + 1
    column = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return f"(linha {line}, coluna {column})"


# ---------------------------------------------------------------------------
# Análise sintática
# ---------------------------------------------------------------------------


class Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = tokenize(text)
        self.index = 0
        self.params: List[str] = []

    # -- utilidades ------------------------------------------------------
    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.tokens[self.index]
        if token.kind != "eof":
            self.index += 1
        return token

    def error(self, message: str, token: Optional[Token] = None) -> QueryError:
        token = token or self.current
        found = "fim da query" if token.kind == "eof" else repr(str(token.value))
        return QueryError(f"{message}, encontrado {found} {_where(self.text, token.pos)}")

    def at_keyword(self, *words: str) -> bool:
        return self.current.keyword in words

    def accept_keyword(self, *words: str) -> Optional[str]:
        if self.at_keyword(*words):
            return self.advance().keyword
        return None

    def expect_keyword(self, word: str) -> None:
        if not self.accept_keyword(word):
            raise self.error(f"Esperado {word}")

    def at_op(self, *ops: str) -> bool:
        return self.current.kind == "op" and self.current.value in ops

    def accept_op(self, *ops: str) -> Optional[str]:
        if self.at_op(*ops):
            return self.advance().value
        return None

    def expect_op(self, op: str) -> None:
        if not self.accept_op(op):
            raise self.error(f"Esperado '{op}'")

    def identifier(self, what: str = "um nome") -> str:
        token = self.current
        if token.kind == "quoted" or (token.kind == "name" and token.keyword is None):
            self.advance()
            return token.value
        raise self.error(f"Esperado {what}")

    # -- instruções ------------------------------------------------------
    def parse(self) -> ParsedQuery:
        keyword = self.current.keyword
        if keyword == "SELECT":
            statement = self.select()
        elif keyword == "INSERT":
            statement = self.insert()
        elif keyword == "UPDATE":
            statement = self.update()
        elif keyword == "DELETE":
            statement = self.delete()
        else:
            raise self.error("A query precisa começar com SELECT, INSERT, UPDATE ou DELETE")
        self.accept_op(";")
        if self.current.kind != "eof":
            raise self.error("Esperado o fim da query (só uma instrução por arquivo)")
        return ParsedQuery(statement=statement, params=list(self.params))

    def select(self) -> Select:
        self.expect_keyword("SELECT")
        columns: Optional[List[Column]] = None
        count: Optional[str] = None
        if self.accept_op("*"):
            pass
        elif self.at_keyword("COUNT"):
            self.advance()
            self.expect_op("(")
            self.expect_op("*")
            self.expect_op(")")
            count = self.identifier("o apelido da contagem") if self.accept_keyword("AS") else "count"
        else:
            columns = [self.column()]
            while self.accept_op(","):
                columns.append(self.column())
        self.expect_keyword("FROM")
        statement = Select(collection=self.identifier("o nome do banco"), columns=columns, count=count)
        if self.accept_keyword("WHERE"):
            statement.where = self.expression()
        if self.accept_keyword("ORDER"):
            self.expect_keyword("BY")
            statement.order.append(self.order_item())
            while self.accept_op(","):
                statement.order.append(self.order_item())
        if self.accept_keyword("LIMIT"):
            statement.limit = self.value()
        if self.accept_keyword("OFFSET"):
            statement.offset = self.value()
        return statement

    def column(self) -> Column:
        path = self.identifier("o nome de uma coluna")
        alias = None
        if self.accept_keyword("AS"):
            alias = self.identifier("o apelido da coluna")
        elif self.current.kind in ("name", "quoted") and self.current.keyword is None:
            alias = self.identifier()
        return Column(path=path, alias=alias)

    def order_item(self) -> Tuple[str, int]:
        path = self.identifier("o nome de uma coluna")
        direction = self.accept_keyword("ASC", "DESC")
        return path, -1 if direction == "DESC" else 1

    def insert(self) -> Insert:
        self.expect_keyword("INSERT")
        self.expect_keyword("INTO")
        collection = self.identifier("o nome do banco")
        self.expect_op("(")
        columns = [self.identifier("o nome de uma coluna")]
        while self.accept_op(","):
            columns.append(self.identifier("o nome de uma coluna"))
        self.expect_op(")")
        self.expect_keyword("VALUES")
        rows = [self.row(len(columns))]
        while self.accept_op(","):
            rows.append(self.row(len(columns)))
        return Insert(collection=collection, columns=columns, rows=rows)

    def row(self, size: int) -> List[Operand]:
        start = self.current
        self.expect_op("(")
        values = [self.value()]
        while self.accept_op(","):
            values.append(self.value())
        self.expect_op(")")
        if len(values) != size:
            raise QueryError(
                f"VALUES com {len(values)} valor(es), mas a lista de colunas tem {size} "
                f"{_where(self.text, start.pos)}"
            )
        return values

    def update(self) -> Update:
        self.expect_keyword("UPDATE")
        collection = self.identifier("o nome do banco")
        self.expect_keyword("SET")
        assignments = [self.assignment()]
        while self.accept_op(","):
            assignments.append(self.assignment())
        where = self.expression() if self.accept_keyword("WHERE") else None
        return Update(collection=collection, assignments=assignments, where=where)

    def assignment(self) -> Assignment:
        path = self.identifier("o nome de uma coluna")
        self.expect_op("=")
        token = self.current
        if token.kind in ("name", "quoted") and token.keyword is None:
            source = self.identifier()
            operator = self.accept_op("+", "-")
            if source != path or operator is None:
                raise QueryError(
                    f"Em SET só é possível usar o próprio campo para incrementar "
                    f"('{path} = {path} + 1') {_where(self.text, token.pos)}"
                )
            return Assignment(path=path, value=self.value(), kind="inc", sign=1 if operator == "+" else -1)
        return Assignment(path=path, value=self.value())

    def delete(self) -> Delete:
        self.expect_keyword("DELETE")
        self.expect_keyword("FROM")
        collection = self.identifier("o nome do banco")
        where = self.expression() if self.accept_keyword("WHERE") else None
        return Delete(collection=collection, where=where)

    # -- expressões ------------------------------------------------------
    def expression(self) -> Any:
        items = [self.conjunction()]
        while self.accept_keyword("OR"):
            items.append(self.conjunction())
        return items[0] if len(items) == 1 else Or(items)

    def conjunction(self) -> Any:
        items = [self.negation()]
        while self.accept_keyword("AND"):
            items.append(self.negation())
        return items[0] if len(items) == 1 else And(items)

    def negation(self) -> Any:
        if self.accept_keyword("NOT"):
            return Not(self.negation())
        return self.predicate()

    def predicate(self) -> Any:
        if self.accept_op("("):
            inner = self.expression()
            self.expect_op(")")
            return inner
        left = self.operand()
        op = self.accept_op("=", "==", "!=", "<>", "<", "<=", ">", ">=")
        if op:
            op = {"==": "=", "<>": "!="}.get(op, op)
            return Compare(left, op, self.operand())
        if self.accept_keyword("IS"):
            negate = bool(self.accept_keyword("NOT"))
            self.expect_keyword("NULL")
            return IsNull(left, negate)
        negate = bool(self.accept_keyword("NOT"))
        if self.accept_keyword("LIKE", "ILIKE"):
            return Like(left, self.operand(), negate)
        if self.accept_keyword("IN"):
            if self.current.kind == "param":
                return In(left, self.value(), negate)
            self.expect_op("(")
            values = [self.value()]
            while self.accept_op(","):
                values.append(self.value())
            self.expect_op(")")
            return In(left, values, negate)
        if self.accept_keyword("BETWEEN"):
            low = self.operand()
            self.expect_keyword("AND")
            return Between(left, low, self.operand(), negate)
        if negate:
            raise self.error("Esperado LIKE, IN ou BETWEEN depois de NOT")
        # ``WHERE active`` equivale a ``WHERE active = true``
        if isinstance(left, Field):
            return Compare(left, "=", Const(True))
        return left

    def operand(self) -> Operand:
        token = self.current
        if token.kind in ("name", "quoted") and token.keyword is None:
            return Field(self.identifier())
        return self.value()

    def value(self) -> Union[Const, Param]:
        token = self.current
        if token.kind == "param":
            self.advance()
            if token.value not in self.params:
                self.params.append(token.value)
            return Param(token.value)
        if token.kind in ("string", "number"):
            self.advance()
            return Const(token.value)
        if self.accept_op("-"):
            number = self.current
            if number.kind != "number":
                raise self.error("Esperado um número depois de '-'")
            self.advance()
            return Const(-number.value)
        keyword = token.keyword
        if keyword in ("TRUE", "FALSE", "NULL"):
            self.advance()
            return Const({"TRUE": True, "FALSE": False, "NULL": None}[keyword])
        raise self.error("Esperado um valor (número, 'texto', true, false, null ou :parametro)")


def parse(text: str) -> ParsedQuery:
    """Interpreta o texto de uma query; levanta :class:`QueryError` se inválido."""
    return Parser(text).parse()


# ---------------------------------------------------------------------------
# Tradução para filtros do MongoDB
# ---------------------------------------------------------------------------

#: filtro que não casa com nenhum documento
MATCH_NOTHING: Dict[str, Any] = {"_id": {"$in": []}}

_MONGO_OPS = {"=": "$eq", "!=": "$ne", "<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte"}
_FLIPPED = {"=": "=", "!=": "!=", "<": ">", "<=": ">=", ">": "<", ">=": "<="}

def resolve(node: Operand, params: Mapping[str, Any]) -> Any:
    """Valor de uma constante ou parâmetro."""
    if isinstance(node, Const):
        return node.value
    if isinstance(node, Param):
        return params.get(node.name)
    raise QueryError(f"Esperado um valor, mas '{node.path}' é um campo")


def build_filter(node: Any, params: Mapping[str, Any]) -> Dict[str, Any]:
    """Traduz o ``WHERE`` (já com os parâmetros) em um filtro do MongoDB."""
    if node is None:
        return {}
    result = _translate(node, params)
    if result is True:
        return {}
    if result is False:
        return dict(MATCH_NOTHING)
    return result


def _translate(node: Any, params: Mapping[str, Any]) -> Union[bool, Dict[str, Any]]:
    if isinstance(node, And):
        parts = []
        for item in node.items:
            result = _translate(item, params)
            if result is False:
                return False
            if result is not True:
                parts.append(result)
        if not parts:
            return True
        return parts[0] if len(parts) == 1 else {"$and": parts}

    if isinstance(node, Or):
        parts = []
        for item in node.items:
            result = _translate(item, params)
            if result is True:
                return True
            if result is not False:
                parts.append(result)
        if not parts:
            return False
        return parts[0] if len(parts) == 1 else {"$or": parts}

    if isinstance(node, Not):
        result = _translate(node.item, params)
        if isinstance(result, bool):
            return not result
        return {"$nor": [result]}

    if isinstance(node, Compare):
        return _compare(node, params)

    if isinstance(node, IsNull):
        if isinstance(node.operand, Field):
            condition = {"$ne": None} if node.negate else None
            return {node.operand.path: condition}
        is_null = resolve(node.operand, params) is None
        return is_null != node.negate

    if isinstance(node, Like):
        pattern = resolve(node.pattern, params)
        if pattern is None:
            return False
        regex = like_to_regex(str(pattern))
        if isinstance(node.operand, Field):
            condition = {node.operand.path: {"$regex": regex, "$options": "i"}}
            return {"$nor": [condition]} if node.negate else condition
        value = resolve(node.operand, params)
        matched = value is not None and re.search(regex, str(value), re.I) is not None
        return matched != node.negate

    if isinstance(node, In):
        values = _in_values(node.values, params)
        if isinstance(node.operand, Field):
            return {node.operand.path: {"$nin" if node.negate else "$in": values}}
        return (resolve(node.operand, params) in values) != node.negate

    if isinstance(node, Between):
        low, high = resolve(node.low, params), resolve(node.high, params)
        if isinstance(node.operand, Field):
            condition = {node.operand.path: {"$gte": low, "$lte": high}}
            return {"$nor": [condition]} if node.negate else condition
        value = resolve(node.operand, params)
        inside = _safe_compare(value, ">=", low) and _safe_compare(value, "<=", high)
        return inside != node.negate

    if isinstance(node, (Const, Param)):
        return bool(resolve(node, params))

    raise QueryError(f"Expressão não suportada no WHERE: {node!r}")  # pragma: no cover


def _compare(node: Compare, params: Mapping[str, Any]) -> Union[bool, Dict[str, Any]]:
    left, op, right = node.left, node.op, node.right
    if isinstance(left, Field) and isinstance(right, Field):
        raise QueryError(
            f"Comparar dois campos ('{left.path}' e '{right.path}') não é suportado"
        )
    if isinstance(right, Field):
        left, right, op = right, left, _FLIPPED[op]
    if isinstance(left, Field):
        return {left.path: {_MONGO_OPS[op]: resolve(right, params)}}
    return _safe_compare(resolve(left, params), op, resolve(right, params))


def _safe_compare(left: Any, op: str, right: Any) -> bool:
    if op == "=":
        return left == right
    if op == "!=":
        return left != right
    try:
        return {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[op]
    except TypeError:  # None ou tipos incompatíveis: como no SQL, não casa
        return False


def _in_values(values: Union[List[Operand], Param], params: Mapping[str, Any]) -> List[Any]:
    if isinstance(values, Param):
        value = params.get(values.name)
        if value is None:
            return []
        return list(value) if isinstance(value, (list, tuple, set)) else [value]
    return [resolve(item, params) for item in values]


def like_to_regex(pattern: str) -> str:
    """``'ba%'`` -> ``'^ba.*$'`` (``%`` = qualquer sequência, ``_`` = um caractere)."""
    parts = []
    for char in pattern:
        if char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    return "^" + "".join(parts) + "$"
