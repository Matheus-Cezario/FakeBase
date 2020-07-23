
from customTypes import Schemas, DataBase as DataBaseType
from models.DataBase import Database 
from models.Schematic import Schematic
from context import Context
from typing import List, Union
from utils.functions import find, str_schema_replace, strToList

import re
import json
import random
import os

class DataBaseManager:
    
    def __init__(self, context: Context):
        super().__init__()
        self.dataBase: DataBaseType = context.dataBase
        self.schemas: Schemas = context.schemas
        self.context = context
        self.dependency = re.compile(r'@?(.*?)[:|@]')
        self._generate_database_list()
    
    def _generate_database_list(self):
        self.database_list: List[Database] = []
        for key, value in zip(self.dataBase.keys(),self.dataBase.values()):
            dataBase = Database(key,value)
            assert dataBase.value['schema'] in self.schemas, f'Schema {dataBase.value["schema"]} not exist'
            dataBase.schematic = Schematic(**self.schemas[dataBase.value['schema']])
            self.database_list.append(dataBase)

    def generate_all_databases(self):
        self.dataBaseValue = {}
        for key in self.dataBase.keys():
            self._generate_database(key)
        return self.dataBaseValue

            

    def _generate_database(self,key):
        if key in self.dataBaseValue:
            return
        el: Database = find(lambda x: x.name == key,self.database_list)
        assert el, f'DataBase {key} not found in database_list'
        dependencies = self.get_dependencies(el)
        if dependencies and len(dependencies):
            self.resolver_dependencies(dependencies)
            self.update_dependencies(el,dependencies)
        
        self.dataBaseValue[key] = el.generate_values()
    
    def resolver_dependencies(self,dependencies):
        for dependency in dependencies:
            self._generate_database(dependency[0])

    def update_dependencies(self,el: Database,dependencies):
        str_schema = str(el.schematic.schema)
        for dependency in dependencies:
            variable = '@'+':'.join(dependency)+'@'
            str_schema = str_schema_replace(str_schema,variable,self.calculate_dependency(dependency))
        el.schematic.schema = json.loads(str_schema)
 

    def calculate_dependency(self,dependency):
        name = dependency[0]
        assert name in self.dataBaseValue, f'DataBase {name} not found in dataBaseValue'
        fields = self.dataBaseValue[name]
        size = len(dependency)
        dependency_fields = None
        conditions = None
        count = None
        if size > 1:
            dependency_fields = self._get_fields(dependency[1])
        if size > 2:
            conditions = dependency[2]
        if size > 3:
            count = self._get_count(dependency[3])

        fields = self._filter_fields(fields,dependency_fields)
        fields = self._filter_conditions(fields,conditions)
        fields = self._filter_count(fields,count)
        return fields


    def _get_fields(self,fields:str):
        resp = strToList(fields)
        return resp if resp else fields
    
    def _get_count(self,count:str):
        resp = strToList(count)
        if resp:
            resp = list(map(int,resp))
            return random.randint(resp[0],resp[1]) 
        if isinstance(count,str):
            return count
        return int(count)
    
    def _filter_fields(self,fields, dependency_fields):
        if not dependency_fields or dependency_fields == 'None':
            return fields
        resp = []
        if not isinstance(dependency_fields,list):
            dependency_fields = [dependency_fields]
        for field in fields:
            r ={}
            for dependency_field in dependency_fields:
                if dependency_field in field:
                    r[dependency_field] = field[dependency_field]
            resp.append(r)
        return resp
    

    def _filter_count(self,fields: list,count):
        if isinstance(count, str) and count == 'all':
            return fields
        if isinstance(count, str) and count == 'None':
            count = None
        fieldsC = fields.copy()
        if not count and len(fieldsC):
            c = random.randint(0, len(fieldsC))
            l = []
            for _ in range(c):
                l.append(random.choice(fieldsC))
                fieldsC.remove(l[-1])
            return l
        if len(fieldsC) <= count:
            return fieldsC
        return fieldsC[0:count]

    
    def _filter_conditions(self,fields,conditions:str):
        if conditions == 'None' or conditions == None:
            return fields
        operatorsPattern = re.compile(r'\=\=|\>|\<|\>\=|\<\=|\!\=')
        operators = operatorsPattern.findall(conditions)
        conditionsCopy = conditions
        for op in operators:
            conditionsCopy = conditionsCopy.replace(op,'@-@')
        conditionsList = conditionsCopy.split('@-@')
        fieldsResp =[]
        for field in fields:
            conditionsCopy = conditions
            for condition in conditionsList:
                if condition in field:
                    conditionsCopy = conditionsCopy.replace(condition,str(field[condition]))
            try:
                resp = eval(conditionsCopy)
                if resp:
                    fieldsResp.append(field)
            except:
                ...
        return fieldsResp


    def get_dependencies(self, el: Database):
        schema = el.schematic.schema
        dependencies = []
        for value in schema.values():
            match = self._match_dependency(value)
            # if len(match) != 0:
            dependencies.extend(match)

        return dependencies if len(dependencies) != 0 else None

    def _match_dependency(self,value: Union[dict,str,list]):
        dependencies = []
        if isinstance(value,str):
            match = self.dependency.findall(value)
            if len(match) != 0:
                dependencies.append(match)
        elif isinstance(value,list):
            for item in value:
                dependencies.extend(self._match_dependency(item))
        elif isinstance(value,dict):
            for item in value.values():
                dependencies.extend(self._match_dependency(item))
        
        return dependencies

    def list_databases(self):
        return self.dataBase.keys()

    def list_database(self,key,**kwargs):
        if key not in self.list_databases():
            return (404,f'DataBase {key} not found.')
        path = os.path.join(self.context.fakeBasePath,key+'.json')
        with open(path) as file:
            json_file: dict = json.load(file)
            json_list = []
            for value in json_file[key]:
                if len(kwargs) == 0 or self.contais_equals(value,kwargs):
                    json_list.append(value)
        return json_list
    
    def getItem(self,key,**kwargs):
        if key not in self.list_databases():
            return (404,f'DataBase {key} not found.')
        path = os.path.join(self.context.fakeBasePath,key+'.json')
        with open(path) as file:
            json_file: dict = json.load(file)
            for value in json_file[key]:
                if  len(kwargs) == 0 or self.contais_equals(value,kwargs):
                    return value
        return {}

    def contais_equals(self,el: dict,condition: dict):
        if len(condition) == 0:
            return False
        for key in condition.keys():
            if key not in el or not self.equals(el[key], condition[key]):
                return False
        return True
    
    def equals(self,one,two):
        if type(one) == type(two):
            return one == two
        try:
            two = type(one)(two)
            return one == two
        except:
            return False
    
    def deleteItem(self,key,every,**kwargs):
        if key not in self.list_databases():
            return (404,f'DataBase {key} not found.')
        if len(kwargs) == 0:
            return (400,'Item not found')
        path = os.path.join(self.context.fakeBasePath,key+'.json')
        resp = []
        with open(path) as file:
            json_file: dict = json.load(file)
            for value in json_file[key]:
                if self.contais_equals(value,kwargs):
                    json_file[key].remove(value)
                    resp.append(value)
                    if not every:
                        break
        with open(path,'w') as file:
            json.dump(json_file,file,indent=4)
        return resp
    
    def updateItem(self,key,newValue,every,**kwargs):
        if key not in self.list_databases():
            return (404,f'DataBase {key} not found.')
        if len(kwargs) == 0:
            return (400,'Item not found')
        path = os.path.join(self.context.fakeBasePath,key+'.json')
        resp = []
        with open(path) as file:
            json_file: dict = json.load(file)
            for index, value in enumerate(json_file[key]):
                if self.contais_equals(value,kwargs):
                    r = {**value,**newValue}
                    json_file[key][index] = r
                    resp.append(r)
                    if not every:
                        break
        with open(path,'w') as file:
            json.dump(json_file,file,indent=4)
        return resp

    def setItem(self,key,newValue,every,**kwargs):
        if key not in self.list_databases():
            return (404,f'DataBase {key} not found.')
        if len(kwargs) == 0:
            return (400,'Item not found')
        path = os.path.join(self.context.fakeBasePath,key+'.json')
        resp = {}
        with open(path) as file:
            json_file: dict = json.load(file)
            for index, value in enumerate(json_file[key]):
                if self.contais_equals(value,kwargs):
                    resp = newValue
                    json_file[key][index] = resp
                    if not every:
                        break
        with open(path,'w') as file:
            json.dump(json_file,file,indent=4)
        return resp

        
      