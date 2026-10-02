import pytest

from fakebase.errors import QueryError
from fakebase.sql import MATCH_NOTHING, Insert, Select, Update, build_filter, like_to_regex, parse


def where(text, **params):
    statement = parse(f"SELECT * FROM users WHERE {text}").statement
    return build_filter(statement.where, params)


def test_full_select():
    query = parse(
        "SELECT name, address.city AS city FROM users "
        "WHERE age >= :age ORDER BY age DESC, name LIMIT :limit OFFSET 5;"
    )
    statement = query.statement
    assert isinstance(statement, Select)
    assert statement.collection == "users"
    assert [(c.path, c.alias) for c in statement.columns] == [("name", None), ("address.city", "city")]
    assert statement.order == [("age", -1), ("name", 1)]
    assert query.params == ["age", "limit"]


def test_comparisons_become_mongo_operators():
    assert where("age > 30") == {"age": {"$gt": 30}}
    assert where("30 < age") == {"age": {"$gt": 30}}
    assert where("name <> 'Ana'") == {"name": {"$ne": "Ana"}}
    assert where("active") == {"active": {"$eq": True}}


def test_and_or_not_and_parentheses():
    assert where("age > 1 AND (name = 'a' OR name = 'b')") == {
        "$and": [
            {"age": {"$gt": 1}},
            {"$or": [{"name": {"$eq": "a"}}, {"name": {"$eq": "b"}}]},
        ]
    }
    assert where("NOT age > 1") == {"$nor": [{"age": {"$gt": 1}}]}


def test_like_in_between_is_null():
    assert where("name LIKE 'ba%'") == {"name": {"$regex": "^ba.*$", "$options": "i"}}
    assert where("tag IN ('a', 'b')") == {"tag": {"$in": ["a", "b"]}}
    assert where("tag NOT IN :tags", tags=[1, 2]) == {"tag": {"$nin": [1, 2]}}
    assert where("price BETWEEN 1 AND 5") == {"price": {"$gte": 1, "$lte": 5}}
    assert where("email IS NULL") == {"email": None}
    assert where("email IS NOT NULL") == {"email": {"$ne": None}}


def test_params_allow_optional_filters():
    text = "(:name IS NULL OR name = :name) AND (:age IS NULL OR age >= :age)"
    assert where(text, name=None, age=None) == {}
    assert where(text, name="Ana", age=None) == {"name": {"$eq": "Ana"}}
    assert where("1 = 2") == MATCH_NOTHING


def test_insert_and_update():
    insert = parse("INSERT INTO users (name, age) VALUES (:name, 30), ('Bia', -1)").statement
    assert isinstance(insert, Insert)
    assert insert.columns == ["name", "age"]
    assert len(insert.rows) == 2

    update = parse("UPDATE products SET stock = stock - :qty, name = 'x' WHERE _id = :id").statement
    assert isinstance(update, Update)
    assert [(a.path, a.kind, a.sign) for a in update.assignments] == [("stock", "inc", -1), ("name", "set", 1)]


def test_like_to_regex_escapes_the_rest():
    assert like_to_regex("a.b_%") == r"^a\.b..*$"


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("SELEC * FROM x", "SELECT, INSERT, UPDATE or DELETE"),
        ("SELECT * FROM users WHERE", "Expected a value"),
        ("SELECT * FROM users; DELETE FROM users", "only one statement"),
        ("INSERT INTO users (a, b) VALUES (1)", "column list has 2"),
        ("UPDATE users SET a = b + 1", "field itself"),
        ("SELECT * FROM users WHERE a = b", "two fields"),
    ],
)
def test_errors_explain_the_problem(text, fragment):
    with pytest.raises(QueryError, match=fragment):
        statement = parse(text).statement
        build_filter(getattr(statement, "where", None), {})
