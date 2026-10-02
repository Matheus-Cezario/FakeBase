import pytest

from fakebase.errors import QueryError
from fakebase.sql import MATCH_NOTHING, Insert, Select, Update, build_filter, like_to_regex, parse


def where(text, **params):
    statement = parse(f"SELECT * FROM users WHERE {text}").statement
    return build_filter(statement.where, params)


def test_select_completo():
    query = parse(
        "SELECT name, address.city AS cidade FROM users "
        "WHERE age >= :idade ORDER BY age DESC, name LIMIT :limite OFFSET 5;"
    )
    statement = query.statement
    assert isinstance(statement, Select)
    assert statement.collection == "users"
    assert [(c.path, c.alias) for c in statement.columns] == [("name", None), ("address.city", "cidade")]
    assert statement.order == [("age", -1), ("name", 1)]
    assert query.params == ["idade", "limite"]


def test_comparacoes_viram_operadores_do_mongo():
    assert where("age > 30") == {"age": {"$gt": 30}}
    assert where("30 < age") == {"age": {"$gt": 30}}
    assert where("name <> 'Ana'") == {"name": {"$ne": "Ana"}}
    assert where("active") == {"active": {"$eq": True}}


def test_and_or_not_e_parenteses():
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


def test_parametros_permitem_filtros_opcionais():
    texto = "(:nome IS NULL OR name = :nome) AND (:idade IS NULL OR age >= :idade)"
    assert where(texto, nome=None, idade=None) == {}
    assert where(texto, nome="Ana", idade=None) == {"name": {"$eq": "Ana"}}
    assert where("1 = 2") == MATCH_NOTHING


def test_insert_e_update():
    insert = parse("INSERT INTO users (name, age) VALUES (:nome, 30), ('Bia', -1)").statement
    assert isinstance(insert, Insert)
    assert insert.columns == ["name", "age"]
    assert len(insert.rows) == 2

    update = parse("UPDATE products SET stock = stock - :qtd, name = 'x' WHERE _id = :id").statement
    assert isinstance(update, Update)
    assert [(a.path, a.kind, a.sign) for a in update.assignments] == [("stock", "inc", -1), ("name", "set", 1)]


def test_like_to_regex_escapa_o_resto():
    assert like_to_regex("a.b_%") == r"^a\.b..*$"


@pytest.mark.parametrize(
    "texto, trecho",
    [
        ("SELEC * FROM x", "SELECT, INSERT, UPDATE ou DELETE"),
        ("SELECT * FROM users WHERE", "Esperado um valor"),
        ("SELECT * FROM users; DELETE FROM users", "só uma instrução"),
        ("INSERT INTO users (a, b) VALUES (1)", "lista de colunas tem 2"),
        ("UPDATE users SET a = b + 1", "próprio campo"),
        ("SELECT * FROM users WHERE a = b", "dois campos"),
    ],
)
def test_erros_explicam_o_problema(texto, trecho):
    with pytest.raises(QueryError, match=trecho):
        statement = parse(texto).statement
        build_filter(getattr(statement, "where", None), {})
