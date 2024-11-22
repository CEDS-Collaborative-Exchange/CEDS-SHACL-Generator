from enum import Enum
from typing import List, Dict, Set

from rdflib import URIRef

from util.Helper import to_string


# class_schema_identifier:str = "http://www.w3.org/2000/01/rdf-schema#Class"
# rdf_syntax_ns_identifier:str = "http://www.w3.org/1999/02/22-rdf-syntax-ns"
# __all__ = ["OntoType","OntoProperty","OntoClass"]
# typeUri = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns")
# classUri = URIRef("http://www.w3.org/2000/01/rdf-schema#Class")
# propUriLst = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#Property")


class OntoRdfTypes(Enum):
    PROPERTY = "Property"
    CLASS = "Class"
    DOMAIN_INCLUDE = "domainIncludes"
    RANGE_INCLUDES = "rangeIncludes"
    TYPE = "type"



class OntoDataType(Enum):
    STRING = 1
    DATE = 2
    NUMBER = 3

# Custom serialization function
def custom_serializer(obj):
    if hasattr(obj, "__dict__"):
        return getattr(obj,"__dict__")
    else:
        raise TypeError(f"Type {type(obj)} not serializable")

# class TreeJson:
#     def __init__(self):
#         pass
#     label:str = None
#     value:str = None
#     children = [] = None

class OntoLogyUberInfo:
    def __init__(self):
        self.class_track:Dict[str,OntoClass] = {}
        """
        holds type OntoProperty with key of string
        """
        self.property_track: Dict[str,OntoProperty] = {}

        self.domain_includes_set: Set[DomainIncludes] = set()
        self.range_includes_set: Set[RangeIncludes] = set()

class OntoProperty:

    def __init__(self):
        self.name: str = None
        # ontDataType:OntoDataType

        # this the class where this property belongs to
        self.domainClassUriRef: URIRef = None
        self.dataTypeUriRef: URIRef = None
        self.uri_ref: URIRef = None



    def __str__(self):
        #return f"OntoProperty:{to_string(self)}"
        return f"OntoProperty:{vars(self)}"

    def __hash__(self):
        return hash( (self.name,self.domainClassUriRef,self.dataTypeUriRef,self.uri_ref))

    def __eq__(self, other):
        if isinstance(other, OntoProperty):
            return self.name == other.name and self.domainClassUriRef == other.domainClassUriRef and self.dataTypeUriRef == other.dataTypeUriRef and self.uri_ref == other.uri_ref


class OntoClass:


    def __init__(self):
        self.name: str = None
        self.onto_properties: List[OntoProperty] = []
        self.uri_ref: URIRef = None


    def __str__(self):
        #return f"OntoProperty:{to_string(self)}"
        return f"OntoClass:{vars(self)}"

    def __hash__(self):
        return hash( (self.name,self.uri_ref))

    def __eq__(self, other):
        if isinstance(other, OntoClass):
            return self.name == other.name and self.uri_ref == other.uri_ref

    """
    Adds the OntoProperty as children of this class in onto_properties
    """
    def add_property(self,ont_property:OntoProperty):
        if self.onto_properties is None:
            self.onto_properties = []
        #ont_property.domainClassUriRef = self.uri_ref
        self.onto_properties.append(ont_property)

    def get_json(self) -> dict:
        json_dict = {
            "label": self.name,
            #"value": self.uri_ref
            "value": f'{{"name":"{self.name}","uri_ref":"{self.uri_ref}"}}'
        }
        if len(self.onto_properties) > 0:
            children_prop_dict = []
            for prop in self.onto_properties:
                children_prop_dict.append({
                    "label" : prop.name,

                    "value" : f'{{"name":"{prop.name}","prop_uri":"{prop.uri_ref}","class_uri":"{self.uri_ref}","data_type":"{prop.dataTypeUriRef}"}}'
                })
            if len(children_prop_dict) > 0:
                json_dict['children'] = children_prop_dict

        return json_dict

class DomainIncludes:
    def __init__(self):
        """
        The actual property itself
        """
        self.property: URIRef = None

        """
        The class where this property belongs to
        """
        self.destinationClass: URIRef = None

    def __hash__(self):
        return hash( (self.property,self.destinationClass))

    def __eq__(self, other):
        if isinstance(other, DomainIncludes):
            return self.property == other.property and self.destinationClass == other.destinationClass

class RangeIncludes:
    def __init__(self):
        """
        The range info where this property belongs to
        """
        self.property: URIRef = None

        """
        Data type for the property
        """
        self.dataType: URIRef = None

        def __hash__(self):
            return hash( (self.property,self.dataType))

        def __eq__(self, other):
            if isinstance(other, RangeIncludes):
                return self.property == other.property and self.dataType == other.dataType