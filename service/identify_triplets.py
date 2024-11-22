import concurrent
import logging
from typing import List, Dict

from rdflib import Graph, URIRef

from models import OntlogyDefs
from models.OntlogyDefs import OntoClass, OntoRdfTypes, DomainIncludes, RangeIncludes
from service.build_ontology_tree import BuildTree
from util import LogUtil
import concurrent.futures
import json

from util.Helper import logger


# from build_ontology_tree import BuildTree



class IdentifyTriplet:
    # logging.basicConfig(level=logging.INFO)
    # logger = logging.getLogger(__name__)
    logger = LogUtil.create_logger(__name__)
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.__ontology_uber_info__ = OntlogyDefs.OntoLogyUberInfo()

    def __printMatch__(self, s, p, o):
        self.logger.info("subject>%s,pred>%s,object>%s", s, p, o)


    def build_hierarchy(self,onto_file_path:str) -> OntlogyDefs.OntoLogyUberInfo:
        self.logger.debug('Inside build_hierarchy')
        self.logger.info("onto_file_path:%s", onto_file_path)
        g = Graph()
        g.parse(location=onto_file_path)
        self.logger.debug('Done parsing graph')
        cnt: int = 0

        self.logger.debug('now starting to loop graph')
        for s, p, o in g:
            cnt += 1

            self.logger.debug('graph>>subject:%s,predicate:%s,object:%s',s,p,o)

            onto_prop = self.__find_property__(s, p, o)
            if onto_prop is not None:
                # logger.info("onto_prop.uri_ref defrag:%s", onto_prop.uri_ref.defrag())
                self.__ontology_uber_info__.property_track[onto_prop.uri_ref] = onto_prop
                #self.__printMatch__(s, p, o)
                # logger.info("subject>%s,pred>%s,object>%s", s, p, o)
                continue

            onto_class = self.__find_class__(s, p, o)
            if onto_class is not None:
                self.logger.debug("onto_class.uri_ref __find_class__:%s",onto_class.uri_ref.defrag())
                self.__ontology_uber_info__.class_track[onto_class.uri_ref] = onto_class
                #self.__printMatch__(s, p, o)
                # logger.info("subject>%s,pred>%s,object>%s", s, p, o)
                continue

            if self.__find_domain_include__(s, p, o) is not None:
                continue

            if self.__find_range__(s, p, o) is not None:
                continue

        # self.logger.info("final class_track::%s", self.__ontology_uber_info__.class_track)
        self.logger.info("final prop_track::%s", str(self.__ontology_uber_info__.property_track))
        # self.logger.info("final domain_includes_list::%s", self.__ontology_uber_info__.domain_includes_lst)
        # self.logger.info("final range_includes_lst::%s", self.__ontology_uber_info__.range_includes_lst)
        self.logger.debug('Now will call BuildTree')
        BuildTree(self.__ontology_uber_info__)
        self.logger.debug('Returning __ontology_uber_info__')
        return self.__ontology_uber_info__

    def no_thread_build_json_tree(self, onto_file_path: str) -> List[Dict]:
        self.logger.debug('Inside build_json_tree onto_file_path%s', onto_file_path)
        ont_uber_obj: OntlogyDefs.OntoLogyUberInfo = self.build_hierarchy(onto_file_path)
        json_onto_class_list = []
        for key in ont_uber_obj.class_track.keys():
            clazz_onto = ont_uber_obj.class_track.get(key)
            json_onto_class_list.append(clazz_onto.get_json())

        return json_onto_class_list

    def build_json_tree(self,onto_file_path:str)->List[Dict]:
        self.logger.debug('Inside build_json_tree onto_file_path%s',onto_file_path)
        ont_uber_obj:OntlogyDefs.OntoLogyUberInfo = self.build_hierarchy(onto_file_path)
        len_of_class = len(ont_uber_obj.class_track.keys())
        self.logger.debug('len_of_class %s', len_of_class)
        threadNum:int = 1 if len_of_class <=5  else int(len_of_class / 5)

        self.logger.debug('threadNum %s', threadNum)
        json_onto_class_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=threadNum ) as executor:

            future_dict = {}
            for key in ont_uber_obj.class_track.keys():
                clazz_onto = ont_uber_obj.class_track.get(key)
                # self.logger.debug('Building json for clazz%s',key)
                if clazz_onto is not None:
                    future = executor.submit(clazz_onto.get_json)
                    future_dict.setdefault(future,key)

            for future in concurrent.futures.as_completed(future_dict):
                key = future_dict[future]
                try:
                    data = future.result()
                    # self.logger.debug('data for key%s,is:%s',data,key)
                    json_onto_class_list.append(data)
                except Exception as exc:
                    print('%r generated an exception: %s' % (key, exc))

        self.logger.debug('Done build json tree , json_onto_class_list size:%s',len(json_onto_class_list))
        return json_onto_class_list

    """
    For eg. from this http://ceds.ed.gov/terms#createdByOrganization
    returns createdByOrganization
    """


    def __name_of_uri__(self, fragment: str):
        spltVal: List[str] = fragment.split("#")
        if spltVal != None and len(spltVal) > 0:
            return spltVal[len(spltVal) - 1]
        return None


    def __find_class__(self, subject, predicate, obj) -> OntoClass:
        if type(obj) !=  URIRef:
            return None

        uri_ref: URIRef = obj
        if not uri_ref.fragment.endswith(OntoRdfTypes.CLASS.value):
            return None

        #self.logger.info("ref class:%s", uri_ref.fragment)
        if type(subject) == URIRef:
            subject_ref: URIRef = subject
            class_name = self.__name_of_uri__(subject_ref.fragment)
            onto_class: OntoClass = OntoClass()
            onto_class.name = class_name
            onto_class.uri_ref = subject_ref
            self.logger.debug('found class %s',class_name)
            return onto_class


    def __find_property__(self, subject, predicate, obj) -> OntlogyDefs.OntoProperty:
        if type(obj) != URIRef:
            return None

        uri_ref: URIRef = obj
        if not uri_ref.fragment.endswith(OntoRdfTypes.PROPERTY.value):
            return None

        #self.logger.info("ref frag:%s", uri_ref.fragment)

        predicate_uri_ref: URIRef = predicate
        if not predicate_uri_ref.endswith(OntoRdfTypes.TYPE.value):
            return None

        subject_uri_ref: URIRef = subject
        ont_prop = OntlogyDefs.OntoProperty()
        ont_prop.name = subject_uri_ref.fragment
        ont_prop.uri_ref = subject_uri_ref
        return ont_prop



    """
    Find which property the class belongs to
    subject is the property
    predicate is domainInclude
    object is the class
    """


    def __find_domain_include__(self, subject, predicate, obj) -> DomainIncludes:
        #predicate is domainIncludes
        if type(predicate) != URIRef:
            return None

        predicate_uri_ref: URIRef = predicate

        if not predicate_uri_ref.endswith(OntoRdfTypes.DOMAIN_INCLUDE.value):
            return None

        # find  the property
        if type(subject) != URIRef:
            return None
        subject_uri_ref: URIRef = subject

        # This is the Class where the property belongs to
        if type(obj) != URIRef:
            return None
        obj_uri_ref: URIRef = obj
        #self.logger.info("now looking class uri ref:%s", obj_uri_ref)
        domain_includes = DomainIncludes()
        domain_includes.property = subject_uri_ref
        domain_includes.destinationClass = obj_uri_ref
        self.__ontology_uber_info__.domain_includes_set.add(domain_includes)

        return domain_includes


    """
    Finds the data type of a property
    """


    def __find_range__(self, subject, predicate, obj) -> RangeIncludes:
        if type(predicate) is not URIRef:
            return None

        # Check if the predicate is rangeIncludes
        predicate_uri_ref: URIRef = predicate
        if not predicate_uri_ref.endswith(OntoRdfTypes.RANGE_INCLUDES.value):
            return None

        # find the property itself
        if type(subject) is not URIRef:
            return None
        prop_uri_ref: URIRef = subject

        # find the data type itself
        if type(obj) is not URIRef:
            return None
        data_type_ref: URIRef = obj

        range_includes = RangeIncludes()
        range_includes.property = prop_uri_ref
        range_includes.dataType = data_type_ref
        self.__ontology_uber_info__.range_includes_set.add(range_includes)
        return range_includes


# if __name__ == "__main__":
#     current_directory = os.getcwd()
#     onto_file_path = os.path.join(current_directory, "xml_files/small_ont.xml")
#     trip = IdentifyTriplet()
#     # trip.build_hierarchy(onto_file_path)
#     big_file = "/Users/ashakya/ceds/ptest/xml_files/ontology.xml"
#     trip.build_hierarchy(big_file)

