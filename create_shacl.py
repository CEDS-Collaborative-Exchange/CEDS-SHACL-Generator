import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import csv
from rdflib import Graph, Namespace
from utils.SHACL import (
    get_parent_classes,
    create_node_shape,
    create_property_shapes,
    initialize_graphs,
    get_filter_class_ids_from_file,
    serialize_graph,
    namespaces,
)
from utils.logging_config import setup_logging

logger = setup_logging()

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

def main():
    logger.info("Starting script")
    ceds_path = input("Enter full path to CEDS Ontology: ").strip()
    extension_path = input("Enter full path to an extension Ontology (optional): ").strip() or None
    filter_file = input("Enter full path to filter ids: ").strip()
    shacl_namespace = input("Enter extension SHACL namespace (or press Enter to skip): ").strip() or "http://ceds.ed.gov/terms#"
    shacl_namespace_abbreviation = input("Enter extension SHACL namespace abbreviation (or press Enter to skip): ").strip() or "ceds"

    namespaces["ceds"] = Namespace("http://ceds.ed.gov/terms#")
    if shacl_namespace and shacl_namespace_abbreviation:
        namespaces[shacl_namespace_abbreviation] = Namespace(shacl_namespace)

    g = Graph()
    g1 = Graph()
    g.parse(ceds_path, format=rdflib.util.guess_format(ceds_path))
    if extension_path:
        g.parse(extension_path, format=rdflib.util.guess_format(extension_path))

    class_property_map = get_filter_class_ids_from_file(filter_file)
    if not class_property_map:
        logger.warning("No class-property mappings found. Exiting.")
        return

    parent_classes = get_parent_classes(g, class_property_map)
    for class_uri, property_uris in class_property_map.items():
        create_node_shape(g1, g, class_uri, parent_classes, shacl_namespace)
        create_property_shapes(g1, g, class_uri, property_uris, class_property_map, shacl_namespace)

    output_file = Path("Filtered_SHACL.ttl")
    g1.serialize(destination=output_file, format="turtle")
    logger.info(f"SHACL generation complete. Output saved to {output_file}")

if __name__ == "__main__":
    main()
