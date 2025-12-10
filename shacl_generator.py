import streamlit as st
from rdflib import Graph
from utils.SHACL import (
    display_classes_and_properties,
    ontology_manager,
    show_SHACL,
    display_constraints
)


st.set_page_config(
    page_title="OM",
    page_icon="🌐",
    layout="wide"
)

def app():
    # Initialize session state
    if "file_list" not in st.session_state:
        st.session_state.file_list = []
    if "combined_graph_id" not in st.session_state:
        st.session_state.combined_graph_id = None
    if "class_property_map" not in st.session_state:
        st.session_state.class_property_map = {}
    if "SHACL_content" not in st.session_state:
        st.session_state.SHACL_content = ""
    if "property_graph_id" not in st.session_state:
        st.session_state.property_graph_id = None
    if "property_constraints" not in st.session_state:
        st.session_state.property_constraints = {}
    if "existing_shacl_id" not in st.session_state:
        st.session_state.existing_shacl_id = None


    page = st.sidebar.radio("Go to", ["Ontology Files", "Class and Property Menu", "Constraints", "SHACL"])

    if page == "Ontology Files":
        ontology_manager()
    elif page == "Class and Property Menu":
        display_classes_and_properties()
    elif page == "Constraints":
        display_constraints()
    elif page == "SHACL":   
        show_SHACL()


        
if __name__ == "__main__":
    app()
