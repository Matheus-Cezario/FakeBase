import json

from click.testing import CliRunner

from fakebase.cli import cli
from conftest import BASE_CONFIG


def write_config(tmp_path, **settings):
    raw = json.loads(json.dumps(BASE_CONFIG))
    raw["Settings"].update({"storage": "sqlite", "storagePath": str(tmp_path / "db"), **settings})
    path = tmp_path / "config.fakebase.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def run(path, *args):
    return CliRunner().invoke(cli, ["--config", str(path), *args])


def test_validate(tmp_path):
    result = run(write_config(tmp_path), "validate")
    assert result.exit_code == 0
    assert "products -> users" in result.output


def test_generate_and_list(tmp_path):
    path = write_config(tmp_path)
    generated = run(path, "generate")
    assert generated.exit_code == 0 and "Total: 16 documents" in generated.output

    listed = run(path, "list")
    assert "users" in listed.output and "6 documents" in listed.output


def test_generate_json_and_only(tmp_path):
    path = write_config(tmp_path)
    result = run(path, "generate", "--only", "products", "--json")
    payload = json.loads(result.output)
    assert [d["name"] for d in payload["databases"]] == ["products"]
    assert payload["seed"] == 123


def test_generate_export(tmp_path):
    path = write_config(tmp_path)
    target = tmp_path / "output"
    assert run(path, "generate", "--export", str(target)).exit_code == 0
    assert sorted(p.name for p in target.glob("*.json")) == ["products.json", "users.json"]


def test_preview_does_not_need_generated_data(tmp_path):
    result = run(write_config(tmp_path), "preview", "products", "-n", "2")
    assert result.exit_code == 0
    assert len(json.loads(result.output)) == 2


def test_export_import_and_drop(tmp_path):
    path = write_config(tmp_path)
    run(path, "generate")
    target = tmp_path / "dump"
    assert run(path, "export", str(target)).exit_code == 0

    assert run(path, "drop", "users", "--yes").exit_code == 0
    assert "0 documents" in run(path, "list").output

    imported = run(path, "import", str(target / "users.json"))
    assert "6 documents" in imported.output


def test_generators_lists_and_filters(tmp_path):
    path = write_config(tmp_path)
    everything = run(path, "generators")
    assert "humanName" in everything.output and "[time]" in everything.output

    filtered = run(path, "generators", "--search", "currency")
    assert "currencyCode" in filtered.output and "humanName" not in filtered.output

    transforms = run(path, "generators", "--transforms")
    assert "currency" in transforms.output


def test_init_creates_configuration(tmp_path):
    target = tmp_path / "new.json"
    result = CliRunner().invoke(cli, ["init", str(target)])
    assert result.exit_code == 0 and target.is_file()
    assert "Schematics" in json.loads(target.read_text(encoding="utf-8"))

    repeated = CliRunner().invoke(cli, ["init", str(target)])
    assert repeated.exit_code != 0


def test_configuration_error_is_friendly(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"Schematics": {}}', encoding="utf-8")
    result = run(path, "validate")
    assert result.exit_code != 0
    assert "DataBase" in str(result.exception or result.output)


def test_cli_seed_overrides_the_configuration(tmp_path):
    path = write_config(tmp_path)
    first = CliRunner().invoke(cli, ["--config", str(path), "--seed", "999", "preview", "users"])
    second = CliRunner().invoke(cli, ["--config", str(path), "--seed", "999", "preview", "users"])
    different = CliRunner().invoke(cli, ["--config", str(path), "--seed", "1", "preview", "users"])
    assert first.output == second.output != different.output
