import streamlit as st
from pathlib import Path
from rdflib import Graph, RDFS, URIRef
from rdflib.namespace import RDF, SKOS, Namespace, SH  # Import SH namespace
from utils.SHACL import (
    namespaces,
    load_ontologies,
    display_classes_and_properties,
    generate_shacl,
)
from streamlit_ace import st_ace
import json

# Add Schema.org namespace
SDO = Namespace("https://schema.org/")

def generate_sample_jsonld(shacl_content):
    """Generate a sample JSON-LD document based on the SHACL shapes."""
    try:
        g = Graph()
        g.parse(data=shacl_content, format="turtle")

        sample_jsonld = {}
        for node_shape in g.subjects(RDF.type, SH.NodeShape):
            target_class = next(g.objects(node_shape, SH.targetClass), None)
            if target_class:
                class_name = str(target_class).split("/")[-1]
                sample_jsonld[class_name] = {}
                for prop_shape in g.objects(node_shape, SH.property):
                    path = next(g.objects(prop_shape, SH.path), None)
                    if path:
                        property_name = str(path).split("/")[-1]
                        sample_jsonld[class_name][property_name] = "Sample Value"

        return json.dumps(sample_jsonld, indent=4)
    except Exception as e:
        st.error(f"Failed to generate JSON-LD: {e}")
        return None

def ontology_manager():
    """Main page of the application."""
    # Apply custom CSS for layout adjustments
    st.markdown(
        """
        <style>
        /* Set the main container to span the full width */
        .stMainBlockContainer {
            max-width: 95% !important;
            padding-left: 10px !important;
            padding-right: 10px !important;
        }
        /* Adjust the layout for the three-column design */
        .stColumn {
            display: flex;
            justify-content: space-between;
            padding: 10px;
            gap: 10px;
            overflow-y: auto;
            max-height: 80vh; 
        }
        .stColumn:nth-child(1) {
            border-right: 1px solid #ddd;
        }
        .stColumn:nth-child(2) {
            border-right: 1px solid #ddd;
        }
        /* Target the Ace editor container */
        .st-emotion-cache-13o7eu2 {
            width: 100% !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Ontology Manager")

    # Create a three-column layout
    left_col, middle_col, right_col = st.columns([2, 4, 4], gap="small")

    # Left-hand column for file management
    with left_col:
        st.subheader("Manage Ontology Files")
        uploaded_files = st.file_uploader("Upload Ontology Files", type=["ttl", "rdf", "xml"], accept_multiple_files=True)
        namespace_data = []
        if uploaded_files:
            for file in uploaded_files:
                namespace_url = st.text_input(f"Namespace URL for {file.name}", "http://ceds.edu.gov/terms#")
                namespace_shortname = st.text_input(f"Namespace Shortname for {file.name}", "ceds")
                namespace_data.append((namespace_url, namespace_shortname))

        if st.button("Load Ontologies"):
            # Store the combined graph in session state
            st.session_state.combined_graph = load_ontologies(uploaded_files, namespace_data)

    # Middle column for displaying classes and properties
    with middle_col:
        st.subheader("Classes and Properties")
        # Only display classes if ontologies have been loaded
        if "combined_graph" in st.session_state and len(st.session_state.combined_graph) > 0:
            display_classes_and_properties()
        else:
            st.info("Please load ontologies to view classes and properties.")

    # Right-hand column for SHACL code editor and JSON-LD generator
    with right_col:
        st.subheader("SHACL Code Editor")
        shacl_content = None
        if st.button("Generate SHACL"):
            if "class_property_map" in st.session_state and st.session_state.class_property_map:
                shacl_content = generate_shacl()
                if shacl_content:
                    # Display the SHACL content in the Ace editor
                    st_ace(
                        value=shacl_content,
                        language="turtle",
                        theme="monokai",
                        readonly=True,
                        height=400,
                        key="st-ace-editor",  # Assign a consistent key to target the editor
                    )
            else:
                st.info("No SHACL content to display. Please select class-property mappings.")

        # JSON-LD Generator
        if shacl_content:
            sample_jsonld = generate_sample_jsonld(shacl_content)
            if sample_jsonld:
                st_ace(
                    value=sample_jsonld,
                    language="json",
                    theme="monokai",
                    readonly=True,
                    height=400,
                    key="st-jsonld-editor",  # Assign a consistent key to target the editor
                )
        else:
            st.info("Generate SHACL first to create a sample JSON-LD document.")

def app():
    """Streamlit multi-page application."""
    # Initialize session state variables
    if "class_property_map" not in st.session_state:
        st.session_state.class_property_map = {}
    if "combined_graph" not in st.session_state:
        st.session_state.combined_graph = Graph()
    if "SHACL_content" not in st.session_state:
        st.session_state.SHACL_content = ""

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Ontology Manager"])

    if page == "Ontology Manager":
        ontology_manager()

if __name__ == "__main__":
    app()
