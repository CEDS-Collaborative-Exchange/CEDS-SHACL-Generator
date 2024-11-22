import concurrent.futures
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from rdflib.plugins.stores.berkeleydb import logger

from models import OntlogyDefs
from service.identify_triplets import IdentifyTriplet
from settings import PROJECT_ROOT_DIR
from util import LogUtil


class TestIdentityTriplets(unittest.TestCase):
    # logging.basicConfig(level=logging.INFO)
    # logger = logging.getLogger(__name__)
    logger = LogUtil.create_logger(__name__)


    def check_dup_properties(self,json_val_arr):
        track_prop: Dict = {}
        for elem in json_val_arr:
            #elem:Dict = elem
            hash:Dict = elem

            if 'children' in hash:
                children: List = hash['children']
                for child in  children:
                    label = child['label']
                    if label in track_prop:
                        logger.debug('bad 1>>%s,2:%s,parent_label:%s,parent_val:%s',track_prop[label],child,elem['label'],elem['value'] )
                    else:
                        track_prop[label] = child

    def test_build_json_tree(self):
        test_clazz = IdentifyTriplet()
        #onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/small_ont.xml")
        onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/ontology.xml")
        json_val = test_clazz.build_json_tree(onto_file_path)
        self.check_dup_properties(json_val)
        # self.logger.debug('jsont val:%s',json.dumps(json_val))
        return


    def test_dup_build_json_tree(self):
        test_clazz = IdentifyTriplet()
        #onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/small_ont.xml")
        onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/duplicate-property.xml")
        ##json_val = test_clazz.build_json_tree(onto_file_path)
        json_dict_list = test_clazz.no_thread_build_json_tree(onto_file_path)
        self.check_dup_properties(json_dict_list)
        self.logger.debug('json-val:%s',json.dumps(json_dict_list))
        return

    def test_small_file_hierarchy(self):
        print("PROJECT_ROOT_DIR", PROJECT_ROOT_DIR)

        test_clazz = IdentifyTriplet()
        #onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/small_ont.xml")
        onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/ontology.xml")
        ont_uber_obj: OntlogyDefs.OntoLogyUberInfo = test_clazz.build_hierarchy(onto_file_path)
        self.logger.debug('Got ont_uber_obj in test')



    def test_do_threaded(self):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(pow, 323, 1235)
            print("result"+str(future.result()))
        return



if __name__ == '__main__':
    unittest.main()
