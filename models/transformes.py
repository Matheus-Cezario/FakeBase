class transform:
    def __init__(self):
        self.methodsName =  [func for func in dir(self) if callable(getattr(self, func)) and not func.startswith("__")]
    
    def call_function(self, method: str,value, **kwargs) -> str:
        if method not in self.methodsName:
            return value
            # raise Exception(f'Method {method} not found')
        return self[method](value,**kwargs)
    
    def __getitem__(self, key):
        return getattr(self,key)

class moneyPipe(transform):
    def __init__(self):
        super().__init__()
    
    def currency(self, value,**kwargs):
        if isinstance(value,tuple):
            return 'R$ ' + str(value[0]), value[1],value[2]
        return 'R$ ' + str(value)