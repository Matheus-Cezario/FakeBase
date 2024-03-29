from customTypes import Schemas, SchemaValue
from controllers.generatorFields import generatorFields
from utils.functions import str_schema_replace
import json
import collections


class Schematic:

    def __init__(self,**kwargs):
        super().__init__()
        self.genarator = generatorFields()
        self.schema: dict = kwargs
        self.values = {}
    
    def get_fieldnames(self) -> list:
        return self.schema.keys()

    def generate_values(self) -> dict:
        self.values = {}
        for key, value in zip(self.schema.keys(), self.schema.values()):
            if isinstance(value, dict):
                self.generate_value_by_type(key=key,**value)
            else:
                self.generate_value_by_type(key=key,method=value)
        return self.values

    def generate_value_by_type(self,key,**kwargs):
        if key in self.values:
            return
        kwargs = self.resolver_dependencyes(**kwargs)
        resp = self.genarator.generate(**kwargs)
        if isinstance(resp, tuple):
            self.values[key] = resp[0]
            self.schema[key][resp[2]] = resp[1]
        else:
            self.values[key] = resp
    
    def resolver_dependencyes(self,**kwargs):
        dependencyes = self.get_dependencyes(kwargs)
        if len(dependencyes) != 0:
            for dependency in dependencyes:
                self.calculate_dependencyes(dependency)
                kwargs = self.update_dependency(dependency,kwargs)
        return kwargs

                

    def calculate_dependencyes(self, dependency):
        if dependency in self.values:
            return
        if isinstance(self.schema[dependency], dict):
            self.generate_value_by_type(key=dependency,**self.schema[dependency])
        else:
            self.generate_value_by_type(key=dependency,method=self.schema[dependency])

    def update_dependency(self, dependency, schema):
        variable = "__"+dependency
        str_schema = str(schema)
        str_schema = str_schema_replace(str_schema,variable,self.values[dependency])

        return json.loads(str_schema)
    

        
    def get_dependencyes(self,values: SchemaValue) -> list:
        dependencyes = []
        if isinstance(values,str):
            if values.startswith('__'):
                dependencyes.append(values.replace('__',''))
        elif isinstance(values,dict):
            for key, value in zip(values.keys(), values.values()):
                if isinstance(value,str) and value.startswith('__'):
                    dependencyes.append(value.replace('__',''))
                elif isinstance(value,list):
                    for i in value:
                        d = self.get_dependencyes(i)
                        dependencyes.extend(d)
                elif isinstance(value,dict):
                    dependencyes.extend(self.get_dependencyes(value))
        return set(dependencyes)