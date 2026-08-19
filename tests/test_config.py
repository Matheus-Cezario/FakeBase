import json

import pytest

from fakebase.config import Config, Settings, example_config
from fakebase.errors import ConfigError

from conftest import BASE_CONFIG


def carregar(tmp_path, raw, **overrides):
    return Config.from_dict(raw, path=tmp_path / "c.json", **overrides)


def test_configuracao_de_exemplo_e_valida(tmp_path):
    config = carregar(tmp_path, example_config())
    assert config.database_names == ["users", "products"]


def test_settings_padrao_e_sobreposicao(tmp_path):
    config = carregar(tmp_path, json.loads(json.dumps(BASE_CONFIG)), seed=7, locale="en_US")
    assert config.settings.seed == 7 and config.settings.locale == "en_US"
    assert config.settings.storage == "memory"  # veio do arquivo


def test_settings_desconhecido(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Settings"]["velocidade"] = 10
    with pytest.raises(ConfigError):
        carregar(tmp_path, raw)


def test_min_max_size_sao_ordenados():
    assert Settings.parse({"minSize": 50, "maxSize": 10}).minSize == 10


def test_chave_desconhecida_no_topo(tmp_path):
    with pytest.raises(ConfigError):
        carregar(tmp_path, {"Schematics": {}, "DataBase": {}, "Outra": 1})


@pytest.mark.parametrize("faltando", ["Schematics", "DataBase"])
def test_chaves_obrigatorias(tmp_path, faltando):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw.pop(faltando)
    with pytest.raises(ConfigError):
        carregar(tmp_path, raw)


def test_schema_inexistente(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["DataBase"]["users"] = {"schema": "fantasma"}
    with pytest.raises(ConfigError) as exc:
        carregar(tmp_path, raw)
    assert "fantasma" in str(exc.value)


def test_database_como_texto(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["DataBase"]["products"] = "product"
    config = carregar(tmp_path, raw)
    assert config.database("products").size is None


def test_size_invalido(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["DataBase"]["users"] = {"schema": "user", "size": "muitos"}
    with pytest.raises(ConfigError):
        carregar(tmp_path, raw)


def test_id_automatico_e_unico(tmp_path):
    config = carregar(tmp_path, json.loads(json.dumps(BASE_CONFIG)))
    campo = config.schematics["user"].fields["_id"]
    assert campo.method == "objectId" and campo.unique is True


def test_id_declarado_pelo_usuario_e_respeitado(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["user"]["_id"] = {"method": "autoIncrement"}
    config = carregar(tmp_path, raw)
    assert config.schematics["user"].fields["_id"].method == "autoIncrement"


def test_arquivo_inexistente(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(tmp_path / "nao_existe.json")


def test_arquivo_vazio(tmp_path):
    caminho = tmp_path / "vazio.json"
    caminho.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(caminho)


def test_json_invalido(tmp_path):
    caminho = tmp_path / "ruim.json"
    caminho.write_text("{ isso nao e json", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        Config.load(caminho)
    assert "JSON inválido" in str(exc.value)


def test_describe_expoe_a_configuracao(tmp_path):
    descricao = carregar(tmp_path, json.loads(json.dumps(BASE_CONFIG))).describe()
    assert descricao["schematics"]["user"]["email"]["unique"] is True
    assert descricao["settings"]["locale"] == "pt_BR"
