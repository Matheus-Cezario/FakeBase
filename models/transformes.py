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
    
    def currency(self, value,prefix="R$ ",brSeparator = True):
        if isinstance(value,tuple):
            return prefix + self.__prepareMoney(value[0],brSeparator), value[1],value[2]
        return prefix + self.__prepareMoney(value,brSeparator)
    
    def __prepareMoney(self,money,brSeparator):
        money = '{:,.2f}'.format(money)
        if brSeparator:
            main, frac = money.split('.')
            main = main.replace(',','.')
            money = main + ','+ frac
        return money