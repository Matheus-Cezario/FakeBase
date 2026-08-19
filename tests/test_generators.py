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


def test_registro_expoe_metadados():
    nomes = {spec.name for spec in available()}
    assert {"number", "humanName", "choice", "date", "object", "array"} <= nomes
    assert get("int") is get("integer")  # apelido


def test_number_respeita_limites(ctx):
    for _ in range(50):
        value = get("number").call(ctx, {"start": 5, "stop": 10, "numberType": "int"})
        assert 5 <= value <= 10 and isinstance(value, int)


def test_parametros_vem_como_texto_do_json(ctx):
    value = get("integer").call(ctx, {"start": "1", "stop": "3"})
    assert 1 <= value <= 3


def test_parametro_desconhecido_e_erro(ctx):
    with pytest.raises(GeneratorError) as exc:
        get("number").call(ctx, {"startt": 1})
    assert "startt" in str(exc.value)


def test_choice_sem_repeticao_esgota_o_pool(ctx):
    spec = get("choice")
    params = {"data": ["a", "b", "c"], "repeat": False}
    valores = [spec.call(ctx, params) for _ in range(3)]
    assert sorted(valores) == ["a", "b", "c"]
    with pytest.raises(GeneratorError) as exc:
        spec.call(ctx, params)
    assert "repeat=false" in str(exc.value)


def test_sequence_sem_repeticao_avisa_no_fim(ctx):
    spec = get("sequence")
    params = {"data": ["a", "b"], "repeat": False}
    assert [spec.call(ctx, params) for _ in range(2)] == ["a", "b"]
    with pytest.raises(GeneratorError):
        spec.call(ctx, params)


def test_choice_sem_dados_devolve_nulo(ctx):
    assert get("choice").call(ctx, {"data": [], "repeat": False}) is None


def test_choice_le_arquivo(ctx, tmp_path):
    arquivo = tmp_path / "dados.txt"
    arquivo.write_text("um\ndois\n\ntres\n", encoding="utf-8")
    valores = {get("choice").call(ctx, {"data": "dados.txt"}) for _ in range(30)}
    assert valores <= {"um", "dois", "tres"}


def test_sequence_percorre_em_ordem(ctx):
    spec = get("sequence")
    params = {"data": [1, 2, 3]}
    assert [spec.call(ctx, params) for _ in range(4)] == [1, 2, 3, 1]


def test_auto_increment(ctx):
    spec = get("autoIncrement")
    assert [spec.call(ctx, {"start": 10}) for _ in range(3)] == [10, 11, 12]


def test_template_usa_campos_da_linha(ctx):
    ctx.row = {"name": "Ana", "age": 30}
    assert get("template").call(ctx, {"pattern": "{name} ({age})"}) == "Ana (30)"


def test_faker_provider_generico(ctx):
    assert isinstance(get("faker").call(ctx, {"provider": "license_plate"}), str)
    with pytest.raises(GeneratorError):
        get("faker").call(ctx, {"provider": "nao_existe"})


def test_date_com_intervalo_explicito(ctx):
    valor = get("date").call(
        ctx, {"start": "2024-01-01", "stop": "2024-12-31", "valueFormat": "%Y"}
    )
    assert valor == "2024"


def test_object_e_array_usam_o_schematic():
    schematic = Schematic(
        "s",
        {
            "endereco": {"method": "object", "fields": {"cidade": "city", "fixo": "abc"}},
            "tags": {"method": "array", "of": {"method": "integer", "start": 1, "stop": 3}, "size": 4},
        },
    )
    faker = Faker("pt_BR")
    ctx = GenContext(rng=random.Random(1), faker=faker, base_dir=Path("."), database="d")
    linha = schematic.generate(ctx)
    assert set(linha["endereco"]) == {"cidade", "fixo"}
    assert linha["endereco"]["fixo"] == "abc"
    assert len(linha["tags"]) == 4 and all(1 <= v <= 3 for v in linha["tags"])


def test_transform_encadeado():
    assert pipes.apply(1234.5, [{"method": "round", "digits": 2}, "currency"]) == "R$ 1.234,50"
    assert pipes.apply("  ana  ", ["trim", "title"]) == "Ana"
    assert pipes.apply(["b", "a", "b"], ["unique", "sort", {"method": "join"}]) == "a, b"


def test_transform_desconhecido():
    with pytest.raises(Exception):
        pipes.apply(1, "naoexiste")


def test_campo_nullable_pode_ser_nulo():
    schematic = Schematic("s", {"x": {"method": "integer", "nullable": 1.0}})
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    assert schematic.generate(ctx)["x"] is None


def test_campo_unique_falha_quando_impossivel():
    schematic = Schematic(
        "s", {"x": {"method": "choice", "data": ["a"], "unique": True}}
    )
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    schematic.generate(ctx)
    with pytest.raises(SchemaError):
        schematic.generate(ctx)


def test_dependencia_circular_entre_campos():
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
    assert "circular" in str(exc.value)


def test_referencia_a_campo_inexistente():
    schematic = Schematic("s", {"a": {"method": "choice", "data": "__zzz"}})
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    with pytest.raises(SchemaError):
        schematic.generate(ctx)


def test_gerador_inexistente_no_schematic():
    with pytest.raises(SchemaError):
        Schematic("s", {"a": {"method": "naoExiste"}})


def test_texto_solto_vira_constante():
    schematic = Schematic("s", {"pais": "Brasil"})
    ctx = GenContext(rng=random.Random(1), faker=Faker(), base_dir=Path("."), database="d")
    assert schematic.generate(ctx)["pais"] == "Brasil"
