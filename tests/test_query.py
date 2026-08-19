import pytest

from fakebase.errors import QueryError
from fakebase.query import (
    ListOptions,
    build_filter,
    coerce,
    parse_conditions,
    parse_projection,
    parse_sort,
)


@pytest.mark.parametrize(
    "raw,expected",
    [("10", 10), ("1.5", 1.5), ("true", True), ("false", False), ("null", None), ("ab", "ab")],
)
def test_coerce_detecta_tipos(raw, expected):
    assert coerce(raw) == expected


def test_build_filter_com_operadores():
    assert build_filter({"price__gt": "40"}) == {"price": {"$gt": 40}}
    assert build_filter({"tag__in": "a,b"}) == {"tag": {"$in": ["a", "b"]}}
    assert build_filter({"name__start": "Ba"})["name"]["$regex"] == "^Ba"
    assert build_filter({"age": "30"}) == {"age": 30}


def test_build_filter_ignora_parametros_reservados():
    assert build_filter({"sort": "-price", "limit": "5", "paginate": "true"}) == {}


def test_build_filter_combina_repeticoes_do_mesmo_campo():
    result = build_filter({"price__gt": ["10", "20"]})
    assert result == {"$and": [{"price": {"$gt": 10}}, {"price": {"$gt": 20}}]}


def test_build_filter_rejeita_operador_desconhecido():
    with pytest.raises(QueryError):
        build_filter({"price__maior": "10"})


def test_parse_sort_e_projection():
    assert parse_sort("-price,name") == [("price", -1), ("name", 1)]
    assert parse_projection("name,price") == {"name": 1, "price": 1, "_id": 1}
    assert parse_projection(None, "cart") == {"cart": 0}


def test_parse_conditions_and_or():
    assert parse_conditions("price<40") == {"price": {"$lt": 40}}
    assert parse_conditions("price<40 and stock>0") == {
        "$and": [{"price": {"$lt": 40}}, {"stock": {"$gt": 0}}]
    }
    assert "$or" in parse_conditions("price<40 or stock>0")
    assert parse_conditions("None") == {}
    assert parse_conditions(None) == {}


def test_parse_conditions_contem():
    assert parse_conditions("name~=bata")["name"]["$options"] == "i"


def test_parse_conditions_invalida():
    with pytest.raises(QueryError):
        parse_conditions("preco muito alto")


def test_list_options_paginacao():
    options = ListOptions.from_query({"paginate": "true", "page": "3", "pageCount": "5"})
    assert (options.limit, options.skip) == (5, 10)
    options = ListOptions.from_query({"limit": "7", "skip": "2"})
    assert (options.limit, options.skip, options.paginate) == (7, 2, False)
