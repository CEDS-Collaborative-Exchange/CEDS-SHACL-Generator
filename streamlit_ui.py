import streamlit as st
import sys
from pathlib import Path
from io import BytesIO
from rdflib import Namespace, Graph
from pyvis.network import Network

sys.path.append(str(Path(__file__).resolve().parent.parent))

from utils.SHACL import (
    initialize_graphs,
    get_parent_classes,
    create_node_shape,
    create_property_shapes,
    get_filter_class_ids_from_file,
    serialize_graph,
    namespaces,
)
from utils.logging_config import setup_logging, destroy_logger

logger = setup_logging()

def visualize_shacl(output_data):
    """Generate a hierarchical visualization of the SHACL shapes."""
    g = Graph()
    try:
        g.parse(data=output_data.getvalue(), format="turtle")
    except Exception as e:
        logger.error(f"Failed to parse SHACL output data: {e}")
        raise

    net = Network(height="750px", width="100%", directed=True)
    net.set_options("""
    {
      "layout": {"hierarchical": {"enabled": true, "direction": "UD"}},
      "nodes": {"shape": "box"},
      "edges": {"arrows": {"to": {"enabled": true}}}
    }
    """)

    for s, p, o in g:
        net.add_node(str(s), label=str(s), shape="box", color="#97C2FC")
        net.add_node(str(o), label=str(o), shape="box", color="#FFCC00")
        net.add_edge(str(s), str(o), title=str(p))

    net.save_graph("shacl_visualization.html")
    return "shacl_visualization.html"

def get_rdf_format(file_name):
    """Determine the RDF format based on the file extension."""
    formats = {".ttl": "turtle", ".rdf": "xml", ".xml": "xml"}
    return formats.get(Path(file_name).suffix.lower(), None)

def main():
    st.title("CEDS SHACL Generator")
    st.write("Generate SHACL shapes from CEDS Ontology and extension files.")

    ceds_file = st.file_uploader("Upload CEDS Ontology file", type=["ttl", "rdf", "xml"])
    extension_file = st.file_uploader("Upload Extension Ontology file (optional)", type=["ttl", "rdf", "xml"])
    filter_file = st.file_uploader("Upload Filter IDs file (TXT)", type=["txt"])

    shacl_namespace = st.text_input("Enter SHACL namespace", "http://ceds.ed.gov/terms#")
    shacl_namespace_abbreviation = st.text_input("Enter SHACL namespace abbreviation", "ceds")

    if st.button("Generate SHACL"):
        if not ceds_file or not filter_file:
            st.error("Please upload both the CEDS Ontology file and the Filter IDs file.")
            return

        try:
            ceds_format = get_rdf_format(ceds_file.name)
            extension_format = get_rdf_format(extension_file.name) if extension_file else None
            if not ceds_format:
                raise ValueError("Unsupported CEDS file format.")

            namespaces["ceds"] = Namespace("http://ceds.ed.gov/terms#")
            if shacl_namespace and shacl_namespace_abbreviation:
                namespaces[shacl_namespace_abbreviation] = Namespace(shacl_namespace)

            g, g1 = initialize_graphs(
                BytesIO(ceds_file.read()),
                BytesIO(extension_file.read()) if extension_file else None,
                ceds_format=ceds_format,
                extension_format=extension_format,
            )
            class_property_map = get_filter_class_ids_from_file(BytesIO(filter_file.read()))
            if not class_property_map:
                st.warning("No class-property mappings found. Exiting.")
                return

            parent_classes = get_parent_classes(g, class_property_map)
            for class_uri, property_uris in class_property_map.items():
                create_node_shape(g1, g, class_uri, parent_classes, shacl_namespace)
                create_property_shapes(g1, g, class_uri, property_uris, class_property_map, shacl_namespace)

            output_data = BytesIO()
            g1.serialize(destination=output_data, format="turtle")
            output_data.seek(0)
            st.success("SHACL generation complete!")

            visualization_file = visualize_shacl(output_data)
            st.components.v1.html(open(visualization_file, "r").read(), height=800)

            st.download_button(
                label="Download SHACL File",
                data=output_data.getvalue(),
                file_name="Filtered_SHACL.ttl",
                mime="text/turtle",
            )
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            st.error(f"An error occurred: {e}")
        finally:
            destroy_logger()

if __name__ == "__main__":
    main()
