import streamlit as st
from rdflib import Graph
from utils.SHACL import (
    display_classes_and_properties,
    ontology_manager,
    show_SHACL,
    display_constraints
)


# Set page configuration to collapse the sidebar by default, set the tab title, and add an icon
st.set_page_config(
    page_title="OM",  # Set the tab title to "OM"
    page_icon="🌐",  # Use a globe icon to represent ontology
    layout="wide"
)

def app():
    # Initialize session state variables
    if "file_list" not in st.session_state:
        st.session_state.file_list = []
    if "combined_graph" not in st.session_state:
        st.session_state.combined_graph = Graph()
    if "class_property_map" not in st.session_state:
        st.session_state.class_property_map = {}
    if "SHACL_content" not in st.session_state:
        st.session_state.SHACL_content = ""
    if "property_graph" not in st.session_state:
        st.session_state.property_graph = None


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
