import streamlit as st
from pathlib import Path
from rdflib import Graph, RDFS, URIRef
from utils.SHACL import namespaces, create_node_shape, create_property_shapes, serialize_graph
from rdflib.namespace import RDF, SKOS, Namespace
from streamlit_ace import st_ace

# Add Schema.org namespace
SDO = Namespace("https://schema.org/")

def get_rdf_format(file_name):
    """Determine the RDF format based on the file extension."""
    formats = {".ttl": "turtle", ".rdf": "xml", ".xml": "xml"}
    extension = Path(file_name).suffix.lower()
    return formats.get(extension, None)

def load_ontologies(uploaded_files, namespace_data):
    """Load all uploaded ontology files into the combined RDF graph."""
    combined_graph = Graph()
    for file, (namespace_url, namespace_shortname) in zip(uploaded_files, namespace_data):
        try:
            rdf_format = get_rdf_format(file.name)
            if not rdf_format:
                raise ValueError(f"Unsupported file format for {file.name}.")
            temp_graph = Graph()
            temp_graph.parse(data=file.read(), format=rdf_format)
            # Dynamically bind namespaces provided by the user
            namespaces[namespace_shortname] = Namespace(namespace_url)
            combined_graph.namespace_manager.bind(namespace_shortname, Namespace(namespace_url))  # Bind namespace
            combined_graph += temp_graph  # Merge the file's graph into the combined graph
            st.success(f"Ontology file '{file.name}' loaded successfully with namespace '{namespace_shortname}'.")
        except Exception as e:
            st.error(f"Failed to load ontology file '{file.name}': {e}")
    return combined_graph

def get_label(uri, graph):
    """Get the human-readable label for a URI."""
    label = next(graph.objects(URIRef(uri), RDFS.label), None)
    return str(label) if label else str(uri)

def get_properties_for_class(class_uri, graph):
    """Get properties associated with a class using domainIncludes."""
    properties = []
    for prop in graph.subjects(SDO.domainIncludes, URIRef(class_uri)):
        properties.append(prop)
    return properties

def display_classes_and_properties():
    """Display classes and their properties in a tree-like structure."""
    if "combined_graph" not in st.session_state or len(st.session_state.combined_graph) == 0:
        st.info("No ontology files loaded. Please upload files.")
        return

    # Initialize session state for class-property mappings
    if "class_property_map" not in st.session_state:
        st.session_state.class_property_map = {}

    # Get all classes in the combined graph and sort them alphabetically by label
    classes = list(st.session_state.combined_graph.subjects(RDF.type, RDFS.Class))
    sorted_classes = sorted(classes, key=lambda class_uri: get_label(class_uri, st.session_state.combined_graph).lower())

    for class_uri in sorted_classes:
        class_label = get_label(class_uri, st.session_state.combined_graph)
        properties = get_properties_for_class(class_uri, st.session_state.combined_graph)

        with st.expander(f"Class: {class_label}"):
            # Determine if all properties are selected for this class
            all_selected = all(
                prop in st.session_state.class_property_map.get(class_uri, set())
                for prop in properties
            )

            # Class-level checkbox to select/deselect all properties
            select_all_key = f"select_all_{class_uri}"
            select_all = st.checkbox(f"Select All Properties", value=all_selected, key=select_all_key)

            # Update property selection based on the class-level checkbox
            if select_all:
                st.session_state.class_property_map[class_uri] = set(properties)
            else:
                st.session_state.class_property_map[class_uri] = set()

            # Individual property checkboxes
            for prop in properties:
                prop_label = get_label(prop, st.session_state.combined_graph)
                key = f"{class_uri}:{prop}"
                is_checked = prop in st.session_state.class_property_map.get(class_uri, set())
                if st.checkbox(f"{prop_label}", key=key, value=is_checked):
                    st.session_state.class_property_map.setdefault(class_uri, set()).add(prop)
                else:
                    st.session_state.class_property_map.get(class_uri, set()).discard(prop)

            # Remove the class from the map if no properties are selected
            if not st.session_state.class_property_map[class_uri]:
                del st.session_state.class_property_map[class_uri]

def update_class_property_map(class_uri, prop, key):
    """Update the class-property mappings in session state."""
    if st.session_state[key]:
        st.session_state.class_property_map.setdefault(str(class_uri), set()).add(str(prop))
    else:
        st.session_state.class_property_map.get(str(class_uri), set()).discard(str(prop))

def generate_shacl():
    """Generate SHACL shapes from the selected class-property mappings."""
    if not st.session_state.class_property_map:
        st.warning("No class-property mappings selected.")
        return None

    g1 = Graph()
    # Dynamically bind all namespaces from the `namespaces` dictionary
    for prefix, namespace in namespaces.items():
        g1.namespace_manager.bind(prefix, namespace)  # Bind namespaces to the SHACL graph

    shacl_namespace = namespaces.get("ceds", Namespace("http://ceds.ed.gov/terms#"))  # Default to CEDS namespace
    for class_uri, properties in st.session_state.class_property_map.items():
        if properties:  # Only include classes with properties
            create_node_shape(g1, st.session_state.combined_graph, class_uri, {}, shacl_namespace)
            create_property_shapes(g1, st.session_state.combined_graph, class_uri, properties, st.session_state.class_property_map, shacl_namespace)

    # Serialize the SHACL graph to a string
    try:
        shacl_content = g1.serialize(format="turtle")
        st.success("SHACL shapes generated successfully!")
        return shacl_content
    except Exception as e:
        st.error(f"Failed to generate SHACL: {e}")
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
                namespace_url = st.text_input(f"Namespace URL for {file.name}", "http://example.org/")
                namespace_shortname = st.text_input(f"Namespace Shortname for {file.name}", "example")
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

    # Right-hand column for SHACL code editor
    with right_col:
        st.subheader("SHACL Code Editor")
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
                        height=800,
                        key="st-ace-editor",  # Assign a consistent key to target the editor
                    )
            else:
                st.info("No SHACL content to display. Please select class-property mappings.")

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
