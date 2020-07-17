# import inspect

def preprocessingParamenters(func):

    def tryConvert(value, toType):
        try:
            return toType(value)
        except:
            raise TypeError(f'Impossible to convert value {value} to {toType} in method {func.__name__}')
    
    def newFunc(*args, **kwargs):
        args = list(args)
        self = args.pop(0)
        annotations: dict = func.__annotations__
        annotationsArgs = list(annotations.values())[0:len(args)]
        for (index, value), expectType in zip(enumerate(args),annotationsArgs):
            if not (type(value) == expectType) and value != None:
                newValue = tryConvert(value,expectType)
                args[index]=newValue
        
        for key in kwargs:
            if key in annotations:
                if not (type(kwargs[key]) == annotations[key]) and kwargs[key] != None:
                    newValue = tryConvert(kwargs[key],annotations[key])
                    kwargs[key] = newValue
            else:
                raise TypeError(f'{func.__name__}() got an unexpected keyword argument {key}')
        return func(self,*args, **kwargs)

    return newFunc

