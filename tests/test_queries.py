from pathlib import Path

import pytest

from fakebase.errors import ConfigError
from fakebase.manager import FakeBase
from fakebase.queries import load_queries, route_for

from conftest import build_config

QUERIES = {
    "products/cheap.sql": """
        -- GET Products below a price
        -- @param max number = 50
        -- @param limit int = 100
        SELECT name, price AS cost FROM products
        WHERE price < :max
        ORDER BY price
        LIMIT :limit
    """,
    "products/index.sql": """
        -- GET
        -- @param name = null
        SELECT * FROM products WHERE (:name IS NULL OR name LIKE :name)
    """,
    "products/index.create.sql": """
        -- POST
        INSERT INTO products (name, price) VALUES (:name, :price)
    """,
    "products/[id].sql": """
        -- GET
        -- @param id string
        -- @one
        SELECT * FROM products WHERE _id = :id
    """,
    "products/[id].stock.sql": """
        -- PUT
        -- @param id string
        -- @one
        UPDATE products SET stock = stock - :qty WHERE _id = :id
    """,
    "products/[id].delete.sql": """
        -- DELETE
        -- @param id string
        DELETE FROM products WHERE _id = :id
    """,
    "reports/users/total.sql": """
        -- GET
        SELECT COUNT(*) AS total FROM users WHERE age >= :age
    """,
}


def write_queries(root: Path, files) -> Path:
    folder = root / "queries"
    for name, text in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(line.strip() for line in text.strip().splitlines()), encoding="utf-8")
    return folder


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from fakebase.api import create_app

    write_queries(tmp_path, QUERIES)
    instance = FakeBase(build_config(tmp_path))
    instance.generate()
    with TestClient(create_app(instance)) as test_client:
        yield test_client
    instance.close()


def test_routes_follow_the_folders():
    assert route_for("a/b/c.sql") == ("/queries/a/b/c", [])
    assert route_for("users/index.sql") == ("/queries/users", [])
    assert route_for("users/[id].sql", prefix="") == ("/users/{id}", ["id"])
    assert route_for("index.sql", prefix="/") == ("/", [])


def test_get_with_default_params_and_aliases(client):
    documents = client.get("/queries/products/cheap").json()
    assert documents and all(set(d) == {"name", "cost"} for d in documents)
    assert all(d["cost"] < 50 for d in documents)
    assert [d["cost"] for d in documents] == sorted(d["cost"] for d in documents)

    few = client.get("/queries/products/cheap", params={"max": 90, "limit": 2}).json()
    assert len(few) == 2


def test_optional_filter(client):
    everything = client.get("/queries/products").json()
    assert len(everything) == 10
    name = everything[0]["name"]
    filtered = client.get("/queries/products", params={"name": name}).json()
    assert filtered and all(d["name"].lower() == name.lower() for d in filtered)


def test_post_inserts_and_get_by_id(client):
    response = client.post("/queries/products", json={"name": "New", "price": 12.5})
    assert response.status_code == 201
    created = response.json()["value"][0]
    assert created["name"] == "New" and "stock" in created  # missing fields are generated

    fetched = client.get(f"/queries/products/{created['_id']}").json()
    assert fetched["_id"] == created["_id"] and fetched["price"] == 12.5


def test_put_increments_and_delete_removes(client):
    product = client.get("/products", params={"limit": 1}).json()[0]
    updated = client.put(f"/queries/products/{product['_id']}", json={"qty": 1}).json()
    assert updated["stock"] == product["stock"] - 1

    deleted = client.delete(f"/queries/products/{product['_id']}").json()
    assert deleted["deleted"] == 1
    assert client.get(f"/queries/products/{product['_id']}").status_code == 404


def test_count_in_subfolder(client):
    body = client.get("/queries/reports/users/total", params={"age": 0}).json()
    assert body == {"total": 6}


def test_required_param_and_invalid_type(client):
    response = client.get("/queries/reports/users/total")
    assert response.status_code == 400 and "age" in response.json()["error"]
    response = client.get("/queries/products/cheap", params={"limit": "lots"})
    assert response.status_code == 400


def test_queries_show_up_in_index_and_swagger(client):
    assert {"method": "POST", "url": "/queries/products"} in client.get("/").json()["queries"]
    described = {(q["method"], q["url"]) for q in client.get("/_queries").json()}
    assert ("DELETE", "/queries/products/{id}") in described
    paths = client.get("/openapi.json").json()["paths"]
    assert "/queries/products/{id}" in paths
    parameters = paths["/queries/products/cheap"]["get"]["parameters"]
    assert {p["name"] for p in parameters} == {"max", "limit"}


def test_fixed_routes_before_parameterized_ones(tmp_path):
    folder = write_queries(
        tmp_path,
        {
            "users/[id].sql": "-- GET\nSELECT * FROM users WHERE _id = :id",
            "users/active.sql": "-- GET\nSELECT * FROM users WHERE active",
        },
    )
    routes = [e.route for e in load_queries(folder, databases=["users"])]
    assert routes == ["/queries/users/active", "/queries/users/{id}"]


@pytest.mark.parametrize(
    "files, fragment",
    [
        ({"a.sql": "SELECT * FROM users"}, "HTTP method"),
        ({"a.sql": "-- PATCH\nSELECT * FROM users"}, "HTTP method"),
        ({"a.sql": "-- GET\nSELECT * FROM nothing"}, "'nothing' does not exist"),
        ({"a.sql": "-- GET\nSELECT * FROM users WHERE"}, "a.sql"),
        ({"a.sql": "-- GET\n-- @param x\nSELECT * FROM users"}, "not used"),
        ({"a.sql": "-- GET\n-- @param x date\nSELECT * FROM users WHERE a = :x"}, "type 'date'"),
        (
            {"a.sql": "-- GET\nSELECT * FROM users", "a.other.sql": "-- GET\nSELECT * FROM users"},
            "same route",
        ),
        ({"with space.sql": "-- GET\nSELECT * FROM users"}, "cannot become part of the URL"),
    ],
)
def test_loading_errors(tmp_path, files, fragment):
    folder = write_queries(tmp_path, files)
    with pytest.raises(ConfigError, match=fragment):
        load_queries(folder, databases=["users"])


def test_missing_folder_yields_no_routes(tmp_path):
    assert load_queries(tmp_path / "nothing") == []
