import random
import names
import re
import time
from datetime import datetime,timedelta

class valuesGenerator:
    def __init__(self):
        self.methodsName =  [func for func in dir(self) if callable(getattr(self, func)) and not func.startswith("__")]
    
    def call_function(self, method: str, **kwargs) -> str:
        if method not in self.methodsName:
            return method
            # raise Exception(f'Method {method} not found')
        return self[method](**kwargs)
    
    def __getitem__(self, key):
        return getattr(self,key)
    

class humanValuesGenerator(valuesGenerator):
    
    def __init__(self):
        super().__init__()
    
    def humanName(self, gender=None,valueFormat=None):
        if not valueFormat:
            return names.get_full_name(gender)
        name = ''
        for position in valueFormat:
            name += self.get_name_by_position(position, gender) + ' '
        name = name[:-1]
        return name
    def get_name_by_position(self, position, gender=None):
        if position == 'first':
            return names.get_first_name(gender)
        return names.get_last_name()

    def date(self,valueFormat = "%d/%m/%Y %H:%M:%S",dateType = "all", dataRange=20):
        present = datetime.now()
        future = datetime.strptime(f'31/12/{present.year + dataRange} 00:00:00', '%d/%m/%Y %H:%M:%S')
        past = datetime.strptime(f'01/01/{present.year - dataRange} 00:00:00', '%d/%m/%Y %H:%M:%S')

        if dateType == 'all':
            start = past
            stop = future
        elif dateType == 'future':
            start = present
            stop = future
        else:
            stop = present
            start = past
        return self.randomdate(start,stop).strftime(valueFormat)
    
    def randomdate(self, start: datetime, end: datetime):
        delta = end - start
        int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
        
        random_second = random.randrange(int_delta)
        return start + timedelta(seconds=random_second)

class numberValuesGenerator(valuesGenerator):
    
    def __init__(self):
        super().__init__()
    
    def number(self,start=-1000,stop=1000,numberType='float',precision=10):
        resp = (random.random() * (stop-start)) + start
        if numberType == 'float':
            return round(resp,int(precision))
        return int(resp)

class randomValuesGenerator(valuesGenerator):
    def __init__(self):
        super().__init__()
    
    def randID(self, IDType='hex',size=16):
        if IDType == 'hex':
            return self.randHex(size)
        return self.randDec(size)
    def randHex(self,size):
        values = "abcdef0123456789"
        resp = ''
        for _ in range(size):
            resp += random.choice(values)
        return resp
    def randDec(self,size):
        values = "0123456789"
        resp = ''
        for _ in range(size):
            resp += random.choice(values)
        return resp
    def choice(self, data, **kwargs):
        if isinstance(data, str):
            with open(data) as file:
                data = file.readlines()
        return random.choice([self.normalize_string(s) for s in data])
    
    def normalize_string(self, text: str):
        if not isinstance(text,str):
            return text
        text = text.replace('\n','')
        text = re.sub(r'\s+',' ',text)
        return text