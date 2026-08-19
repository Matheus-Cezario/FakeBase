def test_index_lista_os_bancos(client):
    body = client.get("/").json()
    assert body["dataBase"] == ["users", "products"]
    assert body["storage"]["backend"] == "memory"
    assert {d["name"]: d["count"] for d in body["databases"]} == {"users": 6, "products": 10}


def test_listagem_simples_devolve_array(client):
    response = client.get("/products")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert response.headers["x-total-count"] == "10"


def test_listagem_com_filtro_ordem_projecao_e_limite(client):
    documentos = client.get(
        "/products", params={"price__gt": 20, "sort": "-price", "fields": "name,price", "limit": 3}
    ).json()
    assert len(documentos) <= 3
    assert all(set(d) == {"_id", "name", "price"} for d in documentos)
    precos = [d["price"] for d in documentos]
    assert precos == sorted(precos, reverse=True) and all(p > 20 for p in precos)


def test_paginacao_devolve_envelope(client):
    body = client.get("/products", params={"paginate": "true", "pageCount": 4, "page": 2}).json()
    assert body["totalItens"] == 10 and body["totalPages"] == 3
    assert body["page"] == 2 and len(body["value"]) == 4


def test_busca_por_id_e_404(client):
    documento = client.get("/users", params={"limit": 1}).json()[0]
    assert client.get(f"/users/{documento['_id']}").json()["_id"] == documento["_id"]
    assert client.get("/users/nao-existe").status_code == 404


def test_post_preenche_os_campos_que_faltam(client):
    criado = client.post("/users", json={"name": "Ana"}).json()
    assert criado["name"] == "Ana"
    assert {"email", "age", "gender", "cart", "_id"} <= set(criado)
    assert client.get(f"/users/{criado['_id']}").json()["name"] == "Ana"


def test_post_sem_preenchimento(client):
    criado = client.post("/users", params={"fill": "false"}, json={"name": "Beto"}).json()
    assert set(criado) == {"name", "_id"}


def test_post_em_lote(client):
    criados = client.post("/products", json=[{"name": "A"}, {"name": "B"}]).json()
    assert [c["name"] for c in criados] == ["A", "B"]
    assert client.get("/products/_count").json()["count"] == 12


def test_patch_put_delete_por_id(client):
    documento = client.get("/users", params={"limit": 1}).json()[0]
    atualizado = client.patch(f"/users/{documento['_id']}", json={"age": 50}).json()
    assert atualizado["age"] == 50 and atualizado["name"] == documento["name"]

    substituido = client.put(f"/users/{documento['_id']}", json={"name": "Só isso"}).json()
    assert substituido == {"_id": documento["_id"], "name": "Só isso"}

    assert client.delete(f"/users/{documento['_id']}").status_code == 200
    assert client.get(f"/users/{documento['_id']}").status_code == 404


def test_operacoes_em_lote_exigem_filtro(client):
    assert client.delete("/users").status_code == 400
    assert client.patch("/users", json={"active": False}).status_code == 400


def test_patch_em_lote_por_filtro(client):
    atualizados = client.patch("/products", params={"price__lt": 1000}, json={"stock": 0}).json()
    assert len(atualizados) == 10 and all(d["stock"] == 0 for d in atualizados)


def test_count_e_distinct(client):
    assert client.get("/users/_count").json()["count"] == 6
    body = client.get("/users/_distinct/gender").json()
    assert set(body["values"]) <= {"male", "female"}


def test_generate_acrescenta_documentos(client):
    body = client.post("/products/_generate", params={"count": 5}).json()
    assert body["created"] == 5
    assert client.get("/products/_count").json()["count"] == 15


def test_reset_regenera_o_banco(client):
    client.delete("/products", params={"price__gt": 0})
    body = client.post("/products/_reset").json()
    assert body["databases"][0]["size"] == 10
    assert client.get("/products/_count").json()["count"] == 10


def test_schema_e_stats(client):
    schema = client.get("/_schema/users").json()
    assert schema["fields"]["email"]["unique"] is True
    assert client.get("/_stats").json()["databases"][0]["count"] == 6
    assert client.get("/_schema").json()["product"]["price"]["method"] == "number"


def test_generators_documenta_o_catalogo(client):
    body = client.get("/_generators").json()
    nomes = {g["name"] for g in body["generators"]}
    assert {"humanName", "number", "choice"} <= nomes
    assert any(t["name"] == "currency" for t in body["transforms"])


def test_erros_tem_corpo_json(client):
    resposta = client.get("/naoexiste")
    assert resposta.status_code == 404 and resposta.json()["type"] == "NotFoundError"
    assert client.get("/users", params={"age__zzz": 1}).status_code == 400


def test_openapi_disponivel(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


# --- rotas da versão 1.x ----------------------------------------------------


def test_legacy_list(client):
    body = client.get("/list/users").json()
    assert body["totalItens"] == 6 and len(body["value"]) == 6


def test_legacy_list_com_paginacao_e_filtro(client):
    body = client.get(
        "/list/users", params={"paginate": "true", "pageCount": 2, "page": 1, "gender": "male"}
    ).json()
    assert len(body["value"]) <= 2 and body["pageCount"] == 2
    assert all(d["gender"] == "male" for d in body["value"])


def test_legacy_get(client):
    assert client.get("/get/users", params={"gender": "female"}).json()["gender"] == "female"
    assert client.get("/get/users", params={"gender": "xxx"}).json() == {}


def test_legacy_update_e_set(client):
    documento = client.get("/get/users").json()
    atualizado = client.post("/update/users", params={"_id": documento["_id"]}, json={"age": 33})
    assert atualizado.json()[0]["age"] == 33

    substituido = client.post("/set/users", params={"_id": documento["_id"]}, json={"name": "Zé"})
    assert substituido.json()[0] == {"_id": documento["_id"], "name": "Zé"}


def test_legacy_delete_com_every(client):
    apagados = client.get("/delete/users", params={"gender": "male", "every": "true"}).json()
    assert all(d["gender"] == "male" for d in apagados)
    assert client.get("/users/_count", params={"gender": "male"}).json()["count"] == 0


def test_legacy_delete_sem_filtro_nao_apaga(client):
    assert client.get("/delete/users").status_code == 400
    assert client.get("/users/_count").json()["count"] == 6
