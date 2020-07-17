import random
import names
import re
import time
from datetime import datetime,timedelta
from utils.decorators import preprocessingParamenters
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
    
    @preprocessingParamenters
    def humanName(self, gender:str=None, valueFormat: list=None):
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

    @preprocessingParamenters
    def date(self,valueFormat: str = "%d/%m/%Y %H:%M:%S",dateType: str = "all", dataRange: int = 20):
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
    
    @preprocessingParamenters
    def number(self,start: float =-1000.0,stop:float =1000.0,numberType: str ='float',precision: int=10):
        resp = (random.random() * (stop-start)) + start
        if numberType == 'float':
            return round(resp,precision)
        return int(resp)

class randomValuesGenerator(valuesGenerator):
    def __init__(self):
        super().__init__()

    @preprocessingParamenters
    def randID(self, IDType: str='hex',size: int=16):
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

    def choice(self, data, repeat=True,):
        if isinstance(data, str):
            with open(data) as file:
                data = file.readlines()
        value = random.choice(data)
        if not repeat:
            data.remove(value)
            return self.normalize_string(value), data, 'data'
        return self.normalize_string(value)
    
    def chooseSeveral(self,data,repeat=True, minValue=0):
        data = data.copy()
        if isinstance(data, str):
            with open(data) as file:
                data = file.readlines()
        count = random.randint(minValue, len(data))
        resp = []
        for _ in range(count):
            value = random.choice(data)
            if not repeat:
                data.remove(value)
            resp.append(value)
        return resp

    def normalize_string(self, text: str):
        if not isinstance(text,str):
            return text
        text = text.replace('\n','')
        text = re.sub(r'\s+',' ',text)
        return text