import click
import json
import os
import random

from context import Context
from customTypes import Schemas, DataBaseValue
from controllers.generatorFields import generatorFields
from models.Schematic import Schematic
from models.enums import ReservedWords
from View.server import start_server

@click.group()
@click.option('--path', default='./config.fakebase.json')
@click.option('--router', default=None)
@click.option('--fakepath',default="./fakeBase")
@click.pass_context
def fb(ctx, path, router, fakepath):
    context = Context(path,router, fakepath)
    context.jsonConfig = load_json_config(context)
    ctx.obj = context

@fb.command()
@click.pass_obj
def start(context: Context):
    generate_fake_database(context)
    start_server(context)

@fb.command()
@click.pass_obj
def server(context: Context):
    start_server(context)

@fb.command()
@click.pass_obj
def generate(context: Context):
    generate_fake_database(context)

def load_json_config(context: Context) -> dict:
    path = context.path
    assert os.path.isfile(path), f'Error! File {path} not found.'
    assert os.path.getsize(path) != 0, f'Error! File {path} is empty.'
    with open(path, 'r') as json_file:
        jsonConfig = preprossing(json.load(json_file))
    return jsonConfig

def preprossing(jsonConfig: dict):
    jsonConfig[ReservedWords.SCHEMATICS.value] = preprossing_schema(jsonConfig[ReservedWords.SCHEMATICS.value])
    return jsonConfig

def preprossing_schema(schema: Schemas):
    for key in schema:
        if '_id' not in schema[key]:
            schema[key]['_id'] = 'randID'
    return schema

def generate_fake_database(context: Context):
    if not os.path.isdir(context.fakeBasePath):
        os.mkdir(context.fakeBasePath)
    for key, value in zip(context.dataBase.keys(),context.dataBase.values()):
        databaseParans: dict = get_database_parans(value)
        assert databaseParans['schema'] in context.schemas, f'Schema {databaseParans["schema"]} not exist'
        schematic = Schematic(**context.schemas[databaseParans['schema']])
        count = get_database_count(databaseParans)
        with open(os.path.join(context.fakeBasePath,key+'.json'), 'w',newline='') as file:
            value ={key:[schematic.generate_values() for _ in range(count)]}
            json.dump(value,file,indent=4)

def get_database_parans(dataBase: DataBaseValue):
    if isinstance(dataBase,str):
        return {'schema': dataBase}
    assert 'schema' in dataBase, 'Erros! schema not specified'
    return dataBase

def get_database_count(databaseParans: dict) -> int:
    if 'count' in databaseParans:
        return databaseParans['count']
    return random.randint(10,50)

if __name__ == '__main__':
    fb()