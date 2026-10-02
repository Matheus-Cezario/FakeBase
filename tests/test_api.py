def test_index_lists_the_databases(client):
    body = client.get("/").json()
    assert body["dataBase"] == ["users", "products"]
    assert body["storage"]["backend"] == "memory"
    assert {d["name"]: d["count"] for d in body["databases"]} == {"users": 6, "products": 10}


def test_simple_listing_returns_array(client):
    response = client.get("/products")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert response.headers["x-total-count"] == "10"


def test_listing_with_filter_sort_projection_and_limit(client):
    documents = client.get(
        "/products", params={"price__gt": 20, "sort": "-price", "fields": "name,price", "limit": 3}
    ).json()
    assert len(documents) <= 3
    assert all(set(d) == {"_id", "name", "price"} for d in documents)
    prices = [d["price"] for d in documents]
    assert prices == sorted(prices, reverse=True) and all(p > 20 for p in prices)


def test_pagination_returns_envelope(client):
    body = client.get("/products", params={"paginate": "true", "pageCount": 4, "page": 2}).json()
    assert body["totalItens"] == 10 and body["totalPages"] == 3
    assert body["page"] == 2 and len(body["value"]) == 4


def test_get_by_id_and_404(client):
    document = client.get("/users", params={"limit": 1}).json()[0]
    assert client.get(f"/users/{document['_id']}").json()["_id"] == document["_id"]
    assert client.get("/users/nao-existe").status_code == 404


def test_post_fills_missing_fields(client):
    created = client.post("/users", json={"name": "Ana"}).json()
    assert created["name"] == "Ana"
    assert {"email", "age", "gender", "cart", "_id"} <= set(created)
    assert client.get(f"/users/{created['_id']}").json()["name"] == "Ana"


def test_post_without_fill(client):
    created = client.post("/users", params={"fill": "false"}, json={"name": "Bob"}).json()
    assert set(created) == {"name", "_id"}


def test_batch_post(client):
    created_items = client.post("/products", json=[{"name": "A"}, {"name": "B"}]).json()
    assert [c["name"] for c in created_items] == ["A", "B"]
    assert client.get("/products/_count").json()["count"] == 12


def test_patch_put_delete_by_id(client):
    document = client.get("/users", params={"limit": 1}).json()[0]
    updated = client.patch(f"/users/{document['_id']}", json={"age": 50}).json()
    assert updated["age"] == 50 and updated["name"] == document["name"]

    replaced = client.put(f"/users/{document['_id']}", json={"name": "Just this"}).json()
    assert replaced == {"_id": document["_id"], "name": "Just this"}

    assert client.delete(f"/users/{document['_id']}").status_code == 200
    assert client.get(f"/users/{document['_id']}").status_code == 404


def test_batch_operations_require_a_filter(client):
    assert client.delete("/users").status_code == 400
    assert client.patch("/users", json={"active": False}).status_code == 400


def test_batch_patch_by_filter(client):
    updated_items = client.patch("/products", params={"price__lt": 1000}, json={"stock": 0}).json()
    assert len(updated_items) == 10 and all(d["stock"] == 0 for d in updated_items)


def test_count_and_distinct(client):
    assert client.get("/users/_count").json()["count"] == 6
    body = client.get("/users/_distinct/gender").json()
    assert set(body["values"]) <= {"male", "female"}


def test_generate_appends_documents(client):
    body = client.post("/products/_generate", params={"count": 5}).json()
    assert body["created"] == 5
    assert client.get("/products/_count").json()["count"] == 15


def test_reset_regenerates_the_database(client):
    client.delete("/products", params={"price__gt": 0})
    body = client.post("/products/_reset").json()
    assert body["databases"][0]["size"] == 10
    assert client.get("/products/_count").json()["count"] == 10


def test_schema_and_stats(client):
    schema = client.get("/_schema/users").json()
    assert schema["fields"]["email"]["unique"] is True
    assert client.get("/_stats").json()["databases"][0]["count"] == 6
    assert client.get("/_schema").json()["product"]["price"]["method"] == "number"


def test_generators_documents_the_catalog(client):
    body = client.get("/_generators").json()
    names = {g["name"] for g in body["generators"]}
    assert {"humanName", "number", "choice"} <= names
    assert any(t["name"] == "currency" for t in body["transforms"])


def test_errors_have_json_body(client):
    response = client.get("/missing")
    assert response.status_code == 404 and response.json()["type"] == "NotFoundError"
    assert client.get("/users", params={"age__zzz": 1}).status_code == 400


def test_openapi_available(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


# --- version 1.x routes ----------------------------------------------------------


def test_legacy_list(client):
    body = client.get("/list/users").json()
    assert body["totalItens"] == 6 and len(body["value"]) == 6


def test_legacy_list_with_pagination_and_filter(client):
    body = client.get(
        "/list/users", params={"paginate": "true", "pageCount": 2, "page": 1, "gender": "male"}
    ).json()
    assert len(body["value"]) <= 2 and body["pageCount"] == 2
    assert all(d["gender"] == "male" for d in body["value"])


def test_legacy_get(client):
    assert client.get("/get/users", params={"gender": "female"}).json()["gender"] == "female"
    assert client.get("/get/users", params={"gender": "xxx"}).json() == {}


def test_legacy_update_and_set(client):
    document = client.get("/get/users").json()
    updated = client.post("/update/users", params={"_id": document["_id"]}, json={"age": 33})
    assert updated.json()[0]["age"] == 33

    replaced = client.post("/set/users", params={"_id": document["_id"]}, json={"name": "Joe"})
    assert replaced.json()[0] == {"_id": document["_id"], "name": "Joe"}


def test_legacy_delete_with_every(client):
    deleted = client.get("/delete/users", params={"gender": "male", "every": "true"}).json()
    assert all(d["gender"] == "male" for d in deleted)
    assert client.get("/users/_count", params={"gender": "male"}).json()["count"] == 0


def test_legacy_delete_without_filter_does_not_delete(client):
    assert client.get("/delete/users").status_code == 400
    assert client.get("/users/_count").json()["count"] == 6
