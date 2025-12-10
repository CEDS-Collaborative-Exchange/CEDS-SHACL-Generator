from rdflib import Graph, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, SH, XSD, SDO, SKOS
from rdflib.collection import Collection
from rdflib.term import Node
import rdflib
import logging
import csv
from pathlib import Path
from io import BytesIO
from utils.common import add_namespace, get_properties_for_class_deep, get_rdf_format, get_label, get_properties_for_class
import streamlit as st
import json
from streamlit_ace import st_ace
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

namespaces = {}

# Cached graph parsing functions

@st.cache_resource(show_spinner=False)
def _parse_ontology_file(_file_content: bytes, format: str, file_name: str) -> Graph:
    """Parse an RDF file into a cached Graph. Underscore prefix prevents hashing."""
    graph = Graph()
    graph.parse(data=_file_content, format=format)
    logger.info(f"Parsed '{file_name}' with {len(graph)} triples")
    return graph


@st.cache_resource(show_spinner=False)
def _combine_graphs(_graph_list: list) -> Graph:
    """Combine multiple RDF graphs into a single cached graph."""
    combined = Graph()
    for graph, ns_url, ns_shortname in _graph_list:
        combined.namespace_manager.bind(ns_shortname, Namespace(ns_url))
        combined += graph
    logger.info(f"Combined {len(_graph_list)} graphs with {len(combined)} triples")
    return combined


# Persistent graph cache (survives Streamlit reruns)

@st.cache_resource
def _get_graph_cache() -> dict:
    """Return singleton dictionary for storing graphs across reruns."""
    logger.info("Initializing graph cache")
    return {}


def store_graph(graph_id: str, graph: Graph) -> None:
    """Store a graph in the persistent cache."""
    cache = _get_graph_cache()
    cache[graph_id] = graph
    logger.info(f"Stored graph '{graph_id}' with {len(graph)} triples")


def get_cached_graph(graph_id: str) -> Graph:
    """Retrieve a graph from cache, or empty Graph if not found."""
    cache = _get_graph_cache()
    graph = cache.get(graph_id, Graph())
    if graph_id and graph_id not in cache:
        logger.warning(f"Graph '{graph_id}' not found in cache")
    return graph


@st.cache_data(show_spinner=False)
def _extract_class_metadata(_graph: Graph) -> dict:
    """Extract all class/property metadata in a single pass. Returns dict with 'classes' and 'labels'."""
    metadata = {
        'classes': {},
        'labels': {}
    }
    
    # Extract all labels in one pass
    for subj, obj in _graph.subject_objects(RDFS.label):
        metadata['labels'][str(subj)] = str(obj)
    
    # Get all classes
    classes = list(_graph.subjects(RDF.type, RDFS.Class))
    
    # For each class, get its properties
    for class_uri in classes:
        class_uri_str = str(class_uri)
        
        # Get label (fallback to URI if no label)
        label = metadata['labels'].get(class_uri_str, class_uri_str)
        
        # Get properties using the existing function
        properties = get_properties_for_class_deep(class_uri, _graph)
        
        metadata['classes'][class_uri_str] = {
            'label': label,
            'properties': [str(p) for p in properties]
        }
    
    logger.info(f"Extracted metadata for {len(metadata['classes'])} classes with {len(metadata['labels'])} labels")
    return metadata


@st.cache_data(show_spinner=False)
def _extract_property_constraints(_property_graph: Graph) -> dict:
    """Extract all property shape constraints in a single pass."""
    constraints = {}
    
    # Get all property shapes
    for prop_shape in _property_graph.subjects(RDF.type, SH.PropertyShape):
        prop_path = _property_graph.value(prop_shape, SH.path)
        if prop_path:
            prop_uri = str(prop_path)
            constraints[prop_uri] = {}
            
            # Extract all constraint predicates
            for pred, obj in _property_graph.predicate_objects(prop_shape):
                pred_str = str(pred)
                # Store constraint values
                if pred_str.startswith('http://www.w3.org/ns/shacl#'):
                    constraint_name = pred_str.split('#')[-1]
                    if constraint_name not in ['path', 'type']:  # Skip metadata
                        constraints[prop_uri][constraint_name] = str(obj)
    
    logger.info(f"Extracted constraints for {len(constraints)} properties")
    return constraints


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

    ignored_props_list: List[Node] = [RDF.type, URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#id"), RDF.value, RDFS.label]
    ignored_list_node = BNode()
    Collection(g1, ignored_list_node, ignored_props_list)

    g1.add((node_title, SH.ignoredProperties, ignored_list_node))

def create_property_shapes(g1, g, class_uri, property_uris, class_property_map, shacl_namespace):
    class_notation = next(g.objects(URIRef(class_uri), SKOS.notation), None)
    if not class_notation:
        logger.warning(f"No skos:notation found for class URI: {class_uri}")
        return

    class_node_title = URIRef(f"{shacl_namespace}{class_notation}Shape")
    
    # Get property graph from cache to check if shapes already exist
    property_graph = get_cached_graph(st.session_state.property_graph_id) if st.session_state.get("property_graph_id") else None

    for prop_uri in property_uris:
        ranges = list(g.objects(URIRef(prop_uri), SDO.rangeIncludes))
        prop_notation = next(g.objects(URIRef(prop_uri), SKOS.notation), None)

        if not prop_notation:
            logger.warning(f"No skos:notation found for property URI: {prop_uri}")
            continue  

        for prefix, uri in g.namespaces():
            if str(prop_uri).startswith(str(uri)):
                prop_namespace = uri
                break
        else:
            prop_namespace = str(prop_uri).rsplit("#", 1)[0] + "#"

        # Always use human-readable shape name based on property notation
        prop_shape = URIRef(f"{prop_namespace}{prop_notation}Shape")
        
        # Check if this property already has a shape defined in the PropertyShapes.ttl file
        property_exists_in_shapes_file = False
        if property_graph and len(property_graph) > 0:
            # Look for a shape with sh:path pointing to this property
            shapes_for_prop = list(property_graph.subjects(SH.path, URIRef(prop_uri)))
            if shapes_for_prop:
                # Property exists in shapes file - don't need to redefine unless custom constraints
                property_exists_in_shapes_file = True

        # Determine if there are any truly custom constraints (not just defaults from property graph)
        constraints_key = f"{class_uri}::{prop_uri}"
        constraints = st.session_state.property_constraints.get(constraints_key, {})
        
        # Check if constraints are truly custom by comparing with property graph defaults
        has_truly_custom_constraints = False
        custom_constraints_to_add = {}  # Store only the truly custom constraints
        
        if constraints and property_graph and len(property_graph) > 0:
            # Find the shape in the property graph for this property
            property_shapes = list(property_graph.subjects(predicate=SH.path, object=URIRef(prop_uri)))
            
            for prop_graph_shape in property_shapes:
                for constraint_name, constraint_data in constraints.items():
                    if constraint_data.get("enabled", False):
                        shacl_predicate = getattr(SH, constraint_name, None)
                        if shacl_predicate:
                            # Get the default value from the property graph
                            default_value = property_graph.value(prop_graph_shape, shacl_predicate)
                            user_value = constraint_data["value"]
                            
                            is_custom = False
                            
                            # Convert both to comparable types
                            if default_value is not None:
                                default_python_value = convert_rdf_literal_to_python(default_value)
                                
                                # Compare values - if they're different, it's a custom constraint
                                if constraint_name in ["minCount", "maxCount", "minLength", "maxLength"]:
                                    try:
                                        uv = int(user_value) if user_value is not None else None
                                        dv = int(default_python_value) if default_python_value is not None else None
                                    except Exception:
                                        uv = str(user_value)
                                        dv = str(default_python_value)
                                    if uv != dv:
                                        is_custom = True
                                elif constraint_name in ["minInclusive", "maxInclusive", "minExclusive", "maxExclusive"]:
                                    try:
                                        uvf = float(user_value) if user_value is not None else None
                                        dvf = float(default_python_value) if default_python_value is not None else None
                                    except Exception:
                                        uvf = str(user_value)
                                        dvf = str(default_python_value)
                                    if uvf != dvf:
                                        is_custom = True
                                elif constraint_name == "pattern":
                                    if str(user_value) != str(default_python_value):
                                        is_custom = True
                                elif constraint_name == "uniqueLang":
                                    if bool(user_value) != bool(default_python_value):
                                        is_custom = True
                                elif constraint_name == "nodeKind":
                                    # Compare node kind values
                                    node_kind_map = {
                                        "IRI": SH.IRI,
                                        "BlankNode": SH.BlankNode,
                                        "Literal": SH.Literal,
                                        "BlankNodeOrIRI": SH.BlankNodeOrIRI,
                                        "BlankNodeOrLiteral": SH.BlankNodeOrLiteral,
                                        "IRIOrLiteral": SH.IRIOrLiteral
                                    }
                                    user_node_kind = node_kind_map.get(str(user_value), SH.IRI)
                                    if user_node_kind != default_value:
                                        is_custom = True
                                elif constraint_name == "languageIn":
                                    # Compare language lists
                                    if str(user_value) != str(default_python_value):
                                        is_custom = True
                                else:
                                    if str(user_value) != str(default_python_value):
                                        is_custom = True
                            else:
                                # No default value exists, so any user value is custom
                                is_custom = True
                            
                            if is_custom:
                                has_truly_custom_constraints = True
                                custom_constraints_to_add[constraint_name] = constraint_data
                
                if has_truly_custom_constraints:
                    break

        # Always add the property shape reference to the class NodeShape
        g1.add((class_node_title, SH.property, prop_shape))
        
        # Determine if we need to create a PropertyShape definition in this file
        # - If property exists in PropertyShapes.ttl and has NO custom constraints: don't create definition
        # - If property does NOT exist in PropertyShapes.ttl: create full definition
        # - If property has custom constraints: create definition with those constraints
        needs_shape_definition = not property_exists_in_shapes_file or has_truly_custom_constraints
        
        # Track additional constraints from range processing
        additional_constraints = []
        
        # Get all of the RDFS classes in the graph to check if the range is a CEDS base class and not an option set
        classes = list(g.subjects(RDF.type, RDFS.Class))
        for range_uri in ranges:

            # Check if the range is a class and not a datatype
            if "#C" in str(range_uri):

                # Check if the property is an option set by seeing if range_uri (concept scheme) is used as a class anywhere (concepts)
                option_set = list(g.subjects(RDF.type, URIRef(range_uri)))
                if len(option_set) > 0:
                    if any(not str(s).startswith("http://ceds.ed.gov/terms#") for s in option_set):
                        # Custom option set - needs its own definition
                        needs_shape_definition = True
                        option_set_node = BNode()
                        Collection(g1, option_set_node, option_set)
                        additional_constraints.append((SH["in"], option_set_node))

                # If the range is an RDFS Class (CEDS Class, not option set), add class/node constraints
                elif range_uri in classes:
                    needs_shape_definition = True
                    range_notation = next(g.objects(range_uri, SKOS.notation), None)

                    if not range_notation:
                        logger.warning(f"No skos:notation found for range URI: {range_uri}")
                        continue

                    for prefix, uri in g.namespaces():
                        if str(range_uri).startswith(str(uri)):
                            range_namespace = uri
                            break
                    else:
                        range_namespace = str(range_uri).rsplit("#", 1)[0] + "#"

                    range_shape = URIRef(f"{range_namespace}{range_notation}Shape")

                    additional_constraints.append((SH["class"], URIRef(range_uri)))
                    additional_constraints.append((SH["node"], range_shape))

                    if str(range_uri) not in class_property_map:
                        additional_constraints.append((SH.nodeKind, SH.IRI))

        # Only create PropertyShape definition if needed
        if needs_shape_definition:
            g1.add((prop_shape, RDF.type, SH.PropertyShape))
            g1.add((prop_shape, SH.path, URIRef(prop_uri)))
            
            # Add additional constraints from range processing
            for predicate, obj in additional_constraints:
                g1.add((prop_shape, predicate, obj))
            
            # Add custom constraints (those that differ from defaults)
            for constraint_name, constraint_data in custom_constraints_to_add.items():
                shacl_predicate = getattr(SH, constraint_name, None)
                if shacl_predicate:
                    value = constraint_data["value"]
                    error_message = constraint_data.get("error_message", "")
                    
                    # Handle different data types appropriately
                    if constraint_name in ["minCount", "maxCount", "minLength", "maxLength"]:
                        literal_value = Literal(int(value))
                    elif constraint_name in ["minInclusive", "maxInclusive", "minExclusive", "maxExclusive"]:
                        # Determine appropriate datatype based on the property's datatype
                        datatype = constraint_data.get("datatype")
                        if datatype and str(datatype) in [str(XSD.integer), str(XSD.int), str(XSD.long)]:
                            literal_value = Literal(int(value))
                        else:
                            literal_value = Literal(float(value))
                    elif constraint_name == "pattern":
                        literal_value = Literal(str(value))
                    elif constraint_name == "uniqueLang":
                        literal_value = Literal(bool(value), datatype=XSD.boolean)
                    elif constraint_name == "nodeKind":
                        # Handle nodeKind as a resource, not a literal
                        node_kind_map = {
                            "IRI": SH.IRI,
                            "BlankNode": SH.BlankNode,
                            "Literal": SH.Literal,
                            "BlankNodeOrIRI": SH.BlankNodeOrIRI,
                            "BlankNodeOrLiteral": SH.BlankNodeOrLiteral,
                            "IRIOrLiteral": SH.IRIOrLiteral
                        }
                        literal_value = node_kind_map.get(str(value), SH.IRI)
                        g1.add((prop_shape, shacl_predicate, literal_value))
                        if error_message:
                            g1.add((prop_shape, SH.message, Literal(error_message)))
                        continue
                    elif constraint_name == "languageIn":
                        # Handle languageIn as a list
                        languages = [lang.strip() for lang in str(value).split(",") if lang.strip()]
                        if languages:
                            lang_list_node = BNode()
                            Collection(g1, lang_list_node, [Literal(lang) for lang in languages])
                            g1.add((prop_shape, shacl_predicate, lang_list_node))
                        if error_message:
                            g1.add((prop_shape, SH.message, Literal(error_message)))
                        continue
                    else:
                        literal_value = Literal(str(value))
                    
                    g1.add((prop_shape, shacl_predicate, literal_value))
                    if error_message:
                        g1.add((prop_shape, SH.message, Literal(error_message)))
        

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
        namespace_url_input = st.text_input(
            f"Namespace URL for {file.name}",
            value=namespace_url,
            key=url_key
        )
        
        # Validate URL format
        import re
        url_pattern = re.compile(r'^https?://[^\s]+$')
        if namespace_url_input and not url_pattern.match(namespace_url_input):
            st.error(f"Invalid URL format for {file.name}. Must start with http:// or https://")
            namespace_url_input = namespace_url  # Revert to previous valid value
        
        namespace_shortname_input = st.text_input(
            f"Namespace Shortname for {file.name}",
            value=namespace_shortname,
            key=short_key
        )
        
        # Validate shortname (alphanumeric and underscores only)
        shortname_pattern = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        if namespace_shortname_input and not shortname_pattern.match(namespace_shortname_input):
            st.error(f"Invalid shortname for {file.name}. Must start with a letter or underscore and contain only alphanumeric characters and underscores.")
            namespace_shortname_input = namespace_shortname  # Revert to previous valid value

        updated_list.append((file, namespace_url_input, namespace_shortname_input))

    st.session_state.file_list = updated_list

    # Button to load ontologies using the stored file list
    if st.button("Load Ontologies"):
        graph = load_ontologies(st.session_state.file_list)
        if len(graph) > 0:
            # Create unique ID and store graph in cache (not session state)
            import hashlib
            # Use N-Triples serialization for consistent hashing
            graph_hash = hashlib.md5(graph.serialize(format='nt').encode()).hexdigest()[:16]
            graph_id = f"combined_{graph_hash}_{len(graph)}"
            store_graph(graph_id, graph)
            st.session_state.combined_graph_id = graph_id
            logger.info(f"Combined graph stored with ID: {graph_id}")

    st.subheader("Upload Property File")

    # Show a status message if a graph is already loaded
    if st.session_state.get("property_graph_id"):
        property_graph = get_cached_graph(st.session_state.property_graph_id)
        if len(property_graph) > 0:
            st.info("A SHACL property file is already loaded. Uploading a new file will replace it.")

    # Always show the uploader
    uploaded = st.file_uploader(
        "Upload Property File",
        type=["ttl", "rdf", "xml"],
        accept_multiple_files=False
    )

    if uploaded is not None:
        # Validate file size (max 100MB)
        max_file_size = 100 * 1024 * 1024  # 100MB in bytes
        if uploaded.size > max_file_size:
            st.error(f"File '{uploaded.name}' is too large ({uploaded.size / 1024 / 1024:.2f}MB). Maximum allowed size is 100MB.")
        else:
            try:
                file_content = uploaded.getvalue()
                
                # Validate file is not empty
                if not file_content:
                    st.error(f"File '{uploaded.name}' is empty.")
                    return

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

                with st.spinner(f"Loading {uploaded.name}..."):
                    g = _parse_ontology_file(file_content, fmt, uploaded.name)
                
                # Validate graph has content
                if len(g) == 0:
                    st.warning(f"File '{uploaded.name}' was parsed but contains no RDF triples.")
                else:
                    # Store in cache with ID to avoid session state hashing
                    import hashlib
                    graph_id = f"property_{hashlib.md5(file_content).hexdigest()}_{len(g)}"
                    store_graph(graph_id, g)
                    st.session_state.property_graph_id = graph_id
                    st.success(f"SHACL file '{uploaded.name}' loaded successfully with {len(g)} triples.")
            except Exception as e:
                st.error(f"Failed to parse SHACL file '{uploaded.name}': {str(e)}")
                logger.exception(f"Failed to parse property file: {e}")

        st.subheader("Manage Ontology Files")

    existing_shacl = st.file_uploader(
        "Update an Existing SHACL File",
        type=["ttl", "rdf", "xml"],
        accept_multiple_files=False
    )

    # Load the existing SHACL file
    if existing_shacl is not None:
        # Validate file size (max 100MB)
        max_file_size = 100 * 1024 * 1024  # 100MB in bytes
        if existing_shacl.size > max_file_size:
            st.error(f"File '{existing_shacl.name}' is too large ({existing_shacl.size / 1024 / 1024:.2f}MB). Maximum allowed size is 100MB.")
        else:
            try:
                file_content = existing_shacl.getvalue()
                
                # Validate file is not empty
                if not file_content:
                    st.error(f"File '{existing_shacl.name}' is empty.")
                    return

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

                fmt = get_rdf_format(existing_shacl.name)

                with st.spinner(f"Loading {existing_shacl.name}..."):
                    g = _parse_ontology_file(file_content, fmt, existing_shacl.name)
                
                # Validate graph has content
                if len(g) == 0:
                    st.warning(f"File '{existing_shacl.name}' was parsed but contains no RDF triples.")
                    return

                # Retrieve property graph from cache
                property_graph = get_cached_graph(st.session_state.property_graph_id) if st.session_state.property_graph_id else Graph()

                # Save the SHACL for later use with constraints (store in cache with ID)
                import hashlib
                graph_id = f"existing_{hashlib.md5(file_content).hexdigest()}_{len(g)}"
                store_graph(graph_id, g)
                st.session_state.existing_shacl_id = graph_id

                # Find all node shapes in the graph
                node_shapes = list(g.subjects(RDF.type, SH.NodeShape))
                
                # Track import statistics for debugging
                import_stats = {
                    "node_shapes": len(node_shapes),
                    "properties_found": 0,
                    "properties_missing_path": 0,
                    "properties_from_uri": 0,
                    "properties_from_local_name": 0
                }
                
                # Debug: Log property_graph status
                if property_graph is not None and len(property_graph) > 0:
                    prop_shapes_in_pg = list(property_graph.subjects(RDF.type, SH.PropertyShape))
                    logger.info(f"Property graph has {len(property_graph)} triples and {len(prop_shapes_in_pg)} PropertyShapes")
                else:
                    logger.warning("Property graph is empty or not loaded - import may be incomplete!")

                for node_shape in node_shapes:
                    # Get the target class for this node shape
                    target_class = g.value(node_shape, SH.targetClass)
                    
                    if target_class:
                        # Get all property shapes for this node shape
                        property_shapes = list(g.objects(node_shape, SH.property))

                        # Create a set for the properties of this class
                        properties = set()
                        
                        # Add each property path to the set
                        for prop_shape in property_shapes:
                            path = None
                            strategy_used = None
                            
                            # Strategy 1: Get sh:path directly from the imported SHACL file
                            path = g.value(prop_shape, SH.path)
                            if path:
                                strategy_used = "direct"
                            
                            if path is None and property_graph is not None and len(property_graph) > 0:
                                # Strategy 2: Look up in property_graph by the exact URI
                                path = property_graph.value(prop_shape, SH.path)
                                if path:
                                    strategy_used = "property_graph_exact"
                                
                                # Strategy 2b: The property_graph might use different namespace prefixes
                                # Try looking up by local name if full URI lookup failed
                                if path is None:
                                    prop_shape_str = str(prop_shape)
                                    # Extract local name (e.g., "RecordEndDateTimeShape" from full URI)
                                    if "#" in prop_shape_str:
                                        local_name = prop_shape_str.split("#")[-1]
                                    else:
                                        local_name = prop_shape_str.split("/")[-1]
                                    
                                    # Search property_graph for any subject with this local name that has sh:path
                                    for subj in property_graph.subjects(RDF.type, SH.PropertyShape):
                                        subj_str = str(subj)
                                        subj_local = subj_str.split("#")[-1] if "#" in subj_str else subj_str.split("/")[-1]
                                        if subj_local == local_name:
                                            path = property_graph.value(subj, SH.path)
                                            if path:
                                                strategy_used = "property_graph_local_name"
                                                import_stats["properties_from_local_name"] += 1
                                                logger.debug(f"Found path via local name match: {local_name} -> {path}")
                                                break
                            
                            if path is None:
                                # Strategy 3: If prop_shape is a URI ending in "Shape", try to derive the property URI
                                # e.g., "http://ceds.ed.gov/terms#lastNameShape" -> "http://ceds.ed.gov/terms#lastName"
                                prop_shape_str = str(prop_shape)
                                if prop_shape_str.endswith("Shape"):
                                    # Remove "Shape" suffix to get potential property URI
                                    potential_prop_uri = prop_shape_str[:-5]  # Remove "Shape"
                                    
                                    # Verify this property exists in the property_graph or combined_graph
                                    if property_graph is not None and len(property_graph) > 0:
                                        # Check if there's a shape with this path in property_graph
                                        shapes_with_path = list(property_graph.subjects(SH.path, URIRef(potential_prop_uri)))
                                        if shapes_with_path:
                                            path = URIRef(potential_prop_uri)
                                            strategy_used = "derived_from_uri"
                                            import_stats["properties_from_uri"] += 1
                                    
                                    # Also check combined_graph if available
                                    if path is None:
                                        combined_graph_check = get_cached_graph(st.session_state.combined_graph_id) if st.session_state.get("combined_graph_id") else None
                                        if combined_graph_check and len(combined_graph_check) > 0:
                                            # Check if this URI exists as a property in the ontology
                                            prop_types = list(combined_graph_check.objects(URIRef(potential_prop_uri), RDF.type))
                                            if prop_types:
                                                path = URIRef(potential_prop_uri)
                                                strategy_used = "derived_from_uri_ontology"
                                                import_stats["properties_from_uri"] += 1
                            
                            # Strategy 4: Look up property by skos:notation in combined_graph
                            # Shape name like "DataCollectionAcademicSchoolYearShape" -> notation "DataCollectionAcademicSchoolYear"
                            if path is None:
                                combined_graph_check = get_cached_graph(st.session_state.combined_graph_id) if st.session_state.get("combined_graph_id") else None
                                if combined_graph_check and len(combined_graph_check) > 0:
                                    prop_shape_str = str(prop_shape)
                                    if prop_shape_str.endswith("Shape"):
                                        # Extract the notation (remove namespace and "Shape" suffix)
                                        if "#" in prop_shape_str:
                                            shape_local = prop_shape_str.split("#")[-1]
                                        else:
                                            shape_local = prop_shape_str.split("/")[-1]
                                        potential_notation = shape_local[:-5]  # Remove "Shape"
                                        
                                        # Search for property with this skos:notation
                                        for prop_subj in combined_graph_check.subjects(SKOS.notation, Literal(potential_notation)):
                                            # Verify it's a property (has domainIncludes or rangeIncludes)
                                            if (combined_graph_check.value(prop_subj, SDO.domainIncludes) or 
                                                combined_graph_check.value(prop_subj, SDO.rangeIncludes)):
                                                path = prop_subj
                                                strategy_used = "notation_lookup"
                                                import_stats["properties_from_uri"] += 1
                                                logger.debug(f"Found path via notation lookup: {potential_notation} -> {path}")
                                                break
                            
                            if path is not None:
                                properties.add(str(path))
                                import_stats["properties_found"] += 1
                                logger.debug(f"Resolved {prop_shape} -> {path} (strategy: {strategy_used})")
                            else:
                                import_stats["properties_missing_path"] += 1
                                logger.warning(f"Could not find sh:path for property shape: {prop_shape}")

                        # Add the class and its properties to the map
                        if len(properties) > 0:
                            st.session_state.class_property_map[str(target_class)] = set(properties)
                
                # Log import statistics
                logger.info(f"SHACL Import stats: {import_stats}")
                if import_stats["properties_missing_path"] > 0:
                    st.warning(f"Note: {import_stats['properties_missing_path']} property shapes could not be resolved. "
                              f"Make sure the Property File is loaded before importing existing SHACL.")

                st.success(f"SHACL file '{existing_shacl.name}' loaded successfully with {len(g)} triples. "
                          f"Found {import_stats['properties_found']} properties across {import_stats['node_shapes']} node shapes.")
            except Exception as e:
                st.error(f"Failed to parse SHACL file '{existing_shacl.name}': {str(e)}")
                logger.exception(f"Failed to parse existing SHACL file: {e}")


def load_ontologies(file_list):
    """Load all files from session_state into a combined RDF graph using cached parsing."""
    # Validate file list is not empty
    if not file_list:
        st.warning("No ontology files to load.")
        return Graph()

    parsed_graphs = []  # List of (Graph, namespace_url, namespace_shortname) tuples
    
    for file, namespace_url, namespace_shortname in file_list:
        # Validate file size (max 100MB)
        max_file_size = 100 * 1024 * 1024  # 100MB in bytes
        if file.size > max_file_size:
            st.error(f"File '{file.name}' is too large ({file.size / 1024 / 1024:.2f}MB). Maximum allowed size is 100MB.")
            continue
            
        try:
            rdf_format = get_rdf_format(file.name)
            if not rdf_format:
                raise ValueError(f"Unsupported file format for {file.name}.")

            file_content = file.getvalue()  # Use getvalue() instead of read() to avoid empty reads
            
            # Validate file is not empty
            if not file_content:
                st.error(f"File '{file.name}' is empty.")
                continue
            
            with st.spinner(f"Loading {file.name}..."):
                temp_graph = _parse_ontology_file(file_content, rdf_format, file.name)
            
            # Validate graph has content
            if len(temp_graph) == 0:
                st.warning(f"File '{file.name}' was parsed but contains no RDF triples.")
                continue

            # Bind the namespace to global namespaces dict
            add_namespace(namespaces, namespace_shortname, namespace_url)
            
            # Store parsed graph with namespace info for combining
            parsed_graphs.append((temp_graph, namespace_url, namespace_shortname))

            st.success(f"Ontology file '{file.name}' loaded successfully with {len(temp_graph)} triples (namespace '{namespace_shortname}').")

        except Exception as e:
            st.error(f"Failed to load ontology file '{file.name}': {str(e)}")
            logger.exception(f"Failed to load ontology file: {e}")
    
    if parsed_graphs:
        combined_graph = _combine_graphs(parsed_graphs)
        st.info(f"Total combined graph contains {len(combined_graph)} triples from {len(parsed_graphs)} file(s).")
        return combined_graph
    else:
        return Graph()


# Fragment-based UI components for performance

def _render_class_properties_fragment(class_uri_str: str, class_label: str, 
                                       sorted_property_uris: list, labels: dict):
    """Render property checkboxes for a single class."""
    # Get current selections from session state
    current_selections = st.session_state.class_property_map.get(class_uri_str, set())
    
    # Determine if all properties are selected
    all_selected = len(sorted_property_uris) > 0 and all(
        prop_uri in current_selections
        for prop_uri in sorted_property_uris
    )
    
    # Select All checkbox
    select_all_key = f"select_all_{class_uri_str}"
    select_all_value = st.checkbox(
        "Select All Properties",
        value=all_selected,
        key=select_all_key
    )
    
    # Handle Select All logic
    if select_all_value and not all_selected:
        # User just checked "Select All" - add all properties
        st.session_state.class_property_map[class_uri_str] = set(sorted_property_uris)
        current_selections = st.session_state.class_property_map[class_uri_str]
    elif not select_all_value and all_selected:
        # User just unchecked "Select All" - remove all properties
        if class_uri_str in st.session_state.class_property_map:
            del st.session_state.class_property_map[class_uri_str]
        current_selections = set()
    
    # Individual property checkboxes
    for prop_uri in sorted_property_uris:
        prop_label = labels.get(prop_uri, prop_uri)
        key = f"{class_uri_str}:{prop_uri}"
        
        is_checked = prop_uri in current_selections
        
        new_value = st.checkbox(
            f"{prop_label}",
            value=is_checked,
            key=key
        )
        
        # Handle individual checkbox changes
        if new_value != is_checked:
            if new_value:
                st.session_state.class_property_map.setdefault(class_uri_str, set()).add(prop_uri)
            else:
                st.session_state.class_property_map.get(class_uri_str, set()).discard(prop_uri)
                # Clean up empty sets
                if class_uri_str in st.session_state.class_property_map and not st.session_state.class_property_map[class_uri_str]:
                    del st.session_state.class_property_map[class_uri_str]


@st.fragment
def _class_expander_fragment(class_uri_str: str, class_label: str, 
                              sorted_property_uris: list, labels: dict):
    """Fragment wrapper for class expander. Checkbox clicks only rerun this fragment."""
    is_expanded = class_uri_str in st.session_state.class_property_map
    
    with st.expander(f"Class: {class_label}", expanded=is_expanded):
        _render_class_properties_fragment(class_uri_str, class_label, 
                                          sorted_property_uris, labels)


def display_classes_and_properties():
    """Display classes and their properties in a tree-like structure."""
    st.subheader("Classes and Properties")
    
    if not st.session_state.combined_graph_id:
        st.info("No ontology files loaded. Please upload files.")
        return
    
    combined_graph = get_cached_graph(st.session_state.combined_graph_id)
    
    if len(combined_graph) == 0:
        st.info("No ontology files loaded. Please upload files.")
        return

    # Extract cached metadata
    metadata = _extract_class_metadata(combined_graph)
    
    # Sort classes alphabetically by label
    sorted_class_items = sorted(
        metadata['classes'].items(),
        key=lambda item: item[1]['label'].lower()
    )
    
    # Display summary
    total_classes = len(sorted_class_items)
    selected_classes = len(st.session_state.class_property_map)
    st.caption(f"📊 {total_classes} classes available | {selected_classes} classes with selections")
    
    # Render each class as a fragment for fast interactions
    for class_uri_str, class_data in sorted_class_items:
        class_label = class_data['label']
        property_uris = class_data['properties']
        
        # Sort properties alphabetically by label
        sorted_property_uris = sorted(
            property_uris,
            key=lambda prop_uri: metadata['labels'].get(prop_uri, prop_uri).lower()
        )
        
        _class_expander_fragment(class_uri_str, class_label, 
                                  sorted_property_uris, metadata['labels'])


def get_available_constraints_for_datatype(datatype):
    """Return available SHACL constraints based on the property's datatype."""
    base_constraints = {
        "minCount": {"type": "number", "min": 0, "description": "Minimum number of values"},
        "maxCount": {"type": "number", "min": 0, "description": "Maximum number of values"},
        "nodeKind": {"type": "select", "options": ["IRI", "BlankNode", "Literal", "BlankNodeOrIRI", "BlankNodeOrLiteral", "IRIOrLiteral"], "description": "Kind of node"}
    }
    
    if datatype == XSD.string:
        base_constraints.update({
            "minLength": {"type": "number", "min": 0, "description": "Minimum string length"},
            "maxLength": {"type": "number", "min": 0, "description": "Maximum string length"},
            "pattern": {"type": "text", "description": "Regular expression pattern"},
            "languageIn": {"type": "text", "description": "Allowed language tags (comma-separated)"},
            "uniqueLang": {"type": "boolean", "description": "Values must have unique language tags"}
        })
    elif datatype in [XSD.integer, XSD.int, XSD.long, XSD.short, XSD.byte]:
        base_constraints.update({
            "minInclusive": {"type": "number", "description": "Minimum value (inclusive)"},
            "maxInclusive": {"type": "number", "description": "Maximum value (inclusive)"},
            "minExclusive": {"type": "number", "description": "Minimum value (exclusive)"},
            "maxExclusive": {"type": "number", "description": "Maximum value (exclusive)"}
        })
    elif datatype in [XSD.decimal, XSD.float, XSD.double]:
        base_constraints.update({
            "minInclusive": {"type": "number", "step": 0.01, "description": "Minimum value (inclusive)"},
            "maxInclusive": {"type": "number", "step": 0.01, "description": "Maximum value (inclusive)"},
            "minExclusive": {"type": "number", "step": 0.01, "description": "Minimum value (exclusive)"},
            "maxExclusive": {"type": "number", "step": 0.01, "description": "Maximum value (exclusive)"}
        })
    elif datatype == XSD.dateTime:
        base_constraints.update({
            "minInclusive": {"type": "datetime-local", "description": "Minimum date/time (inclusive)"},
            "maxInclusive": {"type": "datetime-local", "description": "Maximum date/time (inclusive)"},
            "minExclusive": {"type": "datetime-local", "description": "Minimum date/time (exclusive)"},
            "maxExclusive": {"type": "datetime-local", "description": "Maximum date/time (exclusive)"}
        })
    elif datatype == XSD.date:
        base_constraints.update({
            "minInclusive": {"type": "date", "description": "Minimum date (inclusive)"},
            "maxInclusive": {"type": "date", "description": "Maximum date (inclusive)"},
            "minExclusive": {"type": "date", "description": "Minimum date (exclusive)"},
            "maxExclusive": {"type": "date", "description": "Maximum date (exclusive)"}
        })
    
    return base_constraints

def convert_rdf_literal_to_python(value):
    """Convert RDF Literal objects to appropriate Python types."""
    if value is None:
        return None
    
    if hasattr(value, 'toPython'):
        # RDFLib Literal object
        try:
            return value.toPython()
        except:
            return str(value)
    else:
        # Already a Python type
        return value

def render_constraint_input(constraint_name, constraint_config, current_value, enabled, key_prefix, existing_error=None):
    """Render the appropriate input widget for a constraint based on its configuration."""
    enable_key = f"{key_prefix}_{constraint_name}_enable"
    value_key = f"{key_prefix}_{constraint_name}_value"
    error_key = f"{key_prefix}_{constraint_name}_error"
    
    # Convert RDF literal to Python type
    current_value = convert_rdf_literal_to_python(current_value)
    
    # Special handling for boolean constraints - they combine enable/value into one checkbox
    if constraint_config["type"] == "boolean":
        # Handle boolean conversion
        if current_value is not None:
            if isinstance(current_value, str):
                current_value = current_value.lower() in ('true', '1', 'yes', 'on')
            else:
                current_value = bool(current_value)
        else:
            current_value = enabled  # Use enabled state as default for boolean constraints
            
        value = st.checkbox(
            f"Enable {constraint_name}",  # Keep consistent naming with other constraints
            value=current_value,
            key=value_key,
            help=constraint_config.get("description", "")
        )
        
        error_message = ""
        if value:
            error_message = st.text_input(
                f"Error message for {constraint_name}",
                value=existing_error if existing_error else "",
                key=error_key,
                help="Message shown when this constraint is violated."
            )
        
        # For boolean constraints, if the checkbox is checked, the constraint is enabled and set to true
        return value, value, error_message
    
    # For non-boolean constraints, show enable checkbox first
    is_enabled = st.checkbox(
        f"Enable {constraint_name}",
        value=enabled,
        key=enable_key,
        help=constraint_config.get("description", "")
    )
    
    if not is_enabled:
        return None, False, ""
    
    # Render appropriate input based on constraint type
    if constraint_config["type"] == "number":
        # Ensure current_value is a valid number
        if current_value is not None:
            try:
                current_value = float(current_value) if isinstance(current_value, str) else current_value
                if constraint_config.get("step", 1) == 1:  # Integer input
                    current_value = int(current_value)
            except (ValueError, TypeError):
                current_value = constraint_config.get("min", 0)
        else:
            current_value = constraint_config.get("min", 0)
            
        value = st.number_input(
            constraint_name,
            min_value=constraint_config.get("min", None),
            step=constraint_config.get("step", 1),
            value=current_value,
            key=value_key
        )
    elif constraint_config["type"] == "text":
        value = st.text_input(
            constraint_name,
            value=str(current_value) if current_value is not None else "",
            key=value_key
        )
    elif constraint_config["type"] == "select":
        options = constraint_config["options"]
        index = 0
        if current_value and str(current_value) in options:
            index = options.index(str(current_value))
        value = st.selectbox(
            constraint_name,
            options=options,
            index=index,
            key=value_key
        )
    elif constraint_config["type"] in ["date", "datetime-local"]:
        value = st.text_input(
            f"{constraint_name} (ISO format)",
            value=str(current_value) if current_value is not None else "",
            key=value_key,
            help=f"Enter in ISO format (e.g., {'2023-12-31T23:59:59' if constraint_config['type'] == 'datetime-local' else '2023-12-31'})"
        )
    else:
        value = st.text_input(
            constraint_name,
            value=str(current_value) if current_value is not None else "",
            key=value_key
        )
    
    error_message = st.text_input(
        f"Error message for {constraint_name}",
        value=existing_error if existing_error else "",
        key=error_key,
        help="Message shown when this constraint is violated."
    )
    
    return value, True, error_message


@st.fragment
def _constraints_class_fragment(class_uri: str, properties: set, labels: dict,
                                  property_graph: Graph, existing_shacl: Graph):
    """Fragment for constraint editing. Input changes only rerun this fragment."""
    class_label = labels.get(class_uri, class_uri)
    
    with st.expander(f"Class: {class_label}", expanded=True):
        for prop_uri in properties:
            # Find PropertyShape(s) that have sh:path = this property
            shapes = list(property_graph.subjects(predicate=SH.path, object=URIRef(prop_uri)))
            
            # Skip property if any associated shape has sh:nodeKind sh:IRI
            skip_due_to_nodekind = any(
                property_graph.value(shape, SH.nodeKind) == SH.IRI
                for shape in shapes
            )
            if skip_due_to_nodekind:
                continue

            prop_label = labels.get(prop_uri, prop_uri)
            st.markdown(f"#### Property: {prop_label} (`{prop_uri}`)")

            if not shapes:
                shapes = list(existing_shacl.subjects(predicate=SH.path, object=URIRef(prop_uri)))
                if not shapes:
                    st.warning("No SHACL PropertyShape found for this property.")
                    continue

            for shape in shapes:
                st.markdown(f"**Shape URI:** `{shape}`")
                
                # Get the datatype of the property
                datatype = property_graph.value(shape, SH.datatype)
                node_kind = property_graph.value(shape, SH.nodeKind)
                
                # Display non-editable properties
                editable_predicates = {
                    SH.minCount, SH.maxCount, SH.minLength, SH.maxLength, SH.pattern,
                    SH.minInclusive, SH.maxInclusive, SH.minExclusive, SH.maxExclusive,
                    SH.nodeKind, SH.languageIn, SH.uniqueLang
                }
                
                st.markdown("**Standard Shape Properties:**")
                for p, o in property_graph.predicate_objects(subject=shape):
                    p_label = labels.get(str(p), str(p))
                    o_label = labels.get(str(o), str(o))
                    st.write(f"- **{p_label}**: {o_label}")

                st.markdown("**Custom Shape Properties:**")
                # Override with existing SHACL properties if available
                for p, o in existing_shacl.predicate_objects(subject=shape):
                    if p in editable_predicates:
                        continue
                    p_label = labels.get(str(p), str(p))
                    o_label = labels.get(str(o), str(o))
                    st.write(f"- **{p_label}**: {o_label}")
                
                if datatype:
                    label = labels.get(str(datatype), str(datatype))
                    st.info(f"Detected datatype: {label}")
                if node_kind:
                    label = labels.get(str(node_kind), str(node_kind))
                    st.info(f"Node kind: {label}")
                
                # Get available constraints for this datatype
                available_constraints = get_available_constraints_for_datatype(datatype)
                
                # Load existing constraint values
                constraints_key = f"{class_uri}::{prop_uri}"
                existing_constraints = st.session_state.property_constraints.get(constraints_key, {})
                
                # Identify and remove overlapping property shapes
                property_shapes = list(existing_shacl.subjects(RDF.type, SH.PropertyShape))
                property_shapes += list(property_graph.subjects(RDF.type, SH.PropertyShape))
                subject_predicate_pairs = []
                
                for ps in property_shapes:
                    path = existing_shacl.value(ps, SH.path)
                    if path is None:
                        path = property_graph.value(ps, SH.path)

                    if path == URIRef(prop_uri):
                        for p, o in existing_shacl.predicate_objects(ps):
                            subject_predicate_pairs.append((ps, p))
                            if p in editable_predicates:
                                constraint_name = str(p).split('#')[-1]
                                if constraint_name in available_constraints:
                                    existing_constraints[constraint_name] = {
                                        "value": convert_rdf_literal_to_python(o),
                                        "enabled": True,
                                        "shape": str(ps),
                                        "class": str(class_uri),
                                        "property": str(prop_uri),
                                        "datatype": str(datatype) if datatype else None
                                    }

                # Load current values from the SHACL graph
                current_values = {}
                for constraint_name in available_constraints.keys():
                    shacl_predicate = getattr(SH, constraint_name, None)
                    if shacl_predicate:
                        value = property_graph.value(shape, shacl_predicate)
                        if value is not None:
                            current_values[constraint_name] = convert_rdf_literal_to_python(value)
                
                st.markdown("**Edit Constraints:**")
                
                # Create two columns for better layout
                col1, col2 = st.columns(2)
                
                updated_constraints = {}
                constraint_items = list(available_constraints.items())
                mid_point = len(constraint_items) // 2
                
                # Split constraints between two columns
                for i, (constraint_name, constraint_config) in enumerate(constraint_items):
                    col = col1 if i < mid_point else col2
                    
                    with col:
                        # Get existing values
                        existing_enabled = existing_constraints.get(constraint_name, {}).get("enabled", False)
                        existing_value = existing_constraints.get(constraint_name, {}).get("value")
                        existing_error = existing_constraints.get(constraint_name, {}).get("error_message", "")
                        
                        # Use current SHACL value if no custom constraint exists
                        if not existing_enabled and constraint_name in current_values:
                            display_value = current_values[constraint_name]
                            existing_enabled = True
                        else:
                            display_value = existing_value
                        
                        key_prefix = f"{constraints_key}_{constraint_name}"
                        value, is_enabled, error_message = render_constraint_input(
                            constraint_name, 
                            constraint_config, 
                            display_value, 
                            existing_enabled, 
                            key_prefix,
                            existing_error
                        )
                        
                        if is_enabled and value is not None:
                            updated_constraints[constraint_name] = {
                                "value": value,
                                "enabled": True,
                                "shape": str(shape),
                                "class": str(class_uri),
                                "property": str(prop_uri),
                                "datatype": str(datatype) if datatype else None,
                                "error_message": error_message
                            }
                
                # Update session state
                if updated_constraints:
                    st.session_state.property_constraints[constraints_key] = updated_constraints
                elif constraints_key in st.session_state.property_constraints:
                    del st.session_state.property_constraints[constraints_key]
                
                st.markdown("---")


def display_constraints():
    """Display constraints editing interface for selected properties."""
    st.subheader("Constraints")

    if not st.session_state.property_graph_id:
        st.warning("No SHACL property graph loaded.")
        return

    if "class_property_map" not in st.session_state or not st.session_state.class_property_map:
        st.info("No properties selected. Please select properties in the 'Class and Property Menu' page.")
        return

    if "property_constraints" not in st.session_state or st.session_state.property_constraints is None:
        st.session_state.property_constraints = {}

    combined_graph = get_cached_graph(st.session_state.combined_graph_id) if st.session_state.combined_graph_id else Graph()
    property_graph = get_cached_graph(st.session_state.property_graph_id)
    existing_shacl = get_cached_graph(st.session_state.existing_shacl_id) if st.session_state.existing_shacl_id else Graph()
    
    class_property_map = st.session_state.class_property_map
    
    # Extract metadata once for all labels
    metadata = _extract_class_metadata(combined_graph)
    
    # Display summary
    total_classes = len(class_property_map)
    total_properties = sum(len(props) for props in class_property_map.values())
    st.caption(f"📊 Editing constraints for {total_properties} properties across {total_classes} classes")

    # Render each class as a fragment for fast interactions
    for class_uri, properties in class_property_map.items():
        _constraints_class_fragment(
            class_uri, 
            properties, 
            metadata['labels'],
            property_graph,
            existing_shacl
        )

def get_label(uri, graph):
    label = graph.value(URIRef(uri), RDFS.label)
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
            content = st_ace(
                value=shacl_content,
                language="turtle",
                theme="monokai",
                readonly=True,
                height=400,
                
                key="st-ace-editor",  # Assign a consistent key to target the editor
            )

            # Create a download button for the content
            st.download_button(
                label="Download Code",
                data=content,
                file_name="SHACL.ttl",
                mime="text/turtle"
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

    combined_graph = get_cached_graph(st.session_state.combined_graph_id) if st.session_state.combined_graph_id else Graph()

    g1 = Graph()
    # Dynamically bind all namespaces from the `namespaces` dictionary
    for prefix, namespace in namespaces.items():
        g1.namespace_manager.bind(prefix, namespace)  # Bind namespaces to the SHACL graph

    shacl_namespace = namespaces.get("ceds", Namespace("http://ceds.ed.gov/terms#"))  # Default to CEDS namespace
    for class_uri, properties in st.session_state.class_property_map.items():
        if properties:  # Only include classes with properties
            create_node_shape(g1, combined_graph, class_uri, {}, shacl_namespace)
            create_property_shapes(g1, combined_graph, class_uri, properties, st.session_state.class_property_map, shacl_namespace)

    # Remove default constraints present in the loaded property graph (g2)
    # Match property shapes by sh:path and drop only constraints that equal defaults
    property_graph_id = st.session_state.get('property_graph_id')
    if property_graph_id:
        g2 = get_cached_graph(property_graph_id)
        if len(g2) == 0:
            g2 = None
    else:
        g2 = None
    
    if g2 is not None:
        def list_values(graph, list_node):
            try:
                return [v for v in Collection(graph, list_node)]
            except Exception:
                return []

        for s1 in list(g1.subjects(RDF.type, SH.PropertyShape)):
            path_p = g1.value(s1, SH.path)
            if path_p is None:
                continue

            # For each default property shape with the same path
            default_shapes = list(g2.subjects(SH.path, path_p))
            if not default_shapes:
                continue

            # Build a quick lookup of defaults per predicate -> list of values for any default shape
            defaults_by_pred = {}
            for s2 in default_shapes:
                for p2, o2 in g2.predicate_objects(s2):
                    if p2 in (RDF.type, SH.path):
                        continue
                    defaults_by_pred.setdefault(p2, []).append(o2)

            # Compare constraints on s1 to defaults; if equal to any default, remove from g1
            for p1, o1 in list(g1.predicate_objects(s1)):
                if p1 in (RDF.type, SH.path):
                    continue

                candidates = defaults_by_pred.get(p1, [])
                if not candidates:
                    continue

                def equals(o_left, o_right):
                    # Handle list-valued constraints
                    if p1 in (SH['in'], SH.languageIn):
                        left_vals = set(list_values(g1, o_left)) if isinstance(o_left, BNode) else {o_left}
                        right_vals = set(list_values(g2, o_right)) if isinstance(o_right, BNode) else {o_right}
                        # Compare lexical string forms for safety
                        return {str(v) for v in left_vals} == {str(v) for v in right_vals}
                    # Compare as URIs or literals by lexical form
                    try:
                        return (str(o_left) == str(o_right))
                    except Exception:
                        return False

                if any(equals(o1, o2) for o2 in candidates):
                    g1.remove((s1, p1, o1))

        # Also prune NodeShape-level defaults by matching on sh:targetClass
        for ns1 in list(g1.subjects(RDF.type, SH.NodeShape)):
            target_cls = g1.value(ns1, SH.targetClass)
            if target_cls is None:
                continue

            default_nodes = list(g2.subjects(SH.targetClass, target_cls))
            if not default_nodes:
                continue

            defaults_by_pred = {}
            for ns2 in default_nodes:
                for p2, o2 in g2.predicate_objects(ns2):
                    if p2 in (RDF.type, SH.targetClass):
                        continue
                    defaults_by_pred.setdefault(p2, []).append(o2)

            for p1, o1 in list(g1.predicate_objects(ns1)):
                if p1 in (RDF.type, SH.targetClass):
                    continue

                candidates = defaults_by_pred.get(p1, [])
                if not candidates:
                    continue

                def equals_node(o_left, o_right, pred):
                    if pred in (SH['in'], SH.languageIn):
                        left_vals = set(list_values(g1, o_left)) if isinstance(o_left, BNode) else {o_left}
                        right_vals = set(list_values(g2, o_right)) if isinstance(o_right, BNode) else {o_right}
                        return {str(v) for v in left_vals} == {str(v) for v in right_vals}
                    return str(o_left) == str(o_right)

                if any(equals_node(o1, o2, p1) for o2 in candidates):
                    g1.remove((ns1, p1, o1))

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

