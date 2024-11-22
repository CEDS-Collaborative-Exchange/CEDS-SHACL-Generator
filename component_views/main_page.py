import os

import streamlit as st
from streamlit_tree_select import tree_select

from service.find_tripets import TripletFinder
from settings import PROJECT_ROOT_DIR
from util.LogUtil import create_logger

log = create_logger(__name__)


@st.cache_data
def load_onto_json_tree(file_name):
    log.debug("Inside load_onto_json_tree:%s", file_name)
    finder: TripletFinder = TripletFinder()
    json_resp = finder.get_onto_class_json_arr(file_name)
    return json_resp


onto_file_path = os.path.join(PROJECT_ROOT_DIR, "xml_files/ontology.xml")

nodes = load_onto_json_tree(onto_file_path)


def enter_app():

    with st.sidebar:
        if "return_select" not in st.session_state:
            log.info("return_select not in session_state")
            st.session_state.return_select = []

        tree_select(nodes,
                    no_cascade=True,
                    show_expand_all=False,
                    key="return_select",
                    expand_on_click=False,
                    )

    if "return_select" not in st.session_state:
        log.info("return_select not in session_state")
        st.session_state.return_select = []

    if 'return_select' in st.session_state:
        # st.session_state["selected_nodes"] = return_select
        selected_val = st.session_state.return_select
        log.info("return_select inside session_state")
        st.write("Selected Nodes:", selected_val)
