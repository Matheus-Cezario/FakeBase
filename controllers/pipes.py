from models.transformes import moneyPipe, transform
class Pipes:
    def __init__(self):
        self.money = moneyPipe()
        self.initializer_variables()
    
    def initializer_variables(self):
        variables = self.__dict__
        methodsMap = {}
        for key, value in zip(variables.keys(),variables.values()):
            if(isinstance(value, transform)):
                methodsName: list = value.methodsName
                mapValues = {method:key for method in methodsName}
                methodsMap.update(mapValues)
        self.methodsMap = methodsMap
    def transform(self, method,value, **kwargs):
        if method not in self.methodsMap.keys():
            return value
        variableName = self.methodsMap[method]
        variable: transform = self[variableName]
        return variable.call_function(method,value,**kwargs)
    
    def __getitem__(self, key):
        return getattr(self,key)