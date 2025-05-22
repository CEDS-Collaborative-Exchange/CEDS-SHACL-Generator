from rdflib import Graph, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, SH, XSD, SDO, SKOS
from rdflib.collection import Collection
import logging
import csv
from pathlib import Path
from io import BytesIO

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
    notation = next(g.objects(URIRef(class_uri), SKOS.notation))

    node_title = URIRef(f"{shacl_namespace}{notation}Shape")
    g1.add((node_title, RDF.type, SH.NodeShape))
    g1.add((node_title, SH.targetClass, URIRef(class_uri)))

    if class_uri in parent_classes:
        g1.add((node_title, SH.closed, Literal(True, datatype=XSD.boolean)))

    ignored_props_list = [RDF.type, URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#id"), RDF.value, RDFS.label]
    ignored_list_node = BNode()
    Collection(g1, ignored_list_node, ignored_props_list)

    g1.add((node_title, SH.ignoredProperties, ignored_list_node))

def create_property_shapes(g1, g, class_uri, property_uris, class_property_map, shacl_namespace):
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

        for prefix, uri in g.namespaces():
            if str(prop_uri).startswith(str(uri)):
                prop_namespace = uri
                break
        else:
            prop_namespace = str(prop_uri).rsplit("#", 1)[0] + "#"

        prop_shape = URIRef(f"{prop_namespace}{prop_notation}Shape")

        # Get all of the RDFS classes in the graph to check if the range is a CEDS base class and not an option set
        classes = g.subjects(RDF.type, RDFS.Class)
        for range_uri in ranges:
            # Add the property shape to the class node shape
            g1.add((class_node_title, SH.property, prop_shape))

            # Check if the range is a class and not a datatype
            if "#C" in str(range_uri):
                option_set = list(g.subjects(RDF.type, URIRef(range_uri)))
                if len(option_set) > 0:
                    if any(not str(s).startswith("http://ceds.ed.gov/terms#") for s in option_set):
                        option_set_node = BNode()
                        Collection(g1, option_set_node, option_set)
                        g1.add((prop_shape, SH["in"], option_set_node))

                elif range_uri in classes:
                    g1.add((prop_shape, RDF.type, SH.PropertyShape))
                    g1.add((prop_shape, SH.path, URIRef(prop_uri)))

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

                    g1.add((prop_shape, SH["class"], URIRef(range_uri)))
                    g1.add((prop_shape, SH["node"], range_shape))

                    if str(range_uri) not in class_property_map:
                        g1.add((prop_shape, SH.nodeKind, SH.IRI))

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
        g1.namespace_manager.bind(prefix, uri, override=True)
    g1.namespace_manager.bind("sh", SH, override=True)
    g1.namespace_manager.bind("rdf", RDF, override=True)
    g1.namespace_manager.bind("xsd", XSD, override=True)
    g1.namespace_manager.bind("schema", SDO, override=True)
    logger.info("SHACL graph initialized.")

    return g, g1
