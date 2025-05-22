from pathlib import Path
import csv
import rdflib
from rdflib import Graph, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, SH, XSD, SDO, SKOS
from rdflib.collection import Collection
from logging_config import setup_logging

logger = setup_logging()

namespaces = {}

def destroy_logger():
    global logger
    while logger.hasHandlers():
        handler = logger.handlers[0] if logger.handlers else None
        if handler:
            handler.close()
            logger.removeHandler(handler)

def get_namespace(prefix):
    return namespaces.get(prefix, Namespace(f"http://unknown.org/{prefix}#"))

def initialize_graphs(ceds_path, extension_path):
    logger.info("g initializing")
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

    logger.info("g initialized")

    logger.info("g1 initializing")
    g1 = Graph()
    for prefix, uri in namespaces.items():
        g1.namespace_manager.bind(prefix, uri, override=True)
    g1.namespace_manager.bind("sh", SH, override=True)
    g1.namespace_manager.bind("rdf", RDF, override=True)
    g1.namespace_manager.bind("xsd", XSD, override=True)
    g1.namespace_manager.bind("schema", SDO, override=True)
    logger.info("g1 initialized")

    return g, g1

def get_filter_class_ids_from_file(file_path):
    class_property_map = {}
    try:
        with open(file_path, "r", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 2:
                    class_id_raw, property_id_raw = row[0].strip(), row[1].strip()
                    class_prefix, class_id = class_id_raw.split(":") if ":" in class_id_raw else ("CEDS", class_id_raw)
                    property_prefix, property_id = property_id_raw.split(":") if ":" in property_id_raw else ("CEDS", property_id_raw)
                    class_ns = get_namespace(class_prefix)
                    property_ns = get_namespace(property_prefix)
                    class_uri = f"{class_ns}{class_id}"
                    property_uri = f"{property_ns}{property_id}"
                    if class_uri not in class_property_map:
                        class_property_map[class_uri] = set()
                    class_property_map[class_uri].add(property_uri)
        logger.info("class Property map: %s", class_property_map)
        return class_property_map
    except Exception as e:
        logger.exception(f"Failed to read filter file: {e}")
        return {}

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
            # Add the proprety shape to the class node shape
            g1.add((class_node_title, SH.property, prop_shape))

            # Check if the range is a class and not a datatype.  No need to redefine the datatype in SHACL as they are defined in the common PropertyShapes.ttl file
            if "#C" in str(range_uri):

                # Check if the property is a option set by seeing if range_uri (concept scheme) is used as a class anywhere (concepts)
                option_set = list(g.subjects(RDF.type, URIRef(range_uri)))
                if len(option_set) > 0:
                    if any(not str(s).startswith("http://ceds.ed.gov/terms#") for s in option_set):
                        # If there is a CEPI option set value in the "cepi" namespace, override the property shape's "sh:in" constraint
                        option_set_node = BNode()
                        Collection(g1, option_set_node, option_set)

                        g1.add((prop_shape, SH["in"], option_set_node))


                # If the range is an RDFS Class, meaning it's a CEDS Class and NOT an option set, create a property shape for it
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

def get_label_or_comment(graph, uri):
    label = graph.value(uri, RDFS.label)
    if label is not None:
        return str(label)
    comment = graph.value(uri, RDFS.comment)
    if comment is not None:
        return str(comment)
    return None

def serialize_graph(g, g1):
    output_file = Path.cwd() / "Filtered_SHACL.ttl"
    try:
        output_file.write_text(g1.serialize(format="turtle"))
    except Exception as e:
        logger.exception(f"Failed to write SHACL output: {e}")

def prompt_for_file(prompt_text, required=True):
    while True:
        path = input(prompt_text).strip()
        if (path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'")):
            path = path[1:-1]
        if os.path.isfile(path):
            return path
        elif(not required):
            logger.warning(f"File not found: {path}\nPlease enter a valid file path.\n")

def main():
    logger.info("Starting script")
    ceds_path = prompt_for_file("Enter full path to CEDS Ontology: ")
    extension_path = prompt_for_file("Enter full path to an extension Ontology: ", required=False)
    filter_file = prompt_for_file("Enter full path to filter ids: ")
    shacl_namespace = input("Enter extension SHACL namespace (or press Enter to skip): ").strip()
    shacl_namespace_abbreviation = input("Enter extension SHACL namespace abbreviation (or press Enter to skip): ").strip()

    if shacl_namespace is None or shacl_namespace == "":
        shacl_namespace = "http://ceds.ed.gov/terms#"

    if shacl_namespace_abbreviation is None or shacl_namespace_abbreviation == "":
        shacl_namespace_abbreviation = "ceds"

    namespaces["ceds"] = Namespace("http://ceds.ed.gov/terms#")

    if shacl_namespace and shacl_namespace_abbreviation:
        namespaces[shacl_namespace_abbreviation] = Namespace(shacl_namespace)

    g, g1 = initialize_graphs(ceds_path, extension_path)
    class_property_map = get_filter_class_ids_from_file(filter_file)
    if not class_property_map:
        logger.info("No class-property mappings found. Exiting.")
        return

    parent_classes = get_parent_classes(g, class_property_map)
    for class_uri, property_uris in class_property_map.items():
        create_node_shape(g1, g, class_uri, parent_classes, "http://ceds.ed.gov/terms#")
        create_property_shapes(g1, g, class_uri, property_uris, class_property_map, "http://ceds.ed.gov/terms#")
        logger.info("Class %s has been created", class_uri)

    serialize_graph(g, g1)
    logger.info("SHACL generation complete")
    destroy_logger()

if __name__ == "__main__":
    main()
