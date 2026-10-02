from pathlib import Path

import pytest

from fakebase.errors import ConfigError
from fakebase.manager import FakeBase
from fakebase.queries import load_queries, route_for

from conftest import build_config

QUERIES = {
    "produtos/baratos.sql": """
        -- GET Produtos abaixo de um preço
        -- @param max number = 50
        -- @param limite int = 100
        SELECT name, price AS preco FROM products
        WHERE price < :max
        ORDER BY price
        LIMIT :limite
    """,
    "produtos/index.sql": """
        -- GET
        -- @param nome = null
        SELECT * FROM products WHERE (:nome IS NULL OR name LIKE :nome)
    """,
    "produtos/index.create.sql": """
        -- POST
        INSERT INTO products (name, price) VALUES (:name, :price)
    """,
    "produtos/[id].sql": """
        -- GET
        -- @param id string
        -- @one
        SELECT * FROM products WHERE _id = :id
    """,
    "produtos/[id].stock.sql": """
        -- PUT
        -- @param id string
        -- @one
        UPDATE products SET stock = stock - :qtd WHERE _id = :id
    """,
    "produtos/[id].delete.sql": """
        -- DELETE
        -- @param id string
        DELETE FROM products WHERE _id = :id
    """,
    "relatorios/usuarios/total.sql": """
        -- GET
        SELECT COUNT(*) AS total FROM users WHERE age >= :idade
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


def test_rotas_seguem_as_pastas():
    assert route_for("a/b/c.sql") == ("/queries/a/b/c", [])
    assert route_for("users/index.sql") == ("/queries/users", [])
    assert route_for("users/[id].sql", prefix="") == ("/users/{id}", ["id"])
    assert route_for("index.sql", prefix="/") == ("/", [])


def test_get_com_parametros_padrao_e_apelidos(client):
    documentos = client.get("/queries/produtos/baratos").json()
    assert documentos and all(set(d) == {"name", "preco"} for d in documentos)
    assert all(d["preco"] < 50 for d in documentos)
    assert [d["preco"] for d in documentos] == sorted(d["preco"] for d in documentos)

    poucos = client.get("/queries/produtos/baratos", params={"max": 90, "limite": 2}).json()
    assert len(poucos) == 2


def test_filtro_opcional(client):
    todos = client.get("/queries/produtos").json()
    assert len(todos) == 10
    nome = todos[0]["name"]
    filtrados = client.get("/queries/produtos", params={"nome": nome}).json()
    assert filtrados and all(d["name"].lower() == nome.lower() for d in filtrados)


def test_post_insere_e_get_por_id(client):
    response = client.post("/queries/produtos", json={"name": "Novo", "price": 12.5})
    assert response.status_code == 201
    criado = response.json()["value"][0]
    assert criado["name"] == "Novo" and "stock" in criado  # campos ausentes são gerados

    lido = client.get(f"/queries/produtos/{criado['_id']}").json()
    assert lido["_id"] == criado["_id"] and lido["price"] == 12.5


def test_put_incrementa_e_delete_apaga(client):
    produto = client.get("/products", params={"limit": 1}).json()[0]
    atualizado = client.put(f"/queries/produtos/{produto['_id']}", json={"qtd": 1}).json()
    assert atualizado["stock"] == produto["stock"] - 1

    apagado = client.delete(f"/queries/produtos/{produto['_id']}").json()
    assert apagado["deleted"] == 1
    assert client.get(f"/queries/produtos/{produto['_id']}").status_code == 404


def test_count_em_subpasta(client):
    body = client.get("/queries/relatorios/usuarios/total", params={"idade": 0}).json()
    assert body == {"total": 6}


def test_parametro_obrigatorio_e_tipo_invalido(client):
    response = client.get("/queries/relatorios/usuarios/total")
    assert response.status_code == 400 and "idade" in response.json()["error"]
    response = client.get("/queries/produtos/baratos", params={"limite": "muitos"})
    assert response.status_code == 400


def test_queries_aparecem_no_indice_e_no_swagger(client):
    assert {"method": "POST", "url": "/queries/produtos"} in client.get("/").json()["queries"]
    descritas = {(q["method"], q["url"]) for q in client.get("/_queries").json()}
    assert ("DELETE", "/queries/produtos/{id}") in descritas
    caminhos = client.get("/openapi.json").json()["paths"]
    assert "/queries/produtos/{id}" in caminhos
    parametros = caminhos["/queries/produtos/baratos"]["get"]["parameters"]
    assert {p["name"] for p in parametros} == {"max", "limite"}


def test_rotas_fixas_antes_das_com_parametro(tmp_path):
    folder = write_queries(
        tmp_path,
        {
            "users/[id].sql": "-- GET\nSELECT * FROM users WHERE _id = :id",
            "users/ativos.sql": "-- GET\nSELECT * FROM users WHERE active",
        },
    )
    rotas = [e.route for e in load_queries(folder, databases=["users"])]
    assert rotas == ["/queries/users/ativos", "/queries/users/{id}"]


@pytest.mark.parametrize(
    "arquivos, trecho",
    [
        ({"a.sql": "SELECT * FROM users"}, "método HTTP"),
        ({"a.sql": "-- PATCH\nSELECT * FROM users"}, "método HTTP"),
        ({"a.sql": "-- GET\nSELECT * FROM nada"}, "'nada' não existe"),
        ({"a.sql": "-- GET\nSELECT * FROM users WHERE"}, "a.sql"),
        ({"a.sql": "-- GET\n-- @param x\nSELECT * FROM users"}, "não usado"),
        ({"a.sql": "-- GET\n-- @param x data\nSELECT * FROM users WHERE a = :x"}, "tipo 'data'"),
        (
            {"a.sql": "-- GET\nSELECT * FROM users", "a.outra.sql": "-- GET\nSELECT * FROM users"},
            "mesma rota",
        ),
        ({"com espaço.sql": "-- GET\nSELECT * FROM users"}, "não pode virar parte da URL"),
    ],
)
def test_erros_de_carregamento(tmp_path, arquivos, trecho):
    folder = write_queries(tmp_path, arquivos)
    with pytest.raises(ConfigError, match=trecho):
        load_queries(folder, databases=["users"])


def test_pasta_inexistente_nao_gera_rotas(tmp_path):
    assert load_queries(tmp_path / "nada") == []
