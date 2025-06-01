from rdflib import Graph, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, SH, XSD, SDO, SKOS
from rdflib.collection import Collection
import logging
import csv
from pathlib import Path
from io import BytesIO
from utils.common import add_namespace, get_rdf_format, get_label, get_properties_for_class
import streamlit as st

logger = logging.getLogger(__name__)

namespaces = {}

def get_namespace(prefix, namespaces):
    return namespaces.get(prefix, Namespace(f"http://unknown.org/{prefix}#"))

def get_filter_class_ids_from_file(file_obj):
    """Parse the filter file to extract class-property mappings."""
    class_property_map = {}
    try:
        # Check if the input is a BytesIO object
        if isinstance(file_obj, BytesIO):
            file_obj.seek(0)  # Ensure the BytesIO object is at the beginning
            reader = csv.reader(file_obj.read().decode("utf-8").splitlines())
        else:
            # Assume it's a file path
            with open(file_obj, "r", newline="") as f:
                reader = csv.reader(f)

        for row in reader:
            if len(row) == 2:
                class_id_raw, property_id_raw = row[0].strip(), row[1].strip()
                class_prefix, class_id = class_id_raw.split(":") if ":" in class_id_raw else ("CEDS", class_id_raw)
                property_prefix, property_id = property_id_raw.split(":") if ":" in property_id_raw else ("CEDS", property_id_raw)
                class_ns = namespaces.get(class_prefix, Namespace(f"http://unknown.org/{class_prefix}#"))
                property_ns = namespaces.get(property_prefix, Namespace(f"http://unknown.org/{property_prefix}#"))
                class_uri = f"{class_ns}{class_id}"
                property_uri = f"{property_ns}{property_id}"
                if class_uri not in class_property_map:
                    class_property_map[class_uri] = set()
                class_property_map[class_uri].add(property_uri)
        logger.info("Class Property map: %s", class_property_map)
        return class_property_map
    except Exception as e:
        logger.exception(f"Failed to read filter file: {e}")
        return {}

def serialize_graph(g, g1, output_file="Filtered_SHACL.ttl"):
    """Serialize the SHACL graph to a file."""
    output_path = Path(output_file)
    try:
        output_path.write_text(g1.serialize(format="turtle"))
        logger.info(f"Serialized SHACL graph to {output_path}")
    except Exception as e:
        logger.exception(f"Failed to serialize SHACL graph: {e}")

def get_parent_classes(g, class_property_map):
    parent_classes = {}
    for class_uri in class_property_map.keys():
        for parent in g.objects(URIRef(class_uri), RDFS.subClassOf):  
            parent_classes[class_uri] = parent  
    return parent_classes

def create_node_shape(g1, g, class_uri, parent_classes, shacl_namespace):
    """Create a SHACL node shape for a given class."""
    notation = next(g.objects(URIRef(class_uri), SKOS.notation), None)
    if not notation:
        logger.warning(f"No skos:notation found for class URI: {class_uri}")
        return

    # Use the SHACL namespace to create the node shape URI
    node_title = URIRef(f"{shacl_namespace}{notation}Shape")
    g1.add((node_title, RDF.type, SH.NodeShape))

    # Ensure the targetClass uses the bound namespace
    class_namespace = namespaces.get(class_uri.split("#")[0], None)
    if class_namespace:
        target_class = URIRef(f"{class_namespace}{class_uri.split('#')[-1]}")
        g1.add((node_title, SH.targetClass, target_class))
    else:
        g1.add((node_title, SH.targetClass, URIRef(class_uri)))  # Fallback to full URI if namespace is not found

    if class_uri in parent_classes:
        g1.add((node_title, SH.closed, Literal(True, datatype=XSD.boolean)))

    ignored_props_list = [RDF.type, URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#id"), RDF.value, RDFS.label]
    ignored_list_node = BNode()
    Collection(g1, ignored_list_node, ignored_props_list)

    g1.add((node_title, SH.ignoredProperties, ignored_list_node))

def create_property_shapes(g1, g, class_uri, property_uris, class_property_map, shacl_namespace):
    """Create SHACL property shapes for a given class and its properties."""
    class_notation = next(g.objects(URIRef(class_uri), SKOS.notation), None)
    if not class_notation:
        logger.warning(f"No skos:notation found for class URI: {class_uri}")
        return

    class_node_title = URIRef(f"{shacl_namespace}{class_notation}Shape")

    for prop_uri in property_uris:
        ranges = list(g.objects(URIRef(prop_uri), SDO.rangeIncludes))
        prop_notation = next(g.objects(URIRef(prop_uri), SKOS.notation), None)

        if not prop_notation:
            logger.warning(f"No skos:notation found for property URI: {prop_uri}")
            continue

        # Use the SHACL namespace to create the property shape URI
        prop_shape = URIRef(f"{shacl_namespace}{prop_notation}Shape")

        # Add the property shape to the class node shape
        g1.add((class_node_title, SH.property, prop_shape))

        # Check if the range is a class and not a datatype
        for range_uri in ranges:
            if "#C" in str(range_uri):  # Example condition for identifying classes
                g1.add((prop_shape, RDF.type, SH.PropertyShape))
                g1.add((prop_shape, SH.path, URIRef(prop_uri)))  # Ensure the path uses the bound namespace
                g1.add((prop_shape, SH["class"], URIRef(range_uri)))  # Ensure the class uses the bound namespace

                range_notation = next(g.objects(range_uri, SKOS.notation), None)
                if range_notation:
                    range_shape = URIRef(f"{shacl_namespace}{range_notation}Shape")
                    g1.add((prop_shape, SH["node"], range_shape))
                else:
                    logger.warning(f"No skos:notation found for range URI: {range_uri}")

def initialize_graphs(ceds_path, extension_path):
    """Initialize RDF graphs for CEDS Ontology and Extension Ontology."""
    logger.info("Initializing graphs...")
    g = Graph()
    try:
        # Parse the CEDS Ontology file
        logger.info(f"Parsing CEDS Ontology file: {ceds_path}")
        g.parse(ceds_path, format=rdflib.util.guess_format(ceds_path))
        if extension_path:
            # Parse the Extension Ontology file
            logger.info(f"Parsing Extension Ontology file: {extension_path}")
            g.parse(extension_path, format=rdflib.util.guess_format(extension_path))
    except Exception as e:
        logger.exception(f"Failed to parse RDF files: {e}")
        raise

    logger.info("CEDS and Extension graphs initialized.")

    # Create a new graph for SHACL shapes
    g1 = Graph()
    for prefix, uri in namespaces.items():
        add_namespace(namespaces, prefix, uri)
        g1.namespace_manager.bind(prefix, uri, override=True)
    g1.namespace_manager.bind("sh", SH, override=True)
    g1.namespace_manager.bind("rdf", RDF, override=True)
    g1.namespace_manager.bind("xsd", XSD, override=True)
    g1.namespace_manager.bind("schema", SDO, override=True)
    logger.info("SHACL graph initialized.")

    return g, g1

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
            add_namespace(namespaces, namespace_shortname, namespace_url)
            combined_graph.namespace_manager.bind(namespace_shortname, Namespace(namespace_url))  # Bind namespace
            combined_graph += temp_graph  # Merge the file's graph into the combined graph
            st.success(f"Ontology file '{file.name}' loaded successfully with namespace '{namespace_shortname}'.")
        except Exception as e:
            st.error(f"Failed to load ontology file '{file.name}': {e}")
    return combined_graph

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
