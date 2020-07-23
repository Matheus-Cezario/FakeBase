from customTypes import Schemas, DataBaseValue
from models.Schematic import Schematic
from controllers.generatorFields import generatorFields
import random
from typing import List

class Database:

    def __init__(self, name,value):
        super().__init__()
        self.schematic: Schematic = None
        self.name = name
        self.value: dict = self.prepare_value(value)
    
    def prepare_value(self, value: DataBaseValue) -> dict:

        if isinstance(value,str):
            return {'schema': value}
        assert 'schema' in value, 'Erros! schema not specified'
        return value

    def generate_values(self):
        assert self.schematic is not None, 'Schematic is None'
        print('size',self.size)
        return [self.schematic.generate_values() for _ in range(self.size)]

    @property
    def size(self):
        if 'realSize' in self.value:
            return self.value['realSize']
        size_restriction = self.get_size_restriction()
        if size_restriction is None and 'size' not in self.value:
            self.value['realSize'] = random.randint(10,50)
        elif (size_restriction and 'size' in self.value and int(self.value['size']) > size_restriction) or 'size' not in self.value:
            self.value['realSize'] = size_restriction
        elif 'size' in self.value:
            self.value['realSize'] = self.value['size']
        return self.value['realSize']
        
    def get_size_restriction(self):
        generator = generatorFields()
        size_restriction = []
        for value in self.schematic.schema.values():
            if isinstance(value,str):
                method = value
            else:
                method = value['method']
            resp = generator.get_size_restriction(method)
            if resp:
                size_restriction.extend(self.calc_restriction(value,resp))
        v = min(size_restriction,default=None)
        return v
    
    def calc_restriction(self, value,restriction: dict):
        limit = []
        for r in restriction:
            if (isinstance(value,dict) and r['method'] == value['method']):

                if 'if' in r and self.condition_is_true(r['if'],value) and r['limit_len'] in value:
                    limit.append(self.calc_len(value[r['limit_len']]))
        return limit
    
    def calc_len(self,value):
        if isinstance(value, str):
            with open(value) as file:
                value = file.readlines()
        return len(value)
    
    def condition_is_true(self,condition: str,value):
        op = ['==','>','<','>=','<=','!=']
        if any([k in condition for k in op]):
            l = condition.split(' ')
            for t in l:
                t = t.strip()
                if t in value:
                    condition = condition.replace(t,str(value[t]))
            try:
                return eval(condition)
            except:
                return False
        elif condition in value:
            return value[condition]