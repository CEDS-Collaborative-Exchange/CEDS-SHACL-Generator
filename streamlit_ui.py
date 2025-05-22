import streamlit as st
from pathlib import Path
from create_shacl import (
    initialize_graphs,
    get_filter_class_ids_from_file,
    get_parent_classes,
    create_node_shape,
    create_property_shapes,
    serialize_graph,
    destroy_logger,
    namespaces,
)
from rdflib import Namespace, Graph
from pyvis.network import Network
from logging_config import setup_logging

logger = setup_logging()

def visualize_shacl(output_file):
    """Generate a hierarchical visualization of the SHACL shapes."""
    logger.debug(f"Parsing SHACL output file: {output_file}")
    g = Graph()
    try:
        g.parse(output_file, format="turtle")
    except Exception as e:
        logger.error(f"Failed to parse SHACL output file: {e}")
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

def main():
    st.title("CEDS SHACL Generator")
    st.write("Generate SHACL shapes from CEDS Ontology and extension files.")

    # File inputs
    ceds_path = st.file_uploader("Upload CEDS Ontology file", type=["ttl", "rdf", "xml"])
    extension_path = st.file_uploader("Upload Extension Ontology file (optional)", type=["ttl", "rdf", "xml"])
    filter_file = st.file_uploader("Upload Filter IDs file (TXT)", type=["txt"])

    # Namespace inputs
    shacl_namespace = st.text_input("Enter SHACL namespace", "http://ceds.ed.gov/terms#")
    shacl_namespace_abbreviation = st.text_input("Enter SHACL namespace abbreviation", "ceds")

    # Run button
    if st.button("Generate SHACL"):
        if not ceds_path or not filter_file:
            st.error("Please upload both the CEDS Ontology file and the Filter IDs file.")
            return

        # Determine file extensions based on uploaded file types
        ceds_extension = Path(ceds_path.name).suffix
        extension_extension = Path(extension_path.name).suffix if extension_path else None

        # Save uploaded files to temporary paths with appropriate extensions
        ceds_temp_path = Path(f"ceds_temp{ceds_extension}")
        extension_temp_path = Path(f"extension_temp{extension_extension}") if extension_path else None
        filter_temp_path = Path("filter_temp.txt")

        with open(ceds_temp_path, "wb") as f:
            ceds_content = ceds_path.read()
            logger.debug(f"Saving CEDS Ontology file to {ceds_temp_path}")
            f.write(ceds_content)

        if extension_path:
            with open(extension_temp_path, "wb") as f:
                extension_content = extension_path.read()
                logger.debug(f"Saving Extension Ontology file to {extension_temp_path}")
                f.write(extension_content)

        with open(filter_temp_path, "wb") as f:
            filter_content = filter_file.read()
            logger.debug(f"Saving Filter file to {filter_temp_path}")
            f.write(filter_content)

        # Set up namespaces
        namespaces["ceds"] = Namespace("http://ceds.ed.gov/terms#")
        if shacl_namespace and shacl_namespace_abbreviation:
            namespaces[shacl_namespace_abbreviation] = Namespace(shacl_namespace)

        # Run the SHACL generation process
        try:
            logger.info("Initializing graphs...")
            g, g1 = initialize_graphs(ceds_temp_path, extension_temp_path)
            logger.info("Graphs initialized successfully.")

            logger.info("Reading filter file...")
            class_property_map = get_filter_class_ids_from_file(filter_temp_path)
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
            output_file = Path("Filtered_SHACL.ttl")
            logger.info(f"Serializing SHACL shapes to {output_file}")
            serialize_graph(g, g1)
            st.success("SHACL generation complete!")

            # Add visualization
            logger.info("Generating SHACL visualization...")
            visualization_file = visualize_shacl(output_file)
            st.write("SHACL Visualization:")
            st.components.v1.html(open(visualization_file, "r").read(), height=800)

            # Add download button
            st.download_button(
                label="Download SHACL File",
                data=output_file.read_text(),
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
