import json

import pytest

from fakebase.config import Config, Settings, example_config
from fakebase.errors import ConfigError

from conftest import BASE_CONFIG


def load(tmp_path, raw, **overrides):
    return Config.from_dict(raw, path=tmp_path / "c.json", **overrides)


def test_example_config_is_valid(tmp_path):
    config = load(tmp_path, example_config())
    assert config.database_names == ["users", "products"]


def test_default_settings_and_overrides(tmp_path):
    config = load(tmp_path, json.loads(json.dumps(BASE_CONFIG)), seed=7, locale="en_US")
    assert config.settings.seed == 7 and config.settings.locale == "en_US"
    assert config.settings.storage == "memory"  # came from the file


def test_unknown_setting(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Settings"]["speed"] = 10
    with pytest.raises(ConfigError):
        load(tmp_path, raw)


def test_min_max_size_are_ordered():
    assert Settings.parse({"minSize": 50, "maxSize": 10}).minSize == 10


def test_unknown_top_level_key(tmp_path):
    with pytest.raises(ConfigError):
        load(tmp_path, {"Schematics": {}, "DataBase": {}, "Other": 1})


@pytest.mark.parametrize("missing", ["Schematics", "DataBase"])
def test_required_keys(tmp_path, missing):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw.pop(missing)
    with pytest.raises(ConfigError):
        load(tmp_path, raw)


def test_missing_schema(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["DataBase"]["users"] = {"schema": "ghost"}
    with pytest.raises(ConfigError) as exc:
        load(tmp_path, raw)
    assert "ghost" in str(exc.value)


def test_database_as_string(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["DataBase"]["products"] = "product"
    config = load(tmp_path, raw)
    assert config.database("products").size is None


def test_invalid_size(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["DataBase"]["users"] = {"schema": "user", "size": "lots"}
    with pytest.raises(ConfigError):
        load(tmp_path, raw)


def test_automatic_id_is_unique(tmp_path):
    config = load(tmp_path, json.loads(json.dumps(BASE_CONFIG)))
    field = config.schematics["user"].fields["_id"]
    assert field.method == "objectId" and field.unique is True


def test_user_declared_id_is_kept(tmp_path):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Schematics"]["user"]["_id"] = {"method": "autoIncrement"}
    config = load(tmp_path, raw)
    assert config.schematics["user"].fields["_id"].method == "autoIncrement"


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(tmp_path / "does_not_exist.json")


def test_empty_file(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(path)


def test_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        Config.load(path)
    assert "Invalid JSON" in str(exc.value)


def test_describe_exposes_the_configuration(tmp_path):
    description = load(tmp_path, json.loads(json.dumps(BASE_CONFIG))).describe()
    assert description["schematics"]["user"]["email"]["unique"] is True
    assert description["settings"]["locale"] == "pt_BR"
