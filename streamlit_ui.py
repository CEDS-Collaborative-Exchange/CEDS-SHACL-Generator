import streamlit as st
import sys
from pathlib import Path

# Add the parent directory to sys.path
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
from rdflib import Namespace, Graph
from pyvis.network import Network
from io import BytesIO
import shutil

logger = setup_logging()

def visualize_shacl(output_data):
    """Generate a hierarchical visualization of the SHACL shapes."""
    logger.debug("Parsing SHACL output data")
    g = Graph()
    try:
        g.parse(data=output_data.getvalue(), format="turtle")
    except Exception as e:
        logger.error(f"Failed to parse SHACL output data: {e}")
        raise

    net = Network(height="750px", width="100%", directed=True)
    net.set_options("""
    {
      "layout": {
        "hierarchical": {
          "enabled": true,
          "direction": "UD",
          "sortMethod": "directed"
        }
      },
      "physics": {
        "hierarchicalRepulsion": {
          "centralGravity": 0.0,
          "springLength": 100,
          "springConstant": 0.01,
          "nodeDistance": 120,
          "damping": 0.09
        }
      },
      "nodes": {
        "shape": "box"
      },
      "edges": {
        "arrows": {
          "to": {
            "enabled": true
          }
        }
      }
    }
    """)

    for s, p, o in g:
        logger.debug(f"Adding edge: {s} -> {o} [label: {p}]")
        net.add_node(str(s), label=str(s), title=str(s), shape="box", color="#97C2FC")
        net.add_node(str(o), label=str(o), title=str(o), shape="box", color="#FFCC00")
        net.add_edge(str(s), str(o), title=str(p))

    net.save_graph("shacl_visualization.html")
    logger.debug("SHACL visualization saved as shacl_visualization.html")
    return "shacl_visualization.html"

def get_rdf_format(file_name):
    """Determine the RDF format based on the file extension."""
    extension = Path(file_name).suffix.lower()
    if extension in [".ttl"]:
        return "turtle"
    elif extension in [".rdf", ".xml"]:
        return "xml"
    else:
        raise ValueError(f"Unsupported file extension: {extension}")

def main():
    st.title("CEDS SHACL Generator")
    st.write("Generate SHACL shapes from CEDS Ontology and extension files.")

    # File inputs
    ceds_file = st.file_uploader("Upload CEDS Ontology file", type=["ttl", "rdf", "xml"])
    extension_file = st.file_uploader("Upload Extension Ontology file (optional)", type=["ttl", "rdf", "xml"])
    filter_file = st.file_uploader("Upload Filter IDs file (TXT)", type=["txt"])

    # Namespace inputs
    shacl_namespace = st.text_input("Enter SHACL namespace", "http://ceds.ed.gov/terms#")
    shacl_namespace_abbreviation = st.text_input("Enter SHACL namespace abbreviation", "ceds")

    # Run button
    if st.button("Generate SHACL"):
        if not ceds_file or not filter_file:
            st.error("Please upload both the CEDS Ontology file and the Filter IDs file.")
            return

        # Read files into memory
        ceds_data = BytesIO(ceds_file.read())
        extension_data = BytesIO(extension_file.read()) if extension_file else None
        filter_data = BytesIO(filter_file.read())

        # Determine RDF formats
        try:
            ceds_format = get_rdf_format(ceds_file.name)
            extension_format = get_rdf_format(extension_file.name) if extension_file else None
        except ValueError as e:
            st.error(str(e))
            return

        # Set up namespaces
        namespaces["ceds"] = Namespace("http://ceds.ed.gov/terms#")
        if shacl_namespace and shacl_namespace_abbreviation:
            namespaces[shacl_namespace_abbreviation] = Namespace(shacl_namespace)

        # Run the SHACL generation process
        try:
            logger.info("Initializing graphs...")
            g = Graph()
            g1 = Graph()
            g.parse(data=ceds_data.getvalue(), format=ceds_format)
            if extension_data:
                g.parse(data=extension_data.getvalue(), format=extension_format)
            logger.info("Graphs initialized successfully.")

            logger.info("Reading filter file...")
            class_property_map = get_filter_class_ids_from_file(filter_data)
            if not class_property_map:
                logger.warning("No class-property mappings found. Exiting.")
                st.warning("No class-property mappings found. Exiting.")
                return

            logger.info("Generating SHACL shapes...")
            parent_classes = get_parent_classes(g, class_property_map)
            for class_uri, property_uris in class_property_map.items():
                create_node_shape(g1, g, class_uri, parent_classes, shacl_namespace)
                create_property_shapes(g1, g, class_uri, property_uris, class_property_map, shacl_namespace)

            # Serialize the output
            output_data = BytesIO()
            g1.serialize(destination=output_data, format="turtle")
            output_data.seek(0)
            st.success("SHACL generation complete!")

            # Add visualization
            logger.info("Generating SHACL visualization...")
            visualization_file = visualize_shacl(output_data)
            st.write("SHACL Visualization:")
            st.components.v1.html(open(visualization_file, "r").read(), height=800)

            # Add download button
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
