import json

import pytest

from fakebase.config import Config
from fakebase.errors import ConfigError, LinkError, NotFoundError
from fakebase.manager import FakeBase
from fakebase.query import ListOptions
from fakebase.references import parse_reference

from conftest import BASE_CONFIG, build_config


def test_ordem_de_geracao_segue_as_referencias(fakebase):
    assert fakebase.generation_order() == ["products", "users"]


def test_geracao_cria_os_documentos(fakebase):
    assert fakebase.count("users") == 6
    assert fakebase.count("products") == 10


def test_referencia_entre_bancos_traz_dados_reais(fakebase):
    precos = {p["price"] for p in fakebase.storage.find("products", {})}
    for user in fakebase.storage.find("users", {}):
        for item in user["cart"]:
            assert set(item) == {"name", "price"}
            assert item["price"] < 50 and item["price"] in precos


def test_semente_torna_a_geracao_reproduzivel(tmp_path):
    def gerar():
        instance = FakeBase(build_config(tmp_path))
        instance.generate()
        documents = instance.storage.find("users", {})
        instance.close()
        return json.dumps(documents, sort_keys=True, default=str)

    assert gerar() == gerar()


def test_sementes_diferentes_geram_dados_diferentes(tmp_path):
    def gerar(seed):
        instance = FakeBase(build_config(tmp_path, seed=seed))
        instance.generate()
        documents = instance.storage.find("users", {})
        instance.close()
        return json.dumps(documents, sort_keys=True, default=str)

    assert gerar(1) != gerar(2)


def test_campo_unique_nao_repete(fakebase):
    emails = [u["email"] for u in fakebase.storage.find("users", {})]
    assert len(emails) == len(set(emails))


def test_append_continua_contador_e_unicidade(fakebase):
    antes = fakebase.storage.find("users", {})
    fakebase.append("users", 4)
    depois = fakebase.storage.find("users", {})
    assert len(depois) == len(antes) + 4
    assert len({d["_id"] for d in depois}) == len(depois)
    assert len({d["seq"] for d in depois}) == len(depois)


def test_preview_nao_grava(fakebase):
    antes = fakebase.count("products")
    assert len(fakebase.preview("products", 3)) == 3
    assert fakebase.count("products") == antes


def test_tamanho_limitado_por_gerador_sem_repeticao(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["tag"] = {"name": {"method": "choice", "data": ["a", "b", "c"], "repeat": False}}
    raw["DataBase"]["tags"] = {"schema": "tag", "size": 99}
    config = Config.from_dict(raw, path=tmp_path / "c.json")
    instance = FakeBase(config)
    report = instance.generate()
    tags = next(item for item in report.databases if item.name == "tags")
    assert tags.size == 3 and tags.notes
    instance.close()


def test_tamanho_em_intervalo(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["DataBase"]["users"] = {"schema": "user", "size": [3, 5]}
    instance = FakeBase(Config.from_dict(raw, path=tmp_path / "c.json"))
    report = instance.generate()
    users = next(item for item in report.databases if item.name == "users")
    assert 3 <= users.size <= 5
    instance.close()


def test_crud_completo(fakebase):
    criado = fakebase.create("users", {"name": "Fulano"})
    assert criado["name"] == "Fulano" and "email" in criado

    atualizado = fakebase.update("users", {"_id": criado["_id"]}, {"age": 41})
    assert atualizado[0]["age"] == 41 and atualizado[0]["name"] == "Fulano"

    substituido = fakebase.replace("users", {"_id": criado["_id"]}, {"name": "Outro"})
    assert substituido[0] == {"_id": criado["_id"], "name": "Outro"}

    apagado = fakebase.delete("users", {"_id": criado["_id"]})
    assert apagado[0]["name"] == "Outro"
    assert fakebase.get_by_id("users", criado["_id"]) is None


def test_update_nao_troca_o_id(fakebase):
    documento = fakebase.storage.find("users", {}, limit=1)[0]
    fakebase.update("users", {"_id": documento["_id"]}, {"_id": "hackeado", "age": 30})
    assert fakebase.get_by_id("users", "hackeado") is None
    assert fakebase.get_by_id("users", documento["_id"])["age"] == 30


def test_delete_sem_every_afeta_um_documento(fakebase):
    antes = fakebase.count("users")
    apagados = fakebase.delete("users", {}, every=False)
    assert len(apagados) == 1 and fakebase.count("users") == antes - 1


def test_lista_com_filtro_ordem_e_pagina(fakebase):
    options = ListOptions.from_query({"sort": "-price", "paginate": "true", "pageCount": "4"})
    documentos, total = fakebase.list("products", options)
    assert total == 10 and len(documentos) == 4
    precos = [d["price"] for d in documentos]
    assert precos == sorted(precos, reverse=True)


def test_banco_inexistente(fakebase):
    with pytest.raises(NotFoundError):
        fakebase.count("naoexiste")


def test_export_e_import(fakebase, tmp_path):
    destino = tmp_path / "saida"
    arquivos = fakebase.export(destino)
    assert {p.name for p in arquivos} == {"users.json", "products.json"}
    conteudo = json.loads((destino / "users.json").read_text(encoding="utf-8"))
    assert len(conteudo["users"]) == 6

    fakebase.storage.drop("users")
    assert fakebase.count("users") == 0
    carregado = fakebase.import_json(destino / "users.json")
    assert carregado == {"users": 6}
    assert fakebase.count("users") == 6


def test_stats_lista_todos_os_bancos(fakebase):
    stats = fakebase.stats()
    assert {d["name"] for d in stats["databases"]} == {"users", "products"}
    assert all(d["generated"] for d in stats["databases"])


def test_referencia_circular_entre_bancos(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["product"]["dono"] = {"method": "choice", "data": "@users:name@"}
    instance = FakeBase(Config.from_dict(raw, path=tmp_path / "c.json"))
    with pytest.raises(LinkError):
        instance.generation_order()
    instance.close()


def test_referencia_para_banco_inexistente(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["user"]["x"] = {"method": "choice", "data": "@fantasma:name@"}
    with pytest.raises(ConfigError):
        Config.from_dict(raw, path=tmp_path / "c.json")


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("@products@", ("products", None, None, None)),
        ("@products:name@", ("products", None, "name", None)),
        ("@products:[a,b]@", ("products", ["a", "b"], None, None)),
        ("@products:name:price<50@", ("products", None, "name", "price<50")),
    ],
)
def test_parse_reference(texto, esperado):
    reference = parse_reference(texto)
    assert (
        reference.database,
        reference.fields,
        reference.single_field,
        reference.conditions,
    ) == esperado


def test_parse_reference_quantidade():
    assert parse_reference("@p:_id::3@").count == 3
    assert parse_reference("@p:_id::all@").count == "all"
    assert parse_reference("@p:_id::[1,4]@").count == (1, 4)
    with pytest.raises(LinkError):
        parse_reference("@p:_id::x@")


def test_append_respeita_repeat_false(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["tag"] = {
        "name": {"method": "choice", "data": ["a", "b", "c", "d"], "repeat": False}
    }
    raw["DataBase"]["tags"] = {"schema": "tag", "size": 2}
    instance = FakeBase(Config.from_dict(raw, path=tmp_path / "c.json"))
    instance.generate()
    instance.append("tags", 2)
    nomes = [d["name"] for d in instance.storage.find("tags", {})]
    assert sorted(nomes) == ["a", "b", "c", "d"]
    instance.close()


def test_append_continua_sequence(tmp_path):
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
