from rdflib import Graph, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, SH, XSD, SDO, SKOS
from rdflib.collection import Collection
import logging
import csv
from pathlib import Path
from io import BytesIO
from utils.common import add_namespace, get_rdf_format, get_label, get_properties_for_class
import streamlit as st
import json
from streamlit_ace import st_ace

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

def ontology_manager():
    st.subheader("Manage Ontology Files")

    uploaded_ontology_files = st.file_uploader(
        "Upload Ontology Files",
        type=["ttl", "rdf", "xml"],
        accept_multiple_files=True
    )

    existing_file_ids = {f[0].file_id for f in st.session_state.file_list}

    # Append new files with defaults
    if uploaded_ontology_files:
        for file in uploaded_ontology_files:
            if file.file_id not in existing_file_ids:
                st.session_state.file_list.append(
                    (file, "http://ceds.ed.gov/terms#", "ceds")
                )

    # Rebuild list with updated text box values
    updated_list = []
    for file, namespace_url, namespace_shortname in st.session_state.file_list:
        url_key = f"url_{file.file_id}"
        short_key = f"short_{file.file_id}"

        # Use saved values directly as the default
        namespace_url = st.text_input(
            f"Namespace URL for {file.name}",
            value=namespace_url,
            key=url_key
        )
        namespace_shortname = st.text_input(
            f"Namespace Shortname for {file.name}",
            value=namespace_shortname,
            key=short_key
        )

        updated_list.append((file, namespace_url, namespace_shortname))

    st.session_state.file_list = updated_list

    logging.warning(st.session_state.file_list)

    # Button to load ontologies using the stored file list
    if st.button("Load Ontologies"):
        st.session_state.combined_graph = load_ontologies(st.session_state.file_list)

    st.subheader("Upload Property File")

    # Show a status message if a graph is already loaded
    if st.session_state.get("property_graph") and len(st.session_state.property_graph) > 0:
        st.info("A SHACL property file is already loaded. Uploading a new file will replace it.")

    # Always show the uploader
    uploaded = st.file_uploader(
        "Upload Property File",
        type=["ttl", "rdf", "xml"],
        accept_multiple_files=False
    )

    if uploaded is not None:
        try:
            file_content = uploaded.getvalue()

            # Optional: detect format based on extension
            def get_rdf_format(filename):
                ext = filename.split(".")[-1].lower()
                return {
                    "ttl": "turtle",
                    "rdf": "xml",
                    "xml": "xml",
                    "n3": "n3",
                    "nt": "nt"
                }.get(ext, "turtle")

            fmt = get_rdf_format(uploaded.name)

            g = Graph()
            g.parse(data=file_content, format=fmt)
            st.session_state.property_graph = g

            st.success(f"SHACL file '{uploaded.name}' loaded and parsed successfully.")
        except Exception as e:
            st.error(f"Failed to parse SHACL file: {e}")


def load_ontologies(file_list):
    """Load all files from session_state into a combined RDF graph."""
    combined_graph = Graph()

    for file, namespace_url, namespace_shortname in file_list:
        try:
            rdf_format = get_rdf_format(file.name)
            if not rdf_format:
                raise ValueError(f"Unsupported file format for {file.name}.")

            temp_graph = Graph()
            file_content = file.getvalue()  # Use getvalue() instead of read() to avoid empty reads
            temp_graph.parse(data=file_content, format=rdf_format)

            # Bind the namespace
            add_namespace(namespaces, namespace_shortname, namespace_url)
            combined_graph.namespace_manager.bind(namespace_shortname, Namespace(namespace_url))
            combined_graph += temp_graph

            st.success(f"Ontology file '{file.name}' loaded successfully with namespace '{namespace_shortname}'.")

        except Exception as e:
            st.error(f"Failed to load ontology file '{file.name}': {e}")

    return combined_graph

def display_classes_and_properties():
    st.subheader("Classes and Properties")
    """Display classes and their properties in a tree-like structure."""
    if "combined_graph" not in st.session_state or len(st.session_state.combined_graph) == 0:
        st.info("No ontology files loaded. Please upload files.")
        return

    # Initialize session state for class-property mappings

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


def display_constraints():
    st.subheader("Constraints")

    if "property_graph" not in st.session_state or st.session_state.property_graph is None:
        st.warning("No SHACL property graph loaded.")
        return

    if "class_property_map" not in st.session_state or not st.session_state.class_property_map:
        st.info("No properties selected. Please select properties in the 'Class and Property Menu' page.")
        return

    combined_graph = st.session_state.combined_graph
    property_graph = st.session_state.property_graph
    class_property_map = st.session_state.class_property_map

    for class_uri, properties in class_property_map.items():
        class_label = get_label(class_uri, combined_graph)
        with st.expander(f"Class: {class_label}"):
            for prop_uri in properties:
                # Find PropertyShape(s) that have sh:path = this property
                shapes = list(property_graph.subjects(predicate=SH.path, object=prop_uri))

                # Skip property if any associated shape has sh:nodeKind sh:IRI
                skip_due_to_nodekind = any(
                    property_graph.value(shape, SH.nodeKind) == SH.IRI
                    for shape in shapes
                )
                if skip_due_to_nodekind:
                    continue

                prop_label = get_label(prop_uri, combined_graph)
                st.markdown(f"#### Property: {prop_label} (`{prop_uri}`)")

                if not shapes:
                    st.warning("No SHACL PropertyShape found for this property.")
                    continue

                for shape in shapes:
                    st.markdown(f"**Shape URI:** `{shape}`")
                    for p, o in property_graph.predicate_objects(subject=shape):
                        p_label = get_label(p, property_graph)
                        o_label = get_label(o, property_graph)
                        st.write(f"- **{p_label}**: {o_label}")



def get_label(uri, graph):
    label = graph.value(uri, RDFS.label)
    if label:
        return str(label)
    elif isinstance(uri, str):
        return uri.split("/")[-1].split("#")[-1]
    else:
        return uri.n3(graph.namespace_manager)


def show_SHACL():
    st.header("SHACL")
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

