import json

import pytest

from fakebase.config import Config
from fakebase.errors import ConfigError, LinkError, NotFoundError
from fakebase.manager import FakeBase
from fakebase.query import ListOptions
from fakebase.references import parse_reference

from conftest import BASE_CONFIG, build_config


def test_generation_order_follows_references(fakebase):
    assert fakebase.generation_order() == ["products", "users"]


def test_generation_creates_documents(fakebase):
    assert fakebase.count("users") == 6
    assert fakebase.count("products") == 10


def test_cross_database_reference_brings_real_data(fakebase):
    prices = {p["price"] for p in fakebase.storage.find("products", {})}
    for user in fakebase.storage.find("users", {}):
        for item in user["cart"]:
            assert set(item) == {"name", "price"}
            assert item["price"] < 50 and item["price"] in prices


def test_seed_makes_generation_reproducible(tmp_path):
    def generate():
        instance = FakeBase(build_config(tmp_path))
        instance.generate()
        documents = instance.storage.find("users", {})
        instance.close()
        return json.dumps(documents, sort_keys=True, default=str)

    assert generate() == generate()


def test_different_seeds_generate_different_data(tmp_path):
    def generate(seed):
        instance = FakeBase(build_config(tmp_path, seed=seed))
        instance.generate()
        documents = instance.storage.find("users", {})
        instance.close()
        return json.dumps(documents, sort_keys=True, default=str)

    assert generate(1) != generate(2)


def test_unique_field_does_not_repeat(fakebase):
    emails = [u["email"] for u in fakebase.storage.find("users", {})]
    assert len(emails) == len(set(emails))


def test_append_resumes_counter_and_uniqueness(fakebase):
    before = fakebase.storage.find("users", {})
    fakebase.append("users", 4)
    after = fakebase.storage.find("users", {})
    assert len(after) == len(before) + 4
    assert len({d["_id"] for d in after}) == len(after)
    assert len({d["seq"] for d in after}) == len(after)


def test_preview_does_not_store(fakebase):
    before = fakebase.count("products")
    assert len(fakebase.preview("products", 3)) == 3
    assert fakebase.count("products") == before


def test_size_limited_by_no_repeat_generator(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["tag"] = {"name": {"method": "choice", "data": ["a", "b", "c"], "repeat": False}}
    raw["DataBase"]["tags"] = {"schema": "tag", "size": 99}
    config = Config.from_dict(raw, path=tmp_path / "c.json")
    instance = FakeBase(config)
    report = instance.generate()
    tags = next(item for item in report.databases if item.name == "tags")
    assert tags.size == 3 and tags.notes
    instance.close()


def test_size_range(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["DataBase"]["users"] = {"schema": "user", "size": [3, 5]}
    instance = FakeBase(Config.from_dict(raw, path=tmp_path / "c.json"))
    report = instance.generate()
    users = next(item for item in report.databases if item.name == "users")
    assert 3 <= users.size <= 5
    instance.close()


def test_full_crud(fakebase):
    created = fakebase.create("users", {"name": "John"})
    assert created["name"] == "John" and "email" in created

    updated = fakebase.update("users", {"_id": created["_id"]}, {"age": 41})
    assert updated[0]["age"] == 41 and updated[0]["name"] == "John"

    replaced = fakebase.replace("users", {"_id": created["_id"]}, {"name": "Other"})
    assert replaced[0] == {"_id": created["_id"], "name": "Other"}

    deleted = fakebase.delete("users", {"_id": created["_id"]})
    assert deleted[0]["name"] == "Other"
    assert fakebase.get_by_id("users", created["_id"]) is None


def test_update_does_not_change_the_id(fakebase):
    document = fakebase.storage.find("users", {}, limit=1)[0]
    fakebase.update("users", {"_id": document["_id"]}, {"_id": "hacked", "age": 30})
    assert fakebase.get_by_id("users", "hacked") is None
    assert fakebase.get_by_id("users", document["_id"])["age"] == 30


def test_delete_without_every_affects_one_document(fakebase):
    before = fakebase.count("users")
    deleted = fakebase.delete("users", {}, every=False)
    assert len(deleted) == 1 and fakebase.count("users") == before - 1


def test_list_with_filter_sort_and_page(fakebase):
    options = ListOptions.from_query({"sort": "-price", "paginate": "true", "pageCount": "4"})
    documents, total = fakebase.list("products", options)
    assert total == 10 and len(documents) == 4
    prices = [d["price"] for d in documents]
    assert prices == sorted(prices, reverse=True)


def test_missing_database(fakebase):
    with pytest.raises(NotFoundError):
        fakebase.count("missing")


def test_export_and_import(fakebase, tmp_path):
    target = tmp_path / "output"
    files = fakebase.export(target)
    assert {p.name for p in files} == {"users.json", "products.json"}
    content = json.loads((target / "users.json").read_text(encoding="utf-8"))
    assert len(content["users"]) == 6

    fakebase.storage.drop("users")
    assert fakebase.count("users") == 0
    loaded = fakebase.import_json(target / "users.json")
    assert loaded == {"users": 6}
    assert fakebase.count("users") == 6


def test_stats_lists_every_database(fakebase):
    stats = fakebase.stats()
    assert {d["name"] for d in stats["databases"]} == {"users", "products"}
    assert all(d["generated"] for d in stats["databases"])


def test_circular_reference_between_databases(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["product"]["owner"] = {"method": "choice", "data": "@users:name@"}
    instance = FakeBase(Config.from_dict(raw, path=tmp_path / "c.json"))
    with pytest.raises(LinkError):
        instance.generation_order()
    instance.close()


def test_reference_to_missing_database(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["user"]["x"] = {"method": "choice", "data": "@ghost:name@"}
    with pytest.raises(ConfigError):
        Config.from_dict(raw, path=tmp_path / "c.json")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("@products@", ("products", None, None, None)),
        ("@products:name@", ("products", None, "name", None)),
        ("@products:[a,b]@", ("products", ["a", "b"], None, None)),
        ("@products:name:price<50@", ("products", None, "name", "price<50")),
    ],
)
def test_parse_reference(text, expected):
    reference = parse_reference(text)
    assert (
        reference.database,
        reference.fields,
        reference.single_field,
        reference.conditions,
    ) == expected


def test_parse_reference_count():
    assert parse_reference("@p:_id::3@").count == 3
    assert parse_reference("@p:_id::all@").count == "all"
    assert parse_reference("@p:_id::[1,4]@").count == (1, 4)
    with pytest.raises(LinkError):
        parse_reference("@p:_id::x@")


def test_append_honors_repeat_false(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["tag"] = {
        "name": {"method": "choice", "data": ["a", "b", "c", "d"], "repeat": False}
    }
    raw["DataBase"]["tags"] = {"schema": "tag", "size": 2}
    instance = FakeBase(Config.from_dict(raw, path=tmp_path / "c.json"))
    instance.generate()
    instance.append("tags", 2)
    names = [d["name"] for d in instance.storage.find("tags", {})]
    assert sorted(names) == ["a", "b", "c", "d"]
    instance.close()


def test_append_resumes_sequence(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["tag"] = {
        "name": {"method": "sequence", "data": ["a", "b", "c", "d"], "repeat": False}
    }
    raw["DataBase"]["tags"] = {"schema": "tag", "size": 2}
    instance = FakeBase(Config.from_dict(raw, path=tmp_path / "c.json"))
    instance.generate()
    instance.append("tags", 2)
    assert [d["name"] for d in instance.storage.find("tags", {})] == ["a", "b", "c", "d"]
    instance.close()
