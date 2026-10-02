import random
from pathlib import Path

import pytest
from faker import Faker

from fakebase import pipes
from fakebase.errors import GeneratorError, SchemaError
from fakebase.generators import GenContext, available, get
from fakebase.schematic import Schematic


@pytest.fixture
def ctx(tmp_path):
    faker = Faker("pt_BR")
    faker.seed_instance(5)
    return GenContext(
        rng=random.Random(5), faker=faker, base_dir=Path(tmp_path), database="t", field_name="f"
    )


def test_registry_exposes_metadata():
    names = {spec.name for spec in available()}
    assert {"number", "humanName", "choice", "date", "object", "array"} <= names
    assert get("int") is get("integer")  # alias


def test_number_honors_bounds(ctx):
    for _ in range(50):
        value = get("number").call(ctx, {"start": 5, "stop": 10, "numberType": "int"})
        assert 5 <= value <= 10 and isinstance(value, int)


def test_params_may_come_as_text_from_json(ctx):
    value = get("integer").call(ctx, {"start": "1", "stop": "3"})
    assert 1 <= value <= 3


def test_unknown_param_is_an_error(ctx):
    with pytest.raises(GeneratorError) as exc:
        get("number").call(ctx, {"startt": 1})
    assert "startt" in str(exc.value)


def test_choice_without_repeat_exhausts_the_pool(ctx):
    spec = get("choice")
    params = {"data": ["a", "b", "c"], "repeat": False}
    values = [spec.call(ctx, params) for _ in range(3)]
    assert sorted(values) == ["a", "b", "c"]
    with pytest.raises(GeneratorError) as exc:
        spec.call(ctx, params)
    assert "repeat=false" in str(exc.value)


def test_sequence_without_repeat_fails_at_the_end(ctx):
    spec = get("sequence")
    params = {"data": ["a", "b"], "repeat": False}
    assert [spec.call(ctx, params) for _ in range(2)] == ["a", "b"]
    with pytest.raises(GeneratorError):
        spec.call(ctx, params)


def test_choice_without_data_returns_null(ctx):
    assert get("choice").call(ctx, {"data": [], "repeat": False}) is None


def test_choice_reads_file(ctx, tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("one\ntwo\n\nthree\n", encoding="utf-8")
    values = {get("choice").call(ctx, {"data": "data.txt"}) for _ in range(30)}
    assert values <= {"one", "two", "three"}


def test_sequence_walks_in_order(ctx):
    spec = get("sequence")
    params = {"data": [1, 2, 3]}
    assert [spec.call(ctx, params) for _ in range(4)] == [1, 2, 3, 1]


def test_auto_increment(ctx):
    spec = get("autoIncrement")
    assert [spec.call(ctx, {"start": 10}) for _ in range(3)] == [10, 11, 12]


def test_template_uses_row_fields(ctx):
    ctx.row = {"name": "Ana", "age": 30}
    assert get("template").call(ctx, {"pattern": "{name} ({age})"}) == "Ana (30)"


def test_generic_faker_provider(ctx):
    assert isinstance(get("faker").call(ctx, {"provider": "license_plate"}), str)
    with pytest.raises(GeneratorError):
        get("faker").call(ctx, {"provider": "does_not_exist"})


def test_date_with_explicit_range(ctx):
    value = get("date").call(
        ctx, {"start": "2024-01-01", "stop": "2024-12-31", "valueFormat": "%Y"}
    )
    assert value == "2024"


def test_object_and_array_use_the_schematic():
    schematic = Schematic(
        "s",
        {
            "address": {"method": "object", "fields": {"city_name": "city", "fixed": "abc"}},
            "tags": {"method": "array", "of": {"method": "integer", "start": 1, "stop": 3}, "size": 4},
        },
    )
    faker = Faker("pt_BR")
    ctx = GenContext(rng=random.Random(1), faker=faker, base_dir=Path("."), database="d")
    row = schematic.generate(ctx)
    assert set(row["address"]) == {"city_name", "fixed"}
    assert row["address"]["fixed"] == "abc"
    assert len(row["tags"]) == 4 and all(1 <= v <= 3 for v in row["tags"])


def test_chained_transform():
    assert pipes.apply(1234.5, [{"method": "round", "digits": 2}, "currency"]) == "R$ 1.234,50"
    assert pipes.apply("  ana  ", ["trim", "title"]) == "Ana"
    assert pipes.apply(["b", "a", "b"], ["unique", "sort", {"method": "join"}]) == "a, b"


def test_unknown_transform():
    with pytest.raises(Exception):
        pipes.apply(1, "does_not_exist")


def test_nullable_field_may_be_null():
    schematic = Schematic("s", {"x": {"method": "integer", "nullable": 1.0}})
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    assert schematic.generate(ctx)["x"] is None


def test_unique_field_fails_when_impossible():
    schematic = Schematic(
        "s", {"x": {"method": "choice", "data": ["a"], "unique": True}}
    )
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    schematic.generate(ctx)
    with pytest.raises(SchemaError):
        schematic.generate(ctx)


def test_circular_dependency_between_fields():
    schematic = Schematic(
        "s",
        {
            "a": {"method": "choice", "data": "__b"},
            "b": {"method": "choice", "data": "__a"},
        },
    )
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    with pytest.raises(SchemaError) as exc:
        schematic.generate(ctx)
    assert "Circular" in str(exc.value)


def test_reference_to_missing_field():
    schematic = Schematic("s", {"a": {"method": "choice", "data": "__zzz"}})
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    with pytest.raises(SchemaError):
        schematic.generate(ctx)


def test_missing_generator_in_schematic():
    with pytest.raises(SchemaError):
        Schematic("s", {"a": {"method": "doesNotExist"}})


def test_plain_string_becomes_constant():
    schematic = Schematic("s", {"country": "Brasil"})
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    assert schematic.generate(ctx)["country"] == "Brasil"
