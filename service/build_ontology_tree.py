from venv import logger

from models.OntlogyDefs import OntoProperty, OntoClass, OntoLogyUberInfo
from util import LogUtil


class BuildTree:

    def __init__(self, onto_uber_info:OntoLogyUberInfo):
        self.logger = LogUtil.create_logger(__name__)
        self.logger.debug('Inside BuildTree init')
        self.ontoUberInfo = onto_uber_info
        self.__attach_data_type_to_property__()
        self.__attach_prop_to_class__()

        self.logger.debug('Done BuildTree init')
        #self.logger.info("class_track:%s",self.ontoUberInfo.class_track)


    def __attach_prop_to_class__(self):
        self.logger.debug('Inside __attach_data_type_to_property__')
        for dom in self.ontoUberInfo.domain_includes_set:
            prop: OntoProperty = self.ontoUberInfo.property_track.get(dom.property)
            if prop is None:
                continue

            clazz: OntoClass = self.ontoUberInfo.class_track.get(dom.destinationClass)

            if clazz is None:
                continue

            self.logger.debug("adding property:%s to clazz:%s",prop.uri_ref,clazz.uri_ref)
            # prop.domainClassUriRef = clazz.uri_ref

            clean_prop = OntoProperty()
            clean_prop.name = prop.name
            clean_prop.uri_ref = prop.uri_ref
            clean_prop.dataTypeUriRef = prop.dataTypeUriRef
            clean_prop.domainClassUriRef = clazz.uri_ref
            clazz.add_property(clean_prop)
            self.logger.debug('adding to class_uri:%s, prop:%s',clazz.uri_ref,clean_prop)


    def __attach_data_type_to_property__(self):
        self.logger.debug('Inside __attach_data_type_to_property__');
        for range_iter in self.ontoUberInfo.range_includes_set:
            if self.ontoUberInfo.property_track.get(range_iter.property) is None:
                continue
            ont_prop:OntoProperty = self.ontoUberInfo.property_track.get(range_iter.property)
            ont_prop.dataTypeUriRef = range_iter.dataType