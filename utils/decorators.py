# import inspect

def preprocessingParamenters(func):

    def tryConvert(value, toType):
        types = getattr(toType,'__args__',None)
        if types:
            for t in types:
                try:
                    return tryConvert(value,t)
                except TypeError:
                    pass
        try:
            return toType(value)
        except:
            raise TypeError(f'Impossible to convert value {value} to {toType} in method {func.__name__}')
    
    def validValueType(value, Type):
        if value == None:
            return True
        types = getattr(Type,'__args__',None)
        if not types:
            return type(value) == Type
        return type(value) in types
    
    def newFunc(*args, **kwargs):
        args = list(args)
        self = args.pop(0)
        annotations: dict = func.__annotations__
        annotationsArgs = list(annotations.values())[0:len(args)]
        for (index, value), expectType in zip(enumerate(args),annotationsArgs):
            if not validValueType(value,expectType):
                newValue = tryConvert(value,expectType)
                args[index]=newValue
            if isinstance(args[index],list) or isinstance(args[index],dict):
                args[index] = args[index].copy()
        
        for key in kwargs:
            if key in annotations:
                if not validValueType(kwargs[key],annotations[key]):
                    newValue = tryConvert(kwargs[key],annotations[key])
                    kwargs[key] = newValue
                if isinstance(kwargs[key],list) or isinstance(kwargs[key],dict):
                    kwargs[key] = kwargs[key].copy()
            # else:
            #     raise TypeError(f'{func.__name__}() got an unexpected keyword argument {key}')
        return func(self,*args, **kwargs)

    return newFunc

def countCall(func):
    cache = {}
    def newFunc(*args, **kwargs):
        global count
        if 'count' in kwargs:
            kwargs.pop('count')
        key = make_key(args,kwargs)
        if key in cache:

            cache[key] +=1
            
        else:
            cache[key] = 0
        kwargs['count'] = cache[key]
        return func(*args,**kwargs)
    return newFunc

def make_key(args,kwargs):
    key = args
    if kwargs:
        for k in kwargs.items():
            key += k

    return _HashedSeq(key)

class _HashedSeq(list):
    """ This class guarantees that hash() will be called no more than once
        per element.  This is important because the lru_cache() will hash
        the key multiple times on a cache miss.
    """

    __slots__ = 'hashvalue'

    def __init__(self, tup, hash=hash):
        self[:] = tup
        self.hashvalue = hash(self.prepare(tup))
    
    def prepare(self,data):
        data = list(data)
        for i,v in enumerate(data):
            if isinstance(v,list):
                data[i] = self.prepare(v)
        return tuple(data)

    def __hash__(self):
        return self.hashvalue
