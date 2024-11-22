import typing
import unittest

from rdflib import URIRef

from models.OntlogyDefs import OntoClass
from util.Helper import to_json


class TestHelper(unittest.TestCase):
    def test_to_json(self):

        onto_list:typing.List[OntoClass] = []
        for x in range(6):
            ont_clazz = OntoClass()
            ont_clazz.name = str(x) + 'hello'
            ont_clazz.uri_ref = URIRef("http://hello.com")
            print("json:"+ont_clazz.get_json())





if __name__ == '__main__':
    unittest.main()
