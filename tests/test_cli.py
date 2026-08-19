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
    resultado = run(write_config(tmp_path), "validate")
    assert resultado.exit_code == 0
    assert "products -> users" in resultado.output


def test_generate_e_list(tmp_path):
    path = write_config(tmp_path)
    gerar = run(path, "generate")
    assert gerar.exit_code == 0 and "Total: 16 documentos" in gerar.output

    listar = run(path, "list")
    assert "users" in listar.output and "6 documentos" in listar.output


def test_generate_json_e_only(tmp_path):
    path = write_config(tmp_path)
    resultado = run(path, "generate", "--only", "products", "--json")
    payload = json.loads(resultado.output)
    assert [d["name"] for d in payload["databases"]] == ["products"]
    assert payload["seed"] == 123


def test_generate_export(tmp_path):
    path = write_config(tmp_path)
    destino = tmp_path / "saida"
    assert run(path, "generate", "--export", str(destino)).exit_code == 0
    assert sorted(p.name for p in destino.glob("*.json")) == ["products.json", "users.json"]


def test_preview_nao_precisa_de_dados_gerados(tmp_path):
    resultado = run(write_config(tmp_path), "preview", "products", "-n", "2")
    assert resultado.exit_code == 0
    assert len(json.loads(resultado.output)) == 2


def test_export_import_e_drop(tmp_path):
    path = write_config(tmp_path)
    run(path, "generate")
    destino = tmp_path / "dump"
    assert run(path, "export", str(destino)).exit_code == 0

    assert run(path, "drop", "users", "--yes").exit_code == 0
    assert "0 documentos" in run(path, "list").output

    importar = run(path, "import", str(destino / "users.json"))
    assert "6 documentos" in importar.output


def test_generators_lista_e_filtra(tmp_path):
    path = write_config(tmp_path)
    todos = run(path, "generators")
    assert "humanName" in todos.output and "[tempo]" in todos.output

    filtrado = run(path, "generators", "--search", "moeda")
    assert "currencyCode" in filtrado.output and "humanName" not in filtrado.output

    transforms = run(path, "generators", "--transforms")
    assert "currency" in transforms.output


def test_init_cria_configuracao(tmp_path):
    destino = tmp_path / "novo.json"
    resultado = CliRunner().invoke(cli, ["init", str(destino)])
    assert resultado.exit_code == 0 and destino.is_file()
    assert "Schematics" in json.loads(destino.read_text(encoding="utf-8"))

    repetido = CliRunner().invoke(cli, ["init", str(destino)])
    assert repetido.exit_code != 0


def test_erro_de_configuracao_e_amigavel(tmp_path):
    path = tmp_path / "quebrado.json"
    path.write_text('{"Schematics": {}}', encoding="utf-8")
    resultado = run(path, "validate")
    assert resultado.exit_code != 0
    assert "DataBase" in str(resultado.exception or resultado.output)


def test_semente_do_cli_sobrepoe_a_configuracao(tmp_path):
    path = write_config(tmp_path)
    primeiro = CliRunner().invoke(cli, ["--config", str(path), "--seed", "999", "preview", "users"])
    segundo = CliRunner().invoke(cli, ["--config", str(path), "--seed", "999", "preview", "users"])
    diferente = CliRunner().invoke(cli, ["--config", str(path), "--seed", "1", "preview", "users"])
    assert primeiro.output == segundo.output != diferente.output
