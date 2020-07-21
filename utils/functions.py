import re
def find(func,iterabel):
    for item in iterabel:
        if func(item):
            return item

    return None

def str_schema_replace(str_schema,variable,dependency):
    str_schema = str_schema.replace(variable,str(dependency))
    str_schema = str_schema.replace("'",'"')
    str_schema = str_schema.replace('False','false')
    str_schema = str_schema.replace('True','true')
    str_schema = str_schema.replace('None','null')
    str_schema = str_schema.replace('"[','[')
    str_schema = str_schema.replace(']"',']')
    str_schema = str_schema.replace('"{','{')
    str_schema = str_schema.replace('}"','}')

    return str_schema

def strToList(strValue: str):
    isList = re.compile(r'\[.*?\]')
    if isList.match(strValue):
        strValue = strValue.replace('[','').replace(']','')
        return strValue.split(',')
    return None