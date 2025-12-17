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

# Standard namespaces to skip when extracting (RDFLib adds these automatically)
STANDARD_NS_PREFIXES = {'xml', 'rdf', 'rdfs', 'xsd'}


def sync_namespaces_from_graph(graph: Graph) -> dict:
    """Extract all custom namespaces from a graph and sync to global namespaces dict.
    
    Returns dict of {prefix: namespace_uri} that were added.
    """
    global namespaces
    added = {}
    
    for prefix, ns_uri in graph.namespace_manager.namespaces():
        # Skip standard/default namespaces
        if not prefix or prefix in STANDARD_NS_PREFIXES:
            continue
        
        ns_str = str(ns_uri)
        
        # Add to global namespaces if not already present
        if prefix not in namespaces:
            namespaces[prefix] = Namespace(ns_str)
            added[prefix] = ns_str
            logger.debug(f"Extracted namespace: {prefix} -> {ns_str}")
    
    if added:
        logger.info(f"Synced {len(added)} namespaces from graph: {list(added.keys())}")
    
    return added


# Cached graph parsing functions

def _parse_ontology_file(_file_content: bytes, format: str, file_name: str) -> Graph:
    """Parse an RDF file into a Graph. Underscore prefix prevents hashing."""
    graph = Graph()
    graph.parse(data=_file_content, format=format)
    logger.info(f"Parsed '{file_name}' with {len(graph)} triples")
    return graph


def _combine_graphs(_graph_list: list) -> Graph:
    """Combine multiple RDF graphs into a single graph.
    
    Automatically propagates all namespaces from source graphs.
    """
    combined = Graph()
    for graph in _graph_list:
        # Copy all namespaces from source graph
        for prefix, ns_uri in graph.namespace_manager.namespaces():
            if prefix:  # Skip default namespace
                combined.namespace_manager.bind(prefix, Namespace(str(ns_uri)))
        combined += graph
    logger.info(f"Combined {len(_graph_list)} graphs with {len(combined)} triples")
    return combined


# Graph storage functions - use session state for non-preloaded graphs

def _get_graph_cache() -> dict:
    """Return dictionary for storing graphs. Uses session state for session-scoped storage."""
    if "_graph_cache" not in st.session_state:
        st.session_state._graph_cache = {}
        logger.info("Initializing graph cache in session state")
    return st.session_state._graph_cache


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


# Preloaded data file paths
DATA_DIR = Path(__file__).parent.parent / "data"
PRELOAD_ONTOLOGY_FILE = DATA_DIR / "CEDS-Ontology.rdf"
PRELOAD_PROPERTY_FILE = DATA_DIR / "PropertyShapes.ttl"


@st.cache_resource(show_spinner=False)
def _load_preloaded_ontology() -> Optional[Graph]:
    """Load the preloaded CEDS ontology if available."""
    if PRELOAD_ONTOLOGY_FILE.exists():
        try:
            graph = Graph()
            graph.parse(str(PRELOAD_ONTOLOGY_FILE), format="xml")
            logger.info(f"Preloaded CEDS ontology with {len(graph)} triples")
            return graph
        except Exception as e:
            logger.error(f"Failed to load preloaded ontology: {e}")
    return None


@st.cache_resource(show_spinner=False)
def _load_preloaded_property_shapes() -> Optional[Graph]:
    """Load the preloaded property shapes if available."""
    if PRELOAD_PROPERTY_FILE.exists():
        try:
            graph = Graph()
            graph.parse(str(PRELOAD_PROPERTY_FILE), format="turtle")
            logger.info(f"Preloaded property shapes with {len(graph)} triples")
            return graph
        except Exception as e:
            logger.error(f"Failed to load preloaded property shapes: {e}")
    return None


def check_preloaded_files() -> dict:
    """Check which preloaded files are available."""
    return {
        "ontology": PRELOAD_ONTOLOGY_FILE.exists(),
        "property_shapes": PRELOAD_PROPERTY_FILE.exists(),
        "ontology_path": str(PRELOAD_ONTOLOGY_FILE),
        "property_shapes_path": str(PRELOAD_PROPERTY_FILE)
    }


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
        
        logger.debug(f"[SHACL GEN] Processing property {prop_uri}")
        logger.debug(f"[SHACL GEN] constraints_key: {constraints_key}")
        logger.debug(f"[SHACL GEN] Retrieved constraints from session state: {constraints}")
        logger.debug(f"[SHACL GEN] All property_constraints keys: {list(st.session_state.property_constraints.keys())}")
        
        # Check if constraints are truly custom by comparing with property graph defaults
        has_truly_custom_constraints = False
        custom_constraints_to_add = {}  # Store only the truly custom constraints
        
        if constraints:
            # Find the shape in the property graph for this property (if property_graph exists)
            property_shapes_in_graph = []
            if property_graph and len(property_graph) > 0:
                property_shapes_in_graph = list(property_graph.subjects(predicate=SH.path, object=URIRef(prop_uri)))
            
            # Process each constraint the user has set
            for constraint_name, constraint_data in constraints.items():
                if not constraint_data.get("enabled", False):
                    continue
                    
                shacl_predicate = getattr(SH, constraint_name, None)
                if not shacl_predicate:
                    continue
                    
                user_value = constraint_data["value"]
                is_custom = False
                
                # If no shapes exist in property graph, any user constraint is custom
                if not property_shapes_in_graph:
                    is_custom = True
                    logger.debug(f"Constraint {constraint_name}={user_value} is custom (no shape in property graph)")
                else:
                    # Compare with default values from property graph
                    for prop_graph_shape in property_shapes_in_graph:
                        default_value = property_graph.value(prop_graph_shape, shacl_predicate)
                        
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
                                if str(user_value) != str(default_python_value):
                                    is_custom = True
                            else:
                                if str(user_value) != str(default_python_value):
                                    is_custom = True
                        else:
                            # No default value exists in property graph, so user value is custom
                            is_custom = True
                        
                        # Only need to check one shape
                        break
                
                if is_custom:
                    has_truly_custom_constraints = True
                    custom_constraints_to_add[constraint_name] = constraint_data
                    logger.debug(f"[SHACL GEN] Adding custom constraint: {constraint_name}={user_value}")
                else:
                    logger.debug(f"[SHACL GEN] Skipping constraint {constraint_name}={user_value} (matches default or not custom)")
        
        logger.debug(f"[SHACL GEN] property_exists_in_shapes_file: {property_exists_in_shapes_file}")
        logger.debug(f"[SHACL GEN] has_truly_custom_constraints: {has_truly_custom_constraints}")
        logger.debug(f"[SHACL GEN] custom_constraints_to_add: {custom_constraints_to_add}")

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

            # Skip if range is a datatype (XSD namespace or typed as rdfs:Datatype)
            range_str = str(range_uri)
            is_datatype = (
                range_str.startswith(str(XSD)) or 
                (range_uri, RDF.type, RDFS.Datatype) in g
            )
            
            if not is_datatype:

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
        # Include additional_constraints check - if we have range-based constraints (like sh:in for option sets),
        # we need to create the shape definition even if property exists in shapes file
        needs_shape_definition = (
            not property_exists_in_shapes_file or 
            has_truly_custom_constraints or 
            len(additional_constraints) > 0
        )
        logger.debug(f"[SHACL GEN] needs_shape_definition: {needs_shape_definition} (property_exists={property_exists_in_shapes_file}, custom={has_truly_custom_constraints}, additional={len(additional_constraints)})")
        
        if needs_shape_definition:
            g1.add((prop_shape, RDF.type, SH.PropertyShape))
            g1.add((prop_shape, SH.path, URIRef(prop_uri)))
            logger.debug(f"[SHACL GEN] Created PropertyShape for {prop_uri}")
            
            # Add additional constraints from range processing
            for predicate, obj in additional_constraints:
                g1.add((prop_shape, predicate, obj))
                logger.debug(f"[SHACL GEN] Added range constraint: {predicate} = {obj}")
            
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
                            # Use decimal datatype to avoid scientific notation (e.g., 2e+00)
                            float_val = float(value)
                            # If it's a whole number, use int to get cleaner output
                            if float_val == int(float_val):
                                literal_value = Literal(int(float_val), datatype=XSD.decimal)
                            else:
                                literal_value = Literal(float_val, datatype=XSD.decimal)
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
    
    # Check for preloaded files and show status
    preload_status = check_preloaded_files()
    
    # Show loaded file status
    ontology_loaded = st.session_state.get("preloaded_ontology_loaded", False)
    property_loaded = st.session_state.get("preloaded_property_loaded", False)
    
    if ontology_loaded or property_loaded:
        st.markdown("**Preloaded Files:**")
        col1, col2 = st.columns(2)
        
        with col1:
            if ontology_loaded:
                combined_graph = get_cached_graph(st.session_state.combined_graph_id)
                st.success(f"✅ CEDS Ontology ({len(combined_graph):,} triples)")
            elif preload_status["ontology"]:
                st.warning("⚠️ CEDS Ontology available but not loaded")
            else:
                st.info("📁 Place CEDS-Ontology.rdf in data/ folder")
        
        with col2:
            if property_loaded:
                property_graph = get_cached_graph(st.session_state.property_graph_id)
                st.success(f"✅ Property Shapes ({len(property_graph):,} triples)")
            elif preload_status["property_shapes"]:
                st.warning("⚠️ Property Shapes available but not loaded")
            else:
                st.info("📁 Place PropertyShapes.ttl in data/ folder")
        
        st.markdown("---")
    
    # Extension ontology section as fragment
    _extension_ontology_fragment()
    
    # Existing SHACL import section as fragment
    _existing_shacl_fragment()


@st.fragment
def _extension_ontology_fragment():
    """Fragment for extension ontology file uploads - runs independently."""
    st.markdown("**Upload Extension Ontology Files:**")

    uploaded_ontology_files = st.file_uploader(
        "Upload Ontology Files",
        type=["ttl", "rdf", "xml"],
        accept_multiple_files=True
    )

    # Auto-merge when files are uploaded
    if uploaded_ontology_files:
        # Check for new files
        existing_file_ids = {f.file_id for f in st.session_state.file_list}
        new_files = [f for f in uploaded_ontology_files if f.file_id not in existing_file_ids]
        
        if new_files:
            # Add new files to list
            for file in new_files:
                st.session_state.file_list.append(file)
            
            # Auto-load and merge
            graph = load_ontologies(new_files)
            if len(graph) > 0:
                # Sync namespaces from the loaded graph
                sync_namespaces_from_graph(graph)
                
                # If we already have a preloaded graph, merge with it
                existing_graph = get_cached_graph(st.session_state.combined_graph_id) if st.session_state.get("combined_graph_id") else Graph()
                if len(existing_graph) > 0:
                    # Create a new combined graph that preserves all namespaces
                    merged_graph = Graph()
                    
                    # First copy namespaces from existing graph
                    for prefix, ns_uri in existing_graph.namespace_manager.namespaces():
                        if prefix:
                            merged_graph.namespace_manager.bind(prefix, Namespace(str(ns_uri)))
                    
                    # Then copy namespaces from new graph (may add new prefixes)
                    for prefix, ns_uri in graph.namespace_manager.namespaces():
                        if prefix:
                            merged_graph.namespace_manager.bind(prefix, Namespace(str(ns_uri)))
                    
                    # Add all triples from both graphs
                    for triple in existing_graph:
                        merged_graph.add(triple)
                    for triple in graph:
                        merged_graph.add(triple)
                    
                    graph = merged_graph
                    st.success(f"Merged extension ontology. Total: {len(graph):,} triples")
                
                # Store in session state (not cache) for easy refresh
                st.session_state.extension_graph = graph
                
                # Update combined_graph_id to point to merged graph in cache
                import hashlib
                graph_hash = hashlib.md5(graph.serialize(format='nt').encode()).hexdigest()[:16]
                graph_id = f"combined_{graph_hash}_{len(graph)}"
                store_graph(graph_id, graph)
                st.session_state.combined_graph_id = graph_id
                logger.info(f"Combined graph stored with ID: {graph_id}")

    # Show uploaded files list
    if st.session_state.file_list:
        st.markdown("**Loaded Extension Files:**")
        for file in st.session_state.file_list:
            st.text(f"📄 {file.name}")

@st.fragment
def _existing_shacl_fragment():
    """Fragment for existing SHACL import - runs independently."""
    st.subheader("Import Existing SHACL")

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
    """Load all files from session_state into a combined RDF graph using cached parsing.
    
    Namespaces are automatically extracted from each file - no manual input needed.
    """
    # Validate file list is not empty
    if not file_list:
        st.warning("No ontology files to load.")
        return Graph()

    parsed_graphs = []  # List of parsed Graph objects
    
    for file in file_list:
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

            # Auto-extract namespaces from the parsed graph
            extracted_ns = sync_namespaces_from_graph(temp_graph)
            
            # Store parsed graph for combining
            parsed_graphs.append(temp_graph)
            
            # Show success with extracted namespaces info
            ns_info = f" (namespaces: {', '.join(extracted_ns.keys())})" if extracted_ns else ""
            st.success(f"Ontology file '{file.name}' loaded successfully with {len(temp_graph)} triples{ns_info}.")

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
    
    # String and string-derived datatypes that support length/pattern constraints
    string_like_types = [
        XSD.string, XSD.normalizedString, XSD.token, XSD.language,
        XSD.Name, XSD.NCName, XSD.NMTOKEN, XSD.anyURI
    ]
    
    if datatype in string_like_types:
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
        # Determine if this should be integer or float based on step
        step = constraint_config.get("step", 1)
        is_integer = step == 1
        
        # Ensure current_value is a valid number with consistent type
        if current_value is not None:
            try:
                if is_integer:
                    current_value = int(float(current_value))
                else:
                    current_value = float(current_value)
            except (ValueError, TypeError):
                current_value = int(constraint_config.get("min", 0)) if is_integer else float(constraint_config.get("min", 0))
        else:
            current_value = int(constraint_config.get("min", 0)) if is_integer else float(constraint_config.get("min", 0))
        
        # Ensure min_value matches the type
        min_val = constraint_config.get("min", None)
        if min_val is not None:
            min_val = int(min_val) if is_integer else float(min_val)
            
        value = st.number_input(
            constraint_name,
            min_value=min_val,
            step=int(step) if is_integer else float(step),
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
                                  property_graph: Graph, existing_shacl: Graph, 
                                  combined_graph: Graph):
    """Fragment for constraint editing. Input changes only rerun this fragment."""
    class_label = labels.get(class_uri, class_uri)
    
    # Helper to get a friendly name for datatypes
    def get_datatype_name(dt):
        if dt is None:
            return "Unknown"
        dt_str = str(dt)
        if "#" in dt_str:
            return dt_str.split("#")[-1]
        return dt_str.split("/")[-1]
    
    with st.expander(f"Class: {class_label}", expanded=False):
        for prop_uri in properties:
            # Find PropertyShape(s) that have sh:path = this property
            shapes = list(property_graph.subjects(predicate=SH.path, object=URIRef(prop_uri)))
            
            # Skip property if any associated shape has sh:nodeKind sh:IRI (object property, not editable)
            skip_due_to_nodekind = any(
                property_graph.value(shape, SH.nodeKind) == SH.IRI
                for shape in shapes
            )
            if skip_due_to_nodekind:
                continue

            prop_label = labels.get(prop_uri, prop_uri)
            
            # Determine property source and get datatype
            datatype = None
            node_kind = None
            shape = None
            is_extension_property = False
            shape_properties = {}
            
            if shapes:
                # Property exists in PropertyShapes.ttl
                shape = shapes[0]
                datatype = property_graph.value(shape, SH.datatype)
                node_kind = property_graph.value(shape, SH.nodeKind)
                
                # Collect all shape properties for display
                for p, o in property_graph.predicate_objects(subject=shape):
                    if p != RDF.type:
                        shape_properties[str(p)] = o
            else:
                # Check existing SHACL
                shapes = list(existing_shacl.subjects(predicate=SH.path, object=URIRef(prop_uri)))
                if shapes:
                    shape = shapes[0]
                    datatype = existing_shacl.value(shape, SH.datatype)
                    node_kind = existing_shacl.value(shape, SH.nodeKind)
                    for p, o in existing_shacl.predicate_objects(subject=shape):
                        if p != RDF.type:
                            shape_properties[str(p)] = o
            
            # For extension properties without shapes, look up range from ontology
            if datatype is None and combined_graph:
                ranges = list(combined_graph.objects(URIRef(prop_uri), SDO.rangeIncludes))
                for r in ranges:
                    r_str = str(r)
                    # Check if it's an XSD datatype
                    if r_str.startswith(str(XSD)):
                        datatype = r
                        is_extension_property = True
                        break
            
            # Skip if this is an object property (range is a class, not datatype)
            if datatype is None and not is_extension_property:
                # Check if range points to a class (object property)
                if combined_graph:
                    ranges = list(combined_graph.objects(URIRef(prop_uri), SDO.rangeIncludes))
                    for r in ranges:
                        # If range is a class (not XSD), skip this property
                        if not str(r).startswith(str(XSD)):
                            skip_due_to_nodekind = True
                            break
            
            if skip_due_to_nodekind:
                continue
            
            # Determine source based on property URI namespace, not PropertyShapes presence
            is_ceds_property = str(prop_uri).startswith("http://ceds.ed.gov/")
            has_property_shape = shape is not None and not is_extension_property
            
            # === UI RENDERING ===
            st.markdown(f"#### {prop_label}")
            
            # Property info card
            with st.container():
                # Create info columns
                info_col1, info_col2 = st.columns(2)
                
                with info_col1:
                    st.markdown("**Property Details**")
                    st.caption(f"🔗 URI: `{prop_uri}`")
                    
                    if is_ceds_property:
                        st.caption("📦 Source: CEDS Ontology")
                        if not has_property_shape:
                            st.warning("⚠️ Missing from PropertyShapes.ttl")
                    else:
                        st.caption("📦 Source: Extension Ontology")
                
                with info_col2:
                    st.markdown("**Data Type**")
                    if datatype:
                        dt_name = get_datatype_name(datatype)
                        # Color code by datatype category
                        if "string" in dt_name.lower() or "token" in dt_name.lower() or "uri" in dt_name.lower():
                            st.success(f"📝 {dt_name}")
                        elif "int" in dt_name.lower() or "decimal" in dt_name.lower() or "float" in dt_name.lower() or "double" in dt_name.lower():
                            st.info(f"🔢 {dt_name}")
                        elif "date" in dt_name.lower() or "time" in dt_name.lower():
                            st.warning(f"📅 {dt_name}")
                        elif "bool" in dt_name.lower():
                            st.info(f"✓ {dt_name}")
                        else:
                            st.info(f"📋 {dt_name}")
                    else:
                        st.caption("⚠️ No datatype detected")
                    
                    if node_kind:
                        nk_name = get_datatype_name(node_kind)
                        st.caption(f"Node Kind: {nk_name}")
            
            # Show existing shape properties in a toggleable section (can't use expander inside expander)
            if shape_properties:
                show_props_key = f"show_props_{class_uri}_{prop_uri}"
                if show_props_key not in st.session_state:
                    st.session_state[show_props_key] = False
                
                if st.checkbox("Show current shape properties", key=show_props_key, value=False):
                    props_text = ""
                    for p_uri, o in shape_properties.items():
                        p_name = p_uri.split("#")[-1] if "#" in p_uri else p_uri.split("/")[-1]
                        o_label = labels.get(str(o), str(o))
                        props_text += f"• {p_name}: {o_label}\n"
                    st.code(props_text, language=None)
            
            # Editable predicates
            editable_predicates = {
                SH.minCount, SH.maxCount, SH.minLength, SH.maxLength, SH.pattern,
                SH.minInclusive, SH.maxInclusive, SH.minExclusive, SH.maxExclusive,
                SH.nodeKind, SH.languageIn, SH.uniqueLang
            }
            
            # Get available constraints for this datatype
            available_constraints = get_available_constraints_for_datatype(datatype)
            
            # Load existing constraint values
            constraints_key = f"{class_uri}::{prop_uri}"
            existing_constraints = st.session_state.property_constraints.get(constraints_key, {})
            
            # Check for constraints in existing SHACL
            property_shapes = list(existing_shacl.subjects(RDF.type, SH.PropertyShape))
            property_shapes += list(property_graph.subjects(RDF.type, SH.PropertyShape))
            
            for ps in property_shapes:
                path = existing_shacl.value(ps, SH.path)
                if path is None:
                    path = property_graph.value(ps, SH.path)

                if path == URIRef(prop_uri):
                    shape_message = existing_shacl.value(ps, SH.message)
                    shape_message_str = str(shape_message) if shape_message else ""
                    
                    for p, o in existing_shacl.predicate_objects(ps):
                        if p in editable_predicates:
                            constraint_name = str(p).split('#')[-1]
                            if constraint_name in available_constraints:
                                existing_constraints[constraint_name] = {
                                    "value": convert_rdf_literal_to_python(o),
                                    "enabled": True,
                                    "shape": str(ps),
                                    "class": str(class_uri),
                                    "property": str(prop_uri),
                                    "datatype": str(datatype) if datatype else None,
                                    "error_message": shape_message_str
                                }

            # Load current values from the property graph
            current_values = {}
            if shape:
                for constraint_name in available_constraints.keys():
                    shacl_predicate = getattr(SH, constraint_name, None)
                    if shacl_predicate:
                        value = property_graph.value(shape, shacl_predicate)
                        if value is not None:
                            current_values[constraint_name] = convert_rdf_literal_to_python(value)
            
            # Constraint editing section
            st.markdown("**Edit Constraints**")
            
            if not available_constraints:
                st.info("No editable constraints available for this datatype.")
            else:
                # Create two columns for better layout
                col1, col2 = st.columns(2)
                
                updated_constraints = {}
                constraint_items = list(available_constraints.items())
                mid_point = (len(constraint_items) + 1) // 2
                
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
                                "shape": str(shape) if shape else f"{prop_uri}Shape",
                                "class": str(class_uri),
                                "property": str(prop_uri),
                                "datatype": str(datatype) if datatype else None,
                                "error_message": error_message
                            }
            
                # Update session state
                if updated_constraints:
                    st.session_state.property_constraints[constraints_key] = updated_constraints
                    logger.debug(f"[CONSTRAINTS UI] Saved constraints for {constraints_key}: {updated_constraints}")
                elif constraints_key in st.session_state.property_constraints:
                    del st.session_state.property_constraints[constraints_key]
                    logger.debug(f"[CONSTRAINTS UI] Deleted constraints for {constraints_key}")
            
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
            existing_shacl,
            combined_graph
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
    global namespaces
    
    if not st.session_state.class_property_map:
        st.warning("No class-property mappings selected.")
        return None

    combined_graph = get_cached_graph(st.session_state.combined_graph_id) if st.session_state.combined_graph_id else Graph()

    # Restore namespaces from combined_graph if module-level dict is empty (e.g., after hot reload)
    if not namespaces and combined_graph:
        for prefix, ns_uri in combined_graph.namespace_manager.namespaces():
            if prefix:  # Skip default namespace
                namespaces[prefix] = Namespace(str(ns_uri))
        logger.info(f"Restored {len(namespaces)} namespaces from combined_graph after hot reload")

    g1 = Graph()
    
    # First, bind all namespaces from the combined_graph (source ontology)
    # This ensures URIs like cepi:NI001571100001 in sh:in lists serialize with prefixes
    if combined_graph:
        for prefix, ns_uri in combined_graph.namespace_manager.namespaces():
            if prefix:  # Skip default namespace
                g1.namespace_manager.bind(prefix, Namespace(str(ns_uri)))
    
    # Then bind any additional namespaces from the global dict (may override/add)
    for prefix, namespace in namespaces.items():
        g1.namespace_manager.bind(prefix, namespace)

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

    # Serialize the SHACL graph with NodeShapes first, then PropertyShapes
    # Pass combined_graph so we can copy its namespace bindings
    try:
        shacl_content = serialize_shacl_sorted(g1, combined_graph)
        st.success("SHACL shapes generated successfully!")
        return shacl_content
    except Exception as e:
        st.error(f"Failed to generate SHACL: {e}")
        return None


def _collect_blank_nodes(graph: Graph, start_node, collected: set) -> None:
    """Iteratively collect all blank nodes reachable from a starting node.
    
    Uses a stack-based approach to avoid recursion depth issues with deep RDF lists.
    """
    stack = [start_node]
    visited = set()
    
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        
        for p, o in graph.predicate_objects(current):
            if isinstance(o, BNode) and o not in collected:
                collected.add(o)
                if o not in visited:
                    stack.append(o)


def serialize_shacl_sorted(graph: Graph, source_graph: Graph = None) -> str:
    """Serialize SHACL graph with NodeShapes first, then PropertyShapes.
    
    Args:
        graph: The SHACL graph to serialize
        source_graph: Optional source ontology graph to copy namespace bindings from
    """
    # Copy namespace bindings from source_graph FIRST
    # This ensures all prefixes used in URIs (like cepi:) are properly declared
    if source_graph:
        for prefix, ns_uri in source_graph.namespace_manager.namespaces():
            if prefix:  # Skip default namespace
                graph.namespace_manager.bind(prefix, Namespace(str(ns_uri)))
    
    # Get all NodeShapes and PropertyShapes
    node_shapes = set(graph.subjects(RDF.type, SH.NodeShape))
    property_shapes = set(graph.subjects(RDF.type, SH.PropertyShape))
    
    # Collect all blank nodes associated with each shape type
    node_shape_bnodes = set()
    for ns in node_shapes:
        _collect_blank_nodes(graph, ns, node_shape_bnodes)
    
    prop_shape_bnodes = set()
    for ps in property_shapes:
        _collect_blank_nodes(graph, ps, prop_shape_bnodes)
    
    # Create separate graphs
    node_graph = Graph()
    prop_graph = Graph()
    
    # Copy namespace bindings to all sub-graphs
    for prefix, namespace in graph.namespaces():
        node_graph.namespace_manager.bind(prefix, namespace)
        prop_graph.namespace_manager.bind(prefix, namespace)
    
    # Separate triples into NodeShape and PropertyShape graphs
    for s, p, o in graph:
        if s in node_shapes or s in node_shape_bnodes:
            node_graph.add((s, p, o))
        elif s in property_shapes or s in prop_shape_bnodes:
            prop_graph.add((s, p, o))
        elif isinstance(s, BNode):
            # Orphan blank node - try to determine where it belongs
            # Check if it's referenced by any property shape
            is_prop_bnode = any(
                (ps, pred, s) in graph 
                for ps in property_shapes 
                for pred in graph.predicates(ps)
            )
            if is_prop_bnode:
                prop_graph.add((s, p, o))
            else:
                node_graph.add((s, p, o))
        else:
            # Other triples go to node graph
            node_graph.add((s, p, o))
    
    # Serialize each graph
    node_ttl = node_graph.serialize(format="turtle")
    prop_ttl = prop_graph.serialize(format="turtle")
    
    # Merge prefix declarations from both serializations since RDFLib only emits
    # @prefix for namespaces actually used in each graph's triples
    # Merge prefix declarations from both serializations
    all_prefixes = {}
    for line in node_ttl.split('\n'):
        if line.startswith('@prefix'):
            # Extract prefix name
            parts = line.split()
            if len(parts) >= 2:
                prefix_name = parts[1].rstrip(':')
                all_prefixes[prefix_name] = line
    for line in prop_ttl.split('\n'):
        if line.startswith('@prefix'):
            parts = line.split()
            if len(parts) >= 2:
                prefix_name = parts[1].rstrip(':')
                if prefix_name not in all_prefixes:
                    all_prefixes[prefix_name] = line
    
    # Build combined output with merged prefixes
    prefix_lines = sorted(all_prefixes.values())
    
    # Extract triples (non-prefix lines) from node_graph
    node_lines = node_ttl.split('\n')
    node_triples = []
    for line in node_lines:
        if not line.startswith('@prefix'):
            node_triples.append(line)
    
    # Extract triples from prop_graph  
    prop_lines = prop_ttl.split('\n')
    prop_triples = []
    for line in prop_lines:
        if not line.startswith('@prefix'):
            prop_triples.append(line)
    
    # Combine: prefixes + node triples + prop triples
    result_parts = prefix_lines + [''] + node_triples
    if prop_triples:
        # Add separator and prop triples
        result_parts.append('')
        result_parts.extend(prop_triples)
    
    return '\n'.join(result_parts).strip() + '\n'


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

