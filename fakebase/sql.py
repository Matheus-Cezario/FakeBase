"""SQL subset translated into the MongoDB dialect.

Used by custom queries (``.sql`` files in the queries folder). Supports one
statement per file:

* ``SELECT * | col [AS alias], ... | COUNT(*) [AS alias] FROM database
  [WHERE ...] [ORDER BY col [ASC|DESC], ...] [LIMIT n] [OFFSET n]``
* ``INSERT INTO database (col, ...) VALUES (value, ...), (...)``
* ``UPDATE database SET col = value, col = col + value [WHERE ...]``
* ``DELETE FROM database [WHERE ...]``

In ``WHERE``: ``= != <> < <= > >=``, ``[NOT] LIKE`` / ``ILIKE`` (``%`` and
``_``), ``[NOT] IN (...)`` or ``IN :list``, ``[NOT] BETWEEN a AND b``,
``IS [NOT] NULL``, ``AND``, ``OR``, ``NOT`` and parentheses.

Named parameters (``:name``) are resolved before translation, so conditions
that only involve parameters become constants. This allows optional filters
such as ``(:name IS NULL OR name = :name)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .errors import QueryError

# ---------------------------------------------------------------------------
# Syntax tree
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
    #: ``"set"`` (``col = value``) or ``"inc"`` (``col = col + value``)
    kind: str = "set"
    sign: int = 1


@dataclass
class Select:
    collection: str
    columns: Optional[List[Column]] = None  # None = SELECT *
    count: Optional[str] = None  # key name for COUNT(*)
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
    #: parameters in order of appearance, without repetition
    params: List[str]


# ---------------------------------------------------------------------------
# Lexical analysis
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
            raise QueryError(f"Unexpected character {text[pos]!r} {_where(text, pos)}")
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
    return f"(line {line}, column {column})"


# ---------------------------------------------------------------------------
# Parsing
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
        found = "end of query" if token.kind == "eof" else repr(str(token.value))
        return QueryError(f"{message}, found {found} {_where(self.text, token.pos)}")

    def at_keyword(self, *words: str) -> bool:
        return self.current.keyword in words

    def accept_keyword(self, *words: str) -> Optional[str]:
        if self.at_keyword(*words):
            return self.advance().keyword
        return None

    def expect_keyword(self, word: str) -> None:
        if not self.accept_keyword(word):
            raise self.error(f"Expected {word}")

    def at_op(self, *ops: str) -> bool:
        return self.current.kind == "op" and self.current.value in ops

    def accept_op(self, *ops: str) -> Optional[str]:
        if self.at_op(*ops):
            return self.advance().value
        return None

    def expect_op(self, op: str) -> None:
        if not self.accept_op(op):
            raise self.error(f"Expected '{op}'")

    def identifier(self, what: str = "a name") -> str:
        token = self.current
        if token.kind == "quoted" or (token.kind == "name" and token.keyword is None):
            self.advance()
            return token.value
        raise self.error(f"Expected {what}")

    # -- statements ------------------------------------------------------
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
            raise self.error("The query must start with SELECT, INSERT, UPDATE or DELETE")
        self.accept_op(";")
        if self.current.kind != "eof":
            raise self.error("Expected the end of the query (only one statement per file)")
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
            count = self.identifier("the count alias") if self.accept_keyword("AS") else "count"
        else:
            columns = [self.column()]
            while self.accept_op(","):
                columns.append(self.column())
        self.expect_keyword("FROM")
        statement = Select(collection=self.identifier("the database name"), columns=columns, count=count)
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
        path = self.identifier("a column name")
        alias = None
        if self.accept_keyword("AS"):
            alias = self.identifier("the column alias")
        elif self.current.kind in ("name", "quoted") and self.current.keyword is None:
            alias = self.identifier()
        return Column(path=path, alias=alias)

    def order_item(self) -> Tuple[str, int]:
        path = self.identifier("a column name")
        direction = self.accept_keyword("ASC", "DESC")
        return path, -1 if direction == "DESC" else 1

    def insert(self) -> Insert:
        self.expect_keyword("INSERT")
        self.expect_keyword("INTO")
        collection = self.identifier("the database name")
        self.expect_op("(")
        columns = [self.identifier("a column name")]
        while self.accept_op(","):
            columns.append(self.identifier("a column name"))
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
                f"VALUES has {len(values)} value(s), but the column list has {size} "
                f"{_where(self.text, start.pos)}"
            )
        return values

    def update(self) -> Update:
        self.expect_keyword("UPDATE")
        collection = self.identifier("the database name")
        self.expect_keyword("SET")
        assignments = [self.assignment()]
        while self.accept_op(","):
            assignments.append(self.assignment())
        where = self.expression() if self.accept_keyword("WHERE") else None
        return Update(collection=collection, assignments=assignments, where=where)

    def assignment(self) -> Assignment:
        path = self.identifier("a column name")
        self.expect_op("=")
        token = self.current
        if token.kind in ("name", "quoted") and token.keyword is None:
            source = self.identifier()
            operator = self.accept_op("+", "-")
            if source != path or operator is None:
                raise QueryError(
                    f"In SET only the field itself can be used to increment it "
                    f"('{path} = {path} + 1') {_where(self.text, token.pos)}"
                )
            return Assignment(path=path, value=self.value(), kind="inc", sign=1 if operator == "+" else -1)
        return Assignment(path=path, value=self.value())

    def delete(self) -> Delete:
        self.expect_keyword("DELETE")
        self.expect_keyword("FROM")
        collection = self.identifier("the database name")
        where = self.expression() if self.accept_keyword("WHERE") else None
        return Delete(collection=collection, where=where)

    # -- expressions ------------------------------------------------------
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
            raise self.error("Expected LIKE, IN or BETWEEN after NOT")
        # ``WHERE active`` is the same as ``WHERE active = true``
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
                raise self.error("Expected a number after '-'")
            self.advance()
            return Const(-number.value)
        keyword = token.keyword
        if keyword in ("TRUE", "FALSE", "NULL"):
            self.advance()
            return Const({"TRUE": True, "FALSE": False, "NULL": None}[keyword])
        raise self.error("Expected a value (number, 'text', true, false, null or :parameter)")


def parse(text: str) -> ParsedQuery:
    """Parse the text of a query; raise :class:`QueryError` if invalid."""
    return Parser(text).parse()


# ---------------------------------------------------------------------------
# Translation into MongoDB filters
# ---------------------------------------------------------------------------

#: filter that matches no document
MATCH_NOTHING: Dict[str, Any] = {"_id": {"$in": []}}

_MONGO_OPS = {"=": "$eq", "!=": "$ne", "<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte"}
_FLIPPED = {"=": "=", "!=": "!=", "<": ">", "<=": ">=", ">": "<", ">=": "<="}

def resolve(node: Operand, params: Mapping[str, Any]) -> Any:
    """Value of a constant or parameter."""
    if isinstance(node, Const):
        return node.value
    if isinstance(node, Param):
        return params.get(node.name)
    raise QueryError(f"Expected a value, but '{node.path}' is a field")


def build_filter(node: Any, params: Mapping[str, Any]) -> Dict[str, Any]:
    """Translate ``WHERE`` (with the parameters bound) into a MongoDB filter."""
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

    raise QueryError(f"Unsupported expression in WHERE: {node!r}")  # pragma: no cover


def _compare(node: Compare, params: Mapping[str, Any]) -> Union[bool, Dict[str, Any]]:
    left, op, right = node.left, node.op, node.right
    if isinstance(left, Field) and isinstance(right, Field):
        raise QueryError(
            f"Comparing two fields ('{left.path}' and '{right.path}') is not supported"
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
    except TypeError:  # None or incompatible types: as in SQL, no match
        return False


def _in_values(values: Union[List[Operand], Param], params: Mapping[str, Any]) -> List[Any]:
    if isinstance(values, Param):
        value = params.get(values.name)
        if value is None:
            return []
        return list(value) if isinstance(value, (list, tuple, set)) else [value]
    return [resolve(item, params) for item in values]


def like_to_regex(pattern: str) -> str:
    """``'ba%'`` -> ``'^ba.*$'`` (``%`` = any sequence, ``_`` = one character)."""
    parts = []
    for char in pattern:
        if char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    return "^" + "".join(parts) + "$"
