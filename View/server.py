import cherrypy
import os
import json

from context import Context
from math import ceil

# print(cherrypy.request.method)
class Server(object):
    def __init__(self, context: Context):
        super().__init__()
        self.context = context
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def index(self):  
        return {"dataBase":list(self.list_databases())}
    
    def list_databases(self):
        return self.context.dataBase.keys()
    
    @cherrypy.expose(['get'])
    @cherrypy.tools.json_out()
    @cherrypy.popargs('key')
    def getItem(self,key=None,**kwargs):
        if key not in self.list_databases():
            raise cherrypy.HTTPError(404,f'DataBase {key} not found.')
        path = os.path.join(self.context.fakeBasePath,key+'.json')
        with open(path) as file:
            json_file: dict = json.load(file)
            for value in json_file[key]:
                if self.contais_equals(value,kwargs):
                    return {"value":value}

        return {"value":None}
        

    @cherrypy.expose(['list'])
    @cherrypy.tools.json_out()
    @cherrypy.popargs('key')
    def listBase(self, key=None,paginate=False,pageCount=10,page=1,**kwargs):
        pageCount = int(pageCount)
        page = int(page)
        if key not in self.list_databases():
            raise cherrypy.HTTPError(404,f'DataBase {key} not found.')
        path = os.path.join(self.context.fakeBasePath,key+'.json')
        with open(path) as file:
            json_file: dict = json.load(file)
            json_list = []
            for value in json_file[key]:
                if self.contais_equals(value,kwargs):
                    json_list.append(value)
        info = {}
        count = len(json_list)
        if paginate:
            json_list = json_list[pageCount*(page-1):pageCount*page]
            info = {"pageCount": pageCount, "page": page, "totalPages": ceil(count/pageCount)}

        resp = {key:json_list}
        return {**resp,**info, "totalItens":count}
    
    def contais_equals(self,el: dict,condition: dict):
        if len(condition.items()) == 0:
            return True
        for key in condition.keys():
            if key in el and el[key] != condition[key]:
                return False
        return True
                

def start_server(context: Context):
    cherrypy.quickstart(Server(context))


