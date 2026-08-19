# FakeBase

Gera bancos de dados falsos a partir de um único arquivo JSON e serve tudo por uma
API REST — para prototipar telas, popular ambientes de teste ou demonstrar um app
sem depender de backend nenhum.

Na versão 2 os dados deixaram de morar em arquivos `.json` soltos e passaram a
viver em um **NoSQL embutido** ([MontyDB](https://github.com/davidlatwe/montydb)),
que fala a linguagem de consulta do MongoDB sem exigir servidor: é só uma pasta no
disco. Com isso as rotas ganharam filtros de verdade (`price__gt`, `name__like`,
`sort`, projeção, paginação) e o CRUD passou a ser realmente CRUD — agora com
`POST` para criar.

```bash
pip install -r requirements.txt
python -m fakebase init          # cria um config.fakebase.json de exemplo
python -m fakebase start         # gera os dados e sobe a API
```

```
http://localhost:8080/           lista os bancos
http://localhost:8080/docs       documentação interativa (Swagger)
http://localhost:8080/users?age__gt=30&sort=-age&limit=5
```

---

## Sumário

- [O que mudou na versão 2](#o-que-mudou-na-versão-2)
- [Instalação](#instalação)
- [Comandos](#comandos)
- [API HTTP](#api-http)
  - [Rotas REST](#rotas-rest)
  - [Filtros e operadores](#filtros-e-operadores)
  - [Paginação, ordenação e projeção](#paginação-ordenação-e-projeção)
  - [Rotas da versão 1.x](#rotas-da-versão-1x)
- [Arquivo de configuração](#arquivo-de-configuração)
  - [Settings](#settings)
  - [Schematics](#schematics)
  - [DataBase](#database)
- [Geradores](#geradores)
- [Transforms](#transforms)
- [Ligação entre campos](#ligação-entre-campos)
- [Ligação entre bancos de dados](#ligação-entre-bancos-de-dados)
- [Onde os dados ficam](#onde-os-dados-ficam)
- [Testes](#testes)
- [Migrando da versão 1.x](#migrando-da-versão-1x)

---

## O que mudou na versão 2

| Antes (1.x) | Agora (2.0) |
| --- | --- |
| Um arquivo JSON por banco, lido e reescrito inteiro a cada requisição | NoSQL embutido (MontyDB sobre SQLite), consultado documento a documento |
| Filtros só por igualdade | Operadores `gt`, `gte`, `lt`, `lte`, `ne`, `in`, `nin`, `like`, `start`, `end`, `regex`, `exists`, `size` |
| Sem ordenação, sem projeção | `sort=-price`, `fields=name,price`, `limit`, `skip` |
| Sem criação de registros | `POST /users` — e os campos que faltam são gerados pelo schematic |
| CherryPy | FastAPI, com Swagger em `/docs` e OpenAPI em `/openapi.json` |
| 10 geradores | 59 geradores, com locale (`pt_BR` gera CPF, CEP, cidades e nomes brasileiros) |
| 1 transform (`currency`) | 32 transforms encadeáveis |
| Condições avaliadas com `eval()` | Analisador próprio, sem executar código do arquivo de configuração |
| Dados diferentes a cada execução | `seed` opcional: mesma semente, mesmos dados |
| Erros como `AssertionError` | Mensagens explicando o que está errado e o que é aceito |

As rotas antigas (`/list`, `/get`, `/update`, `/set`, `/delete`) continuam
funcionando, com o mesmo formato de resposta.

---

## Instalação

Requer Python 3.9 ou mais novo.

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
source .venv/bin/activate      # Linux/macOS
pip install -r requirements.txt
```

Também dá para instalar como pacote e ganhar o comando `fakebase`:

```bash
pip install -e .
fakebase --help
```

Todos os exemplos abaixo usam `fakebase`; sem instalar, troque por
`python -m fakebase` (ou `python FakeBase.py`, que continua funcionando).

---

## Comandos

```
fakebase [OPÇÕES GLOBAIS] COMANDO [ARGUMENTOS]
```

| Comando | O que faz |
| --- | --- |
| `generate` | Gera (ou regenera) todos os bancos. `--only users` limita, `--export pasta` também salva JSONs, `--json` imprime o relatório em JSON |
| `serve` | Sobe a API sobre os dados já gerados. `--host`, `--port`, `--latency 300` (atraso artificial em ms) |
| `start` | `generate` + `serve` |
| `list` | Mostra cada banco e quantos documentos tem |
| `preview users -n 3` | Mostra linhas de exemplo sem gravar nada — ótimo para ajustar um schematic |
| `validate` | Confere a configuração e mostra a ordem de geração |
| `generators` | Lista os geradores e seus parâmetros. `--search cpf`, `--transforms` |
| `export pasta` | Salva cada banco em um `.json` (formato da versão 1.x) |
| `import pasta` | Carrega arquivos `.json` para dentro do NoSQL. `--append` mantém o que já existe |
| `drop users` | Apaga os dados de um banco (`--all` para todos) |
| `init` | Cria um `config.fakebase.json` de exemplo |

Opções globais:

| Opção | Padrão | Descrição |
| --- | --- | --- |
| `-c`, `--config`, `--path` | `./config.fakebase.json` | Arquivo de configuração |
| `--storage-path`, `--fakepath` | `./.fakebase` | Pasta onde o NoSQL guarda os dados |
| `--storage` | `sqlite` | `sqlite`, `flatfile` ou `memory` |
| `--seed` | — | Semente aleatória: mesma semente, mesmos dados |
| `--locale` | `pt_BR` | Locale dos dados falsos (`en_US`, `es_ES`, `fr_FR`, ...) |

---

## API HTTP

### Rotas REST

Cada banco declarado em `DataBase` vira um recurso. Para um banco chamado `users`:

| Método e rota | O que faz |
| --- | --- |
| `GET /users` | Lista documentos (aceita filtros, ordenação, projeção e paginação) |
| `GET /users/{id}` | Busca por `_id`; devolve 404 se não existir |
| `POST /users` | Cria um documento. Os campos ausentes são **gerados pelo schematic**; use `?fill=false` para gravar só o que veio no corpo. O corpo também pode ser uma lista |
| `PATCH /users/{id}` | Atualiza os campos informados |
| `PUT /users/{id}` | Substitui o documento inteiro (o `_id` é preservado) |
| `DELETE /users/{id}` | Apaga o documento |
| `PATCH /users?filtro` | Atualiza em lote (exige ao menos um filtro) |
| `DELETE /users?filtro` | Apaga em lote (exige ao menos um filtro) |
| `GET /users/_count` | Conta documentos, com os mesmos filtros da listagem |
| `GET /users/_distinct/{campo}` | Valores distintos de um campo |
| `POST /users/_generate?count=10` | Gera mais documentos falsos e acrescenta ao banco |
| `POST /users/_reset` | Regenera o banco do zero |

Rotas de metadados:

| Rota | Conteúdo |
| --- | --- |
| `GET /` | Bancos, contagens e onde os dados estão |
| `GET /_schema` e `GET /_schema/{banco}` | Os schematics, já normalizados |
| `GET /_stats` | Quantidade de documentos por banco |
| `GET /_generators` | Catálogo de geradores e transforms |
| `GET /docs` | Swagger UI |

### Filtros e operadores

Qualquer parâmetro que não seja reservado vira filtro. Use `campo__operador`:

```
GET /products?price__gt=40&price__lte=80
GET /products?name__like=arroz
GET /products?tags__in=novo,importado
GET /users?nickname__exists=false
GET /orders?status__ne=cancelado
```

| Operador | Significado |
| --- | --- |
| (nenhum) | igual |
| `ne` | diferente |
| `gt`, `gte`, `lt`, `lte` | maior / maior ou igual / menor / menor ou igual |
| `in`, `nin` | está / não está na lista (separada por vírgula) |
| `like`, `contains`, `ilike` | contém o texto (ignora maiúsculas) |
| `start`, `end` | começa / termina com |
| `regex` | expressão regular |
| `exists` | o campo existe |
| `size` | tamanho exato de uma lista |
| `all` | a lista contém todos os valores |

Valores são convertidos automaticamente: `30` vira número, `true`/`false` viram
booleanos, `null` vira nulo. Repetir o mesmo campo combina as condições com `E`
lógico (`?price__gt=10&price__gt=20`).

### Paginação, ordenação e projeção

| Parâmetro | Efeito |
| --- | --- |
| `sort=-price,name` | Ordena por preço decrescente e depois por nome |
| `fields=name,price` | Devolve só esses campos (o `_id` vem junto) |
| `exclude=cart` | Devolve tudo menos esses campos |
| `limit=10&skip=20` | Recorte simples |
| `paginate=true&page=2&pageCount=5` | Paginação com metadados na resposta |
| `every=true` | Nas rotas de atualização/remoção em lote da versão 1.x, aplica a todos |

Sem `paginate`, a listagem devolve um array puro e o total vai no cabeçalho
`X-Total-Count`. Com `paginate=true`, a resposta vem em envelope:

```json
{
  "value": [ ... ],
  "totalItens": 25,
  "totalItems": 25,
  "page": 2,
  "pageCount": 5,
  "totalPages": 5
}
```

### Rotas da versão 1.x

Continuam disponíveis e com o mesmo formato de antes:

| Rota | Equivalente novo |
| --- | --- |
| `GET /list/users` | `GET /users?paginate=true` |
| `GET /get/users?gender=male` | `GET /users?gender=male&limit=1` |
| `GET|POST /update/users?_id=...` | `PATCH /users/{id}` |
| `GET|POST /set/users?_id=...` | `PUT /users/{id}` |
| `GET|DELETE /delete/users?_id=...` | `DELETE /users/{id}` |

Uma diferença importante: `update`, `set` e `delete` agora **exigem pelo menos um
filtro**. Sem filtro, a resposta é `400` e nenhum documento é tocado.

---

## Arquivo de configuração

```jsonc
{
  "Settings":   { /* ajustes globais, opcional */ },
  "Schematics": { /* como cada tipo de registro é montado */ },
  "DataBase":   { /* quais bancos existem e de que tamanho */ }
}
```

### Settings

| Campo | Padrão | Descrição |
| --- | --- | --- |
| `locale` | `pt_BR` | Idioma/país dos dados falsos |
| `seed` | — | Semente aleatória; sem ela cada execução gera dados diferentes |
| `storage` | `sqlite` | Backend do NoSQL: `sqlite`, `flatfile` ou `memory` |
| `storagePath` | `./.fakebase` | Pasta dos dados |
| `database` | `fakebase` | Nome do banco dentro do NoSQL |
| `idGenerator` | `objectId` | Gerador usado para o `_id` automático |
| `minSize` / `maxSize` | `10` / `50` | Faixa do tamanho sorteado quando o banco não declara `size` |
| `host` / `port` | `127.0.0.1` / `8080` | Endereço do servidor |
| `cors` | `true` | Libera CORS (útil para front-ends locais) |
| `latency` | `0` | Atraso artificial por requisição, em ms |

### Schematics

Um schematic é um conjunto de campos. Cada campo aponta para um gerador:

```json
{
  "Schematics": {
    "user": {
      "name": "humanName",
      "age": { "method": "number", "numberType": "int", "start": 10, "stop": 40 }
    }
  }
}
```

- `"campo": "nomeDoGerador"` usa o gerador com os padrões dele.
- `"campo": { "method": "...", ... }` permite passar parâmetros.
- Um texto que não seja nome de gerador vira **valor fixo**: `"pais": "Brasil"`.

Além dos parâmetros do gerador, todo campo aceita:

| Chave | Efeito |
| --- | --- |
| `transform` | Aplica um ou mais [transforms](#transforms) ao valor gerado |
| `unique` | Garante que o valor não se repita dentro do banco |
| `nullable` | Probabilidade (0 a 1) de o campo vir `null` |

```json
"email":   { "method": "email", "name": "__name", "unique": true },
"shipped": { "method": "isoDate", "dateType": "past", "nullable": 0.3 },
"price":   { "method": "number", "start": 10, "stop": 90, "transform": ["round", "currency"] }
```

Todo schematic ganha um `_id` automático (um `objectId`, único) caso você não
declare um.

### DataBase

```json
{
  "DataBase": {
    "users":    { "schema": "user", "size": 25 },
    "products": "product",
    "orders":   { "schema": "order", "size": [30, 60] }
  }
}
```

- `size` fixa a quantidade de linhas; `[min, max]` sorteia dentro do intervalo.
- Sem `size`, o tamanho é sorteado entre `minSize` e `maxSize`.
- Se algum campo usar um gerador sem repetição (`repeat: false`), o tamanho é
  limitado pela quantidade de valores disponíveis — e o `generate` avisa.
- O nome do banco é o caminho da rota: `users` → `/users`.

---

## Geradores

`fakebase generators` lista tudo com os parâmetros; `GET /_generators` devolve o
mesmo catálogo em JSON.

**Pessoas** — `humanName` (`gender`, `valueFormat`), `firstName`, `lastName`,
`email` (`name`, `domain`), `username`, `password`, `phone`, `cpf`, `cnpj`.

**Lugares** — `address`, `street`, `city`, `state` (`abbr`), `country`,
`postcode`, `coordinates`.

**Negócios** — `company`, `jobTitle`, `creditCard`, `currencyCode`.

**Números** — `number` (`start`, `stop`, `numberType`, `precision`, `step`),
`integer`, `boolean` (`chance`).

**Tempo** — `date` (`valueFormat`, `dateType`, `dataRange`, `start`, `stop`),
`isoDate`, `timestamp`, `time`.

**Texto** — `word`, `sentence`, `paragraph`, `text`, `slug`, `template`
(interpola campos da própria linha), `pattern` (máscara: `#` dígito, `?` letra
minúscula, `!` maiúscula).

**Listas** — `choice` (`data`, `repeat`, `weights`), `chooseSeveral`
(`minValue`, `maxValue`, `size`), `sequence`, `numericSequence`,
`randomSequence`, `shuffle`.

**Identificadores** — `objectId`, `uuid`, `randID` (`IDType`, `size`, `prefix`),
`autoIncrement`.

**Estruturas** — `object` (campos aninhados), `array` (lista de valores gerados).

**Web e mídia** — `url`, `domain`, `ipv4`, `ipv6`, `macAddress`, `userAgent`,
`color`, `imageUrl`, `fileName`, `mimeType`.

**Avançado** — `faker`, que abre todos os *providers* do Faker:

```json
"placa": { "method": "faker", "provider": "license_plate" },
"iban":  { "method": "faker", "provider": "iban" }
```

O parâmetro `data` de `choice`, `chooseSeveral`, `sequence`, `randomSequence` e
`shuffle` aceita três formas: uma lista literal, o caminho de um arquivo de texto
(um valor por linha, como `productsName.txt`) ou uma
[referência a outro banco](#ligação-entre-bancos-de-dados).

Objetos e listas aninhados:

```json
"address": {
  "method": "object",
  "fields": {
    "city": "city",
    "state": { "method": "state", "abbr": true },
    "zipCode": "postcode"
  }
},
"tags": { "method": "array", "of": { "method": "word" }, "min": 1, "max": 3 }
```

---

## Transforms

Transforms rodam depois do gerador. Podem ser um nome, um objeto com parâmetros ou
uma lista aplicada em sequência:

```json
"price": {
  "method": "number", "start": 10, "stop": 90,
  "transform": [{ "method": "round", "digits": 2 }, "currency"]
}
```

**Texto** — `upper`, `lower`, `title`, `capitalize`, `trim`, `prefix`, `suffix`,
`replace`, `truncate`, `pad`, `hide`, `slug`.
**Números** — `round`, `floor`, `ceil`, `abs`, `multiply`, `currency`, `toInt`,
`toFloat`, `toString`, `toBool`.
**Datas e listas** — `dateFormat`, `join`, `split`, `unique`, `sort`, `length`,
`pluck`, `sum`, `jsonString`.

`fakebase generators --transforms` mostra os parâmetros de cada um.

---

## Ligação entre campos

Um campo pode usar o valor de outro campo da mesma linha com o prefixo `__`:

```json
{
  "gender": { "method": "choice", "data": ["male", "female"] },
  "name":   { "method": "humanName", "gender": "__gender" },
  "email":  { "method": "email", "name": "__name" }
}
```

O FakeBase resolve a ordem sozinho — `gender` é gerado antes de `name`, mesmo
aparecendo depois. Dependências circulares são detectadas e reportadas com o
caminho completo.

---

## Ligação entre bancos de dados

Um campo pode buscar dados de outro banco com a sintaxe:

```
@banco:campos:condições:quantidade@
```

Só o nome do banco é obrigatório; as outras partes podem ficar vazias.

```json
"cart": {
  "method": "chooseSeveral",
  "data": "@products:[_id,name,price]:price<50@",
  "repeat": false,
  "maxValue": 4
}
```

| Parte | Formas aceitas |
| --- | --- |
| `campos` | vazio (documento inteiro), `name` (lista de valores desse campo), `[name,price]` (lista de objetos) |
| `condições` | `price<50`, `price<50 and stock>0`, `status==pago,ativo` (lista = "um destes"), `name~=bata` (contém), `or` também funciona |
| `quantidade` | vazio ou `all` (todos), `3` (sorteia 3 por linha), `[1,4]` (sorteia entre 1 e 4) |

```
"@products@"                      todos os produtos
"@products:name@"                 só os nomes, como lista de textos
"@products:_id::3@"               três ids diferentes para cada linha
"@users:[_id,name]:active==true@" usuários ativos, com dois campos
```

A ordem de geração é deduzida das referências (`products` antes de `users`), e
referências circulares entre bancos são detectadas antes de qualquer coisa ser
gerada.

> **Mudança em relação à 1.x:** a quantidade é sorteada **por linha**, então cada
> registro recebe uma seleção diferente; antes o sorteio valia para o banco todo.
> E `@products:name@` agora devolve `["Arroz", "Feijão"]` em vez de
> `[{"name": "Arroz"}, ...]` — para objetos, use `[name]`.

---

## Onde os dados ficam

Por padrão, em `./.fakebase` (SQLite, gerenciado pelo MontyDB). A pasta pode ser
apagada à vontade: `fakebase generate` reconstrói tudo.

- `--storage sqlite` — padrão, um arquivo por coleção dentro da pasta.
- `--storage flatfile` — arquivos de texto, mais fáceis de inspecionar.
- `--storage memory` — nada é gravado; útil em testes e demonstrações.

Precisa dos JSONs do jeito antigo? `fakebase export ./fakeBase` gera um arquivo
por banco, no mesmo formato `{"users": [...]}` da versão 1.x. E `fakebase import`
faz o caminho de volta.

Como o MontyDB implementa a API do PyMongo, trocar o armazenamento por um MongoDB
de verdade é questão de substituir o cliente em `fakebase/storage/monty.py`; o
resto do código conversa apenas com a interface descrita em
`fakebase/storage/base.py`.

---

## Testes

```bash
pip install -r requirements.txt
python -m pytest
```

A suíte cobre consultas, geradores, transforms, schematics, referências entre
bancos, persistência, CLI e todas as rotas HTTP (inclusive as da versão 1.x).

---

## Migrando da versão 1.x

1. Seu `config.fakebase.json` continua válido. Se quiser, acrescente um bloco
   `Settings` com `locale` e `seed`.
2. `--fakepath` agora aponta para a pasta do NoSQL, não para uma pasta de JSONs.
   Para continuar gerando os arquivos, use `fakebase generate --export ./fakeBase`.
3. Os arquivos `.json` antigos podem ser recarregados com
   `fakebase import ./fakeBase`.
4. Referências entre bancos: reveja o formato dos campos (`name` versus `[name]`),
   conforme a nota acima.
5. As rotas antigas continuam funcionando; as de escrita passaram a exigir filtro.

---

## Estrutura do projeto

```
fakebase/
  cli.py            comandos de linha de comando
  config.py         leitura e validação do config.fakebase.json
  schematic.py      montagem de uma linha, com dependências entre campos
  references.py     referências @banco:campos:condições:quantidade@
  manager.py        orquestração: ordem de geração, tamanhos, CRUD, import/export
  query.py          query string -> filtro no dialeto MongoDB
  pipes.py          transforms
  generators/       catálogo de geradores de valores
  storage/          interface de persistência + implementação MontyDB
  api/              aplicação FastAPI
tests/              suíte pytest
```
