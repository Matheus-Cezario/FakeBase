# FakeBase

## Comandos:

* generate

    Gera os arquivos JSON

* server

    Inicia o servidor

* start

    Gera os arquivos JSON e inicia o servidor

## Opições:
* --path
    Caminho para o arquivo de configuração, padrão `./config.fakebase.json`
* --fakepath
    Caminho para a pasta onde os arquivos vão ser gerados, padrão `./fakebase`

> Uso: python FakeBase.py [OPTIONS] COMMAND

## EndPoints
* \
> Url: http://localhost:8080

Lista os bancos de dados existentes

* list
> Url: http://localhost:8080/list/<key\>

Lista os itens de um banco de dados
key: Nome do banco de dados que vai ser consultado
* Query params
    paginate: Diz se a paginação está ativa, padrão `False`
    pageCount: Número de itens por página, padrão 10
    page: página, padrão 1

    kwargs: Vai conter todos os outros queryParams, estes serão usados como filtros
    - Caso vazio retorna a lista toda
    - Caso contrário retorna apenas aqueles que tiveram os campos contidos em kwargs iguais.
### Exemplo
>  http://localhost:8080/list/users
* Retorna todos os itens do arquivo users.json
>  http://localhost:8080/list/users?gender=male
* Retorna todos os itens do arquivo users.json cujo campo gender seja igual a male
>  http://localhost:8080/list/users?paginate=true&pageCount=4&page=2
* Retorna a segunda pagina com 4 itens dos itens do arquivo users.json, retorna também o total de itens, total de páginas

* get
> Url: http://localhost:8080/get/<key\>

Retorna um item do banco de dados

key: Nome do banco de dados que vai ser consultado
* Query params
    kwargs: Vai conter todos os queryParams, estes serão usados como filtros
    * Caso vazio retorna o primeiro da lista
    * Caso contrário retorna o primeiro que tiver os campos contidos em kwargs iguais.

* delete
> Url: http://localhost:8080/delete/<key\>

Deleta um ou vários itens de um banco de dados, retorna a lista de elementos deletados
key: Nome do banco de dados
* Query params
    kwargs: Vai conter todos os queryParams, estes serão usados como filtros
    * Caso vazio nada será deletado

    every: Indica se a ação se aplica a mais de um elemento
    * Caso true, todos os elementos que passarem no filtro serão deletados
    * Padrão: false

* update
> Url: http://localhost:8080/update/<key\>

Atualiza um ou varios itens de um banco de dados, retorna a lista de elementos atualizados
key: Nome do banco de dados
* Query params
    kwargs: Vai conter todos os queryParams, estes serão usados como filtros
    * Caso vazio nada será atualizado

    every: Indica se a ação se aplica a mais de um elemento
    * Caso true, todos os elementos que passarem no filtro serão atualizados
    * Padrão: false

* body
O *body* é um *JSON* contendo os campos que vão ser atualizados e seus valores.

* set
> Url: http://localhost:8080/set/<key\>

Substitui um ou varios itens de um banco de dados
key: Nome do banco de dados
* Query params
    kwargs: Vai conter todos os queryParams, estes serão usados como filtros
    * Caso vazio nada será substituido

    every: Indica se a ação se aplica a mais de um elemento
    * Caso true, todos os elementos que passarem no filtro serão substituidos
    * Padrão: false

* body
O *body* é um *JSON* que irá substituir os campos.


### Exemplo
>  http://localhost:8080/get/users
* Retorna o primeiro item do arquivo users.json
>  http://localhost:8080/get/users?gender=male
* Retorna o primeiro item do arquivo users.json cujo campo gender seja igual a male

## Como construir os Schematics
Schematics são os padrões usados pra construir os bancos de dados.
Eles devem ficar dentro do arquivo especificado pelo `--fakepath` dentro do campo `Schematics`
### Exemplo
```JSON
{
  "Schematics": {
    "user": {
      "name":  "humanName",
      "age": {
        "method": "number",
        "numberType": "int",
        "start": 10,
        "stop": 40
      },
    },
  },
```
Aqui criamos um *Schema* chamado `users` que possui dois campos.
* name: Cujo o *gerador* é o método `humanName`.
* age: Cujo o *gerador* é o método `number` 

## Como construir o DataBase
O *DataBase* deve ser descrito no mesmo arquivo que o *Schematics*, no campo *DataBase*.

### Exemplo

```JSON
  "DataBase": {
      "users":{
        "schema":"user",
        "size": 10
      },
      "products": "product"
  }
```
Aqui criamos dois *DataBase*, um chamado users que vai ter como *schema* o *schematic user*  e vai ter dez linhas.
O segundo se chama *products* vai como *schema* o *schematic product* seu numero de linhas é aleatório.
Os nomes usados no *DataBase* serão usados como *endPoint* da aplicação

## Geradores

Geradores são responsáveis por gerar os valores para os *schematics*.
São usados das seguintes maneiras:
```JSON
{
    "campo": "nome do gerador"
}
```
Assim estará usando as configurações padrão do gerador, para alterar essas configurações use o formato `JSON`
```JSON
{
    "campo": {
        "method": "nome do gerador"
        /* Outros parâmetros... */
    }
}
```
### Lista de geradores

* humanName
    * Gera um nome aleatório
    * parâmetros
        *  gender: gênero do nome, padrão `None`
            * Opções: `male | female | None`
        * valueFormat: Formato do nome, padrão `None`
            * Opções: `['first','last'] | None` 
* date
    * Gera uma data aleatória
    * parâmetros
        * valueFormat: Formato da data, padrão `%d/%m/%Y %H:%M:%S`
        * dateType: Indica se é uma data futura ou não, padrão `all`
            * Opções: `past | all | future`
        * dataRange: Indica o deslocamento máximo das datas em anos para o ano atual, padrão 20
* number
    * Gera um número aleatório
    * parâmetros
        * start: número inicial padrão -1000
        * stop: número final padrão 1000
        * numberType: tipo do número, padrão `float`
            * Opções: `float | int`
        * precision: Precisão do número, padrão 10
* randID
    * Gera um ID aleatório
    * parâmetros
        * IDType: Base numérica do ID, padrão `hex`
            * Opções: `hex | dec`
        * size: Tamanho do IS, padrão 16
* choice
    * Escolhe um valor aleatório dentre uma lista
    * parâmetros
        * data: Pode ser uma lista com os valores ou uma *string* com o caminho para um arquivo com os valores, cada um em uma linha
            * Observação: *data* é um parâmetro obrigatório
        * repeat: Indica se os valores podem se repedir, padrão `True`
            * Observação: Caso o *repeat* seja `False` e o `size` do *DataBase* que usa esse *schema* não for definido, ele será limitado pelo tamanho de *data*
* chooseSeveral
    * Escolhe um número aleatório de valores de uma lista
    * parâmetros
        * data: Pode ser uma lista com os valores ou uma *string* com o caminho para um arquivo com os valores, cada um em uma linha
            * Observação: *data* é um parâmetro obrigatório
        * repeat: Indica se os valores podem se repedir, padrão `True`
        * minValue: Número mínimo de valores que podem ser escolhidos, padrão 0
        * maxValue: Número máximo de valores que podem ser escolhidos, padrão `len(data)`

* sequence
    * Retorna um item de uma lista de forma sequencial
    * parâmetros
        * data: Pode ser uma lista com os valores ou uma *string* com o caminho para um arquivo com os valores, cada um em uma linha
            * Observação: *data* é um parâmetro obrigatório
        * repeat: Indica se os valores podem se repedir, padrão `True`
* numericSequence
    * Retorna uma lista de números sequenciais
    * parâmetros
        * start: Começo da lista, padrão 0
        * stop: Fim da lista, padrão 10
        * step: Passo da lista, padrão 1

* randomSequence
    * Retorna uma fatia aleatória de uma lista
    * parâmetros
        * data: Pode ser uma lista com os valores ou uma *string* com o caminho para um arquivo com os valores, cada um em uma linha
            * Observação: *data* é um parâmetro obrigatório
        * size: Tamanho da fatia, padrão `len(data)/3`



## Ligação entre campos
Um campo de um *schematic* pode referênciar a outro campo desse mesmo *schematic* usando o padrão `@nome_dataBase,campo(s),condições,count@`

## Exemplo

```JSON
{
    "Schematics": {
    "user": {
      "name": {
        "method": "humanName",
        "gender": "__genre"
      },
      "age": {
        "method": "number",
        "numberType": "int",
        "start": 10,
        "stop": 40
      },
      "genre": {
        "method": "choice",
        "data": ["male", "female"]
      },

    }
  }
}
```

Nesse exemplo o parâmetro *gender*  usado no campo *name* faz uma referência ao campo *genre*, assim *gender* vai ter sempre o mesmo valor que *genre*


## Ligação entre bancos de dados
Um campo de um *schematic* pode referênciar a outro *dataBase* usando o padrão `__nomeDoCampo`

## Exemplo

```JSON
{
  "Schematics": {
    "user": {
      "name": "humanName",
      "card": {
        "method": "chooseSeveral",
        "data": "@products:name:price<40:2@",
        "repeat": false
      }
    },
    "product": {
      "price": {
        "method": "number",
        "start": 10,
        "stop": 90,
        "precision": 2
      },
      "name": {
        "method": "choice",
        "data": "productsName.txt",
        "repeat": false
      }
    }
  },
  "DataBase": {
      "users":{
        "schema":"user",
        "size": 10
      },
      "products":  "product"
  }
}

```

Nesse exemplo o parametro *data* do campo *card* faz uma referência ao *dataBase products*, dos elementos do *dataBase products* será retornado apenas o campo *name*, para retornar mais campos basta colocá-los entre colchetes `[name,_id]`, para esse exemplo limitamos no *card* apenas os *products* cujo o *price* for menor de 40 e por fim serão retornados 2 elementos como especifica o *count*

A referência para *dataBase* sempre retorna uma lista.
