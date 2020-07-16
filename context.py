from customTypes import Schemas, DataBase
from models.enums import ReservedWords
class Context:
    
    def __init__(self, path, router, fakeBasePath):
        self.path = path
        self.router = router
        self.fakeBasePath = fakeBasePath
        self.jsonConfig = {}

    @property
    def schemas(self) -> Schemas:
        return self.jsonConfig[ReservedWords.SCHEMATICS.value]
    
    @property
    def dataBase(self) -> DataBase:
        return self.jsonConfig[ReservedWords.DATABASE.value]