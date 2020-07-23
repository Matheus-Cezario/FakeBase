import cherrypy
import os
import json


from controllers.dataBaseManager import DataBaseManager
from math import ceil
from utils.decorators import preprocessingParamenters

# print(cherrypy.request.method)
class Server(object):
    def __init__(self, dataBaseManager: DataBaseManager):
        super().__init__()
        self.dataBaseManager = dataBaseManager
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def index(self):  
        return {"dataBase":list(self.dataBaseManager.list_databases())}
    
    @cherrypy.expose(['get'])
    @cherrypy.tools.json_out()
    @cherrypy.popargs('key')
    def getItem(self,key=None,**kwargs):
        resp = self.dataBaseManager.getItem(key,**kwargs)
        if isinstance(resp,tuple):
            raise cherrypy.HTTPError(*resp)

        return resp

    @cherrypy.expose(['update'])
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.popargs('key')
    def updateItem(self,key:str,every:bool =False,**kwargs):
        newValue = cherrypy.request.json
        resp = self.dataBaseManager.updateItem(key,newValue,every,**kwargs)
        if isinstance(resp,tuple):
            raise cherrypy.HTTPError(*resp)
        return resp
    
    @cherrypy.expose(['set'])
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.popargs('key')
    @preprocessingParamenters
    def setItem(self,key:str,every:bool =False,**kwargs):
        newValue = cherrypy.request.json
        resp = self.dataBaseManager.setItem(key,newValue,every,**kwargs)
        if isinstance(resp,tuple):
            raise cherrypy.HTTPError(*resp)
        return resp

    @cherrypy.expose(['delete'])
    @cherrypy.tools.json_out()
    @cherrypy.popargs('key')
    @preprocessingParamenters
    def deleteItem(self,key:str,every:bool =False,**kwargs):
        resp = self.dataBaseManager.deleteItem(key,every,**kwargs)
        if isinstance(resp,tuple):
            raise cherrypy.HTTPError(*resp)

        return resp

    @cherrypy.expose(['list'])
    @cherrypy.tools.json_out()
    @cherrypy.popargs('key')
    @preprocessingParamenters
    def listBase(self, key:str =None,paginate:bool =False,pageCount:int =10,page:int =1,**kwargs):
        json_list = self.dataBaseManager.list_database(key,**kwargs)
        if isinstance(json_list,tuple):
            raise cherrypy.HTTPError(*json_list)
        info = {}
        count = len(json_list)
        if paginate:
            json_list = json_list[pageCount*(page-1):pageCount*page]
            info = {"pageCount": pageCount, "page": page, "totalPages": ceil(count/pageCount)}

        resp = {'value':json_list}
        return {**resp,**info, "totalItens":count}
    
                

def start_server(dataBaseManager: DataBaseManager):
    cherrypy.quickstart(Server(dataBaseManager))


