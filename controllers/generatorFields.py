from models.valuesGenerator import humanValuesGenerator, valuesGenerator, numberValuesGenerator, randomValuesGenerator
from controllers.pipes import Pipes
from models.enums import ReservedWords

class generatorFields:

    def __init__(self):
        super().__init__()
        self.humanValues = humanValuesGenerator()
        self.numberValues = numberValuesGenerator()
        self.randomValues = randomValuesGenerator()
        self.pipes = Pipes()
        self.initializer_variables()

    def get_size_restriction(self,method: str):
        if method not in self.methodsMap.keys():
            return None
        variableName = self.methodsMap[method]
        variable: valuesGenerator = self[variableName]
        return variable.size_restriction

    def initializer_variables(self):
        variables = self.__dict__
        methodsMap = {}
        for key, value in zip(variables.keys(), variables.values()):
            if(isinstance(value, valuesGenerator)):
                methodsName: list = value.methodsName
                mapValues = {method: key for method in methodsName}
                methodsMap.update(mapValues)
        self.methodsMap = methodsMap

    def generate(self, method, **kwargs):
        # assert method in self.methodsMap.keys(), f'Method {method} not exist'
        if not isinstance(method,str):
            return method
        if method not in self.methodsMap.keys():
            return method
        transformMethod = None
        if ReservedWords.TRANSFORM.value in kwargs:
            transformMethod = kwargs.pop(ReservedWords.TRANSFORM.value)
            
        variableName = self.methodsMap[method]
        variable: valuesGenerator = self[variableName]
        result = variable.call_function(method, **kwargs)
        if transformMethod:
            if isinstance(transformMethod, str):
                transform = {'method':transformMethod, 'value': result}
            else:
                transform = {**transformMethod, 'value': result}
            result = self.pipes.transform(**transform)
        return result

    def __getitem__(self, key):
        return getattr(self, key)
