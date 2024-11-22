import json
from typing import Dict, List

from rdflib import Graph, URIRef, RDFS, RDF, SDO

from models.OntlogyDefs import OntoClass, OntoProperty
from settings import PROJECT_ROOT_DIR
from util.LogUtil import create_logger

rdfs_domain_includes_uri = URIRef("http://www.w3.org/2000/01/rdf-schema#domainIncludes")
rdfs_range_includes_uri = URIRef("http://www.w3.org/2000/01/rdf-schema#rangeIncludes")
class TripletFinder:
    def __init__(self):
        self.log = create_logger(__name__)

    def find_label_for_subject(self, graph: Graph, subject: URIRef) -> str:
        for s, p, o in graph.triples((subject, RDFS.label, None)):
            #self.log.debug("\tFound subject and label:[%s],[%s]", s, o)
            return str(o)


    """
    for the property 
    sets the label, and data type  of property
    and returns OntProperty
    here range_include_type argument can be either SDO.rangeIncludes or  URIRef("http://www.w3.org/2000/01/rdf-schema#rangeIncludes")
    """
    def find_objects_for_property(self,graph:Graph,prop_s:URIRef,range_include_type:URIRef)->OntoProperty:

        ont_prop = OntoProperty()
        ont_prop.uri_ref = prop_s
        for s, p, o in graph.triples((prop_s, range_include_type, None)):
                ont_prop.dataTypeUriRef = o

        for s, p, o in graph.triples((prop_s, RDFS.label, None)):
                ont_prop.name = o

        if not ont_prop.name:
            ont_prop.name = ont_prop.uri_ref.fragment
        return ont_prop

    """
   For each class, finds its properties
    """
    def __find_prop_for_class__(self, ont_class:OntoClass, graph:Graph):
        """
        predicate:domainInclude
         (there are 2 types of domainIncludes rfds and schema )
         and object:this_class_uri , then the subject is the property
        """

        for prop_s, prop_p, prop_o in graph.triples((None, SDO.domainIncludes, ont_class.uri_ref)):
            self.log.debug("prop:found_domainIncludes:%s", prop_s)
            ont_class.add_property(self.find_objects_for_property(graph,prop_s,SDO.rangeIncludes))

        # If we cannot find property using SDO.domainIncludes will try rdfs_property
        for prop_s, prop_p, prop_o in graph.triples((None, rdfs_domain_includes_uri, ont_class.uri_ref)):
            self.log.debug("prop:found_rdfs_domain_includes_uri:%s", prop_s)
            ont_class.add_property(self.find_objects_for_property(graph,prop_s,rdfs_range_includes_uri))





    """
    Returns a List which has these Json tree as string
    each elements in json has {label,value,children:[{label,value,childre}]
    [
  {
    "label": "Record Status",
    "value": "{\"name\":\"Record Status\",\"uri_ref\":\"http://ceds.ed.gov/terms#RecordStatus\"}",
    "children": [
      {
        "label": "Has Organization",
        "value": "{\"name\":\"Has Organization\",\"prop_uri\":\"http://ceds.ed.gov/terms#hasOrganization\",\"class_uri\":\"http://ceds.ed.gov/terms#RecordStatus\",\"data_type\":\"http://ceds.ed.gov/terms#Organization\"}"
      },
      {
        "label": "Record Created By person",
        "value": "{\"name\":\"Record Created By person\",\"prop_uri\":\"http://ceds.ed.gov/terms#createdByPerson\",\"class_uri\":\"http://ceds.ed.gov/terms#RecordStatus\",\"data_type\":\"http://ceds.ed.gov/terms#Person\"}"
      },
      {
        "label": "Record Created By Organization",
        "value": "{\"name\":\"Record Created By Organization\",\"prop_uri\":\"http://ceds.ed.gov/terms#createdByOrganization\",\"class_uri\":\"http://ceds.ed.gov/terms#RecordStatus\",\"data_type\":\"http://ceds.ed.gov/terms#Organization\"}"
      },
      {
        "label": "hasRecordStatusHistory",
        "value": "{\"name\":\"hasRecordStatusHistory\",\"prop_uri\":\"http://ceds.ed.gov/terms#hasRecordStatusHistory\",\"class_uri\":\"http://ceds.ed.gov/terms#RecordStatus\",\"data_type\":\"http://ceds.ed.gov/terms#RecordStatusHistory\"}"
      }
    ]
  }
]

    """
    def get_onto_class_json_arr(self,file_name)-> List[str]:
        ont_class_dic: Dict[URIRef, OntoClass] = self.find_class(file_name)
        json_hold_arr = []
        for ont_clazz in ont_class_dic.values():
            json_hold_arr.append(ont_clazz.get_json())
        # json_response =     json.dumps(json_hold_arr)
        self.log.info("json_response%s", json_hold_arr)
        return json_hold_arr

    """
    This returns a Dictionary
    where key is the URIRef of the Class
    and the value is OntoClass
        Each Onto class has properties
    """
    def find_class(self, file_name:str) -> Dict[URIRef, OntoClass]:
        self.log.debug("Inside find_class file_name%s:",file_name)
        graph = Graph()
        graph.parse(location=file_name)
        ont_class_track: Dict[URIRef, OntoClass] = {}

        for clazz_s, clazz_p, clazz_o in graph.triples((None, RDF.type, RDFS.Class)):

            if type(clazz_s) is not URIRef:
                continue
            uri_ref: URIRef = clazz_s
            clazz:OntoClass = OntoClass()

            clazz.uri_ref = uri_ref
            clazz.name = self.find_label_for_subject(graph, clazz_s)

            ont_class_track.setdefault(uri_ref, clazz)

            self.__find_prop_for_class__(clazz,graph )

            self.log.debug("clazz:%s", clazz)

        print("length of class:%s", len(ont_class_track))
        return ont_class_track