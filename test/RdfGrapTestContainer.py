import json
import os
import unittest
from os.path import join
from typing import Dict

from rdflib import Graph, RDF, Dataset, SDO, URIRef

from models.OntlogyDefs import OntoClass
from service.find_tripets import TripletFinder
from settings import PROJECT_ROOT_DIR
from util import LogUtil

#onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/duplicate-property.xml")
onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/ontology.xml")

class RdfGrapLearnTest(unittest.TestCase):
    log = LogUtil.create_logger(__name__)

    finder:TripletFinder = TripletFinder()

    def test_graph_loop(self):
        g = Graph()
        # onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/duplicate-property.xml")
        g.parse(location=onto_file_path)
        #
        for s, p, o in g:
            print((s,p,o))
        print("now doing match triples class ")


    def test_find_class(self):

        ont_class_track:Dict[URIRef,OntoClass] = self.finder.find_class(join(PROJECT_ROOT_DIR, "xml_files/duplicate-property.xml"))


    def test_get_onto_class_json_arr(self):
        #file_name = join(PROJECT_ROOT_DIR, "xml_files/duplicate-property.xml")
        #file_name = join(PROJECT_ROOT_DIR, "xml_files/small_ont.xml")
        #file_name = join(PROJECT_ROOT_DIR, "xml_files/ontology.xml")
        file_name = join(PROJECT_ROOT_DIR, "xml_files/bad_value.xml")
        json_arr = self.finder.get_onto_class_json_arr(file_name)
        json_dump = json.dumps(json_arr)
        self.log.debug("json_dump:%s",json_dump)

    def test_query_graph(self):
        g = Graph()
        # onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/duplicate-property.xml")
        g.parse(location=onto_file_path)


        class_map:Dict[URIRef,OntoClass] = {}
        # match of predicate(type) object(Class)
        # for s,p,o in g.triples((None,RDF.type,RDFS.Class)):
        #     print ("class items:%s",(s,p,o))
        #     onto_class = OntoClass()
        #     class_uri_ref:URIRef =  s
        #     onto_class.uri_ref = s
        #     onto_class.name = class_uri_ref.fragment
        #     class_map.setdefault(class_uri_ref,onto_class)


        """
        find predicate(domainIncludes) 
            this will give subject as property_uri_ref
            and this will give object an class_uri_ref, means which class  the property belongs to
        
            find the predicate(rangeIncludes) for subject  property uri 
                this will give the the data type , either the class 
                
        create OntoProperty object from property uri
        look up 
        """
        cnt = 0
        #rdfs domainIncludes
        #http://www.w3.org/2000/01/rdf-schema#domainIncludes
        rdfs_domain_includes_uri = URIRef("http://www.w3.org/2000/01/rdf-schema#domainIncludes")
        rdfs_range_includes_uri = URIRef("http://www.w3.org/2000/01/rdf-schema#rangeIncludes")
        rdfs_property = URIRef("http://www.w3.org/2000/01/rdf-schema#Property")
        # for ds,dp,do in g.triples((None,rdfs_domain_includes_uri,None)):
        #     prop_uri:URIRef = ds
        #     class_uri:URIRef = do
        #     cnt +=1
        #     print("prop_uri and class_uri: %s,%s",prop_uri,class_uri)
        #     for rs,rp,ro in g.triples((prop_uri,rdfs_range_includes_uri,class_uri)):
        #         print("\t\trangeIncludes:%s",(rs,rp,ro))
        #
        prop_set = set()
        # match of predicate(type) object(Property)
        for s, p, o in g.triples((None, RDF.type,rdfs_property)):
            print("rdfs_property:%s",(s, p, o))

            for ss,sp,so in g.triples((s,SDO.domainIncludes,None)):
                print("\tpropAsSubject%s:",(sp,so))

            #prop_set.add(s)

            # Each property belongs to a class
            # This is matched by predicate domainIncludes
            # for s, p, o in g.triples((s, SDO.domainIncludes, None)):
            #     print("\tschema-domain:%s", (s, p, o))
            #
            # # Each property has a data type
            # # This is matched by predicate rangeIncludes
            # for s, p, o in g.triples((s, SDO.rangeIncludes, None)):
            #     print("\tschema-range:%s", (s, p, o))





    def test_load_dataset(self):
        g = Dataset()
        # onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/duplicate-property.xml")
        g.parse(location=onto_file_path)
        for s, p, o, g in g.quads((None, RDF.type, None, None)):
            print(s, g)



if __name__ == '__main__':
    unittest.main()
