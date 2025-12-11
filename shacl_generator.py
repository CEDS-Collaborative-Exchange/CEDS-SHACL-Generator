import streamlit as st
from rdflib import Graph
from utils.SHACL import (
    display_classes_and_properties,
    ontology_manager,
    show_SHACL,
    display_constraints,
    check_preloaded_files,
    _load_preloaded_ontology,
    _load_preloaded_property_shapes,
    store_graph,
    namespaces,
    sync_namespaces_from_graph
)
import hashlib


st.set_page_config(
    page_title="OM",
    page_icon="🌐",
    layout="wide"
)
import time

def load_preloaded_files():
    """Automatically load preloaded files on startup."""
    preload_status = check_preloaded_files()
    files_to_load = []
    
    # Check what needs to be loaded
    if preload_status["ontology"] and not st.session_state.preloaded_ontology_loaded:
        files_to_load.append("CEDS Ontology")
    if preload_status["property_shapes"] and not st.session_state.preloaded_property_loaded:
        files_to_load.append("Property Shapes")
    
    if not files_to_load:
        return False  # Nothing to load
    
    # Show loading screen with animation
    loading_container = st.empty()
    with loading_container.container():
        st.markdown("""
        <style>
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .loading-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 60px;
        }
        .loading-icon {
            font-size: 80px;
            animation: pulse 1.5s ease-in-out infinite;
        }
        .loading-title {
            font-size: 28px;
            font-weight: bold;
            margin-top: 20px;
            color: #1f77b4;
        }
        .loading-subtitle {
            font-size: 18px;
            color: #666;
            margin-top: 10px;
        }
        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60%, 100% { content: '...'; }
        }
        </style>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("""
            <div class="loading-container">
                <div class="loading-icon">🔮</div>
                <div class="loading-title">Initializing CEDS SHACL Generator</div>
            </div>
            """, unsafe_allow_html=True)
            
            status_text = st.empty()
        
        # Load ontology if available
        if preload_status["ontology"] and not st.session_state.preloaded_ontology_loaded:
            status_text.markdown("<p style='text-align: center; font-size: 16px; color: #888;'>📚 Loading CEDS Ontology (this may take a moment)...</p>", unsafe_allow_html=True)
            preloaded_graph = _load_preloaded_ontology()
            if preloaded_graph and len(preloaded_graph) > 0:
                graph_hash = hashlib.md5(preloaded_graph.serialize(format='nt').encode()).hexdigest()[:16]
                graph_id = f"combined_preload_{graph_hash}_{len(preloaded_graph)}"
                store_graph(graph_id, preloaded_graph)
                st.session_state.combined_graph_id = graph_id
                st.session_state.preloaded_ontology_loaded = True
                # Auto-extract namespaces from the loaded ontology
                sync_namespaces_from_graph(preloaded_graph)
        
        # Load property shapes if available
        if preload_status["property_shapes"] and not st.session_state.preloaded_property_loaded:
            status_text.markdown("<p style='text-align: center; font-size: 16px; color: #888;'>📋 Loading Property Shapes...</p>", unsafe_allow_html=True)
            preloaded_props = _load_preloaded_property_shapes()
            if preloaded_props and len(preloaded_props) > 0:
                prop_hash = hashlib.md5(preloaded_props.serialize(format='nt').encode()).hexdigest()[:16]
                prop_id = f"property_preload_{prop_hash}_{len(preloaded_props)}"
                store_graph(prop_id, preloaded_props)
                st.session_state.property_graph_id = prop_id
                st.session_state.preloaded_property_loaded = True
                # Auto-extract namespaces from property shapes too
                sync_namespaces_from_graph(preloaded_props)
        
        status_text.markdown("<p style='text-align: center; font-size: 16px; color: #28a745;'>✅ Ready!</p>", unsafe_allow_html=True)
        time.sleep(0.5)  # Brief pause to show "Ready!" message
    
    # Clear the loading screen
    loading_container.empty()
    return True  # Files were loaded

def app():
    # Initialize session state
    if "file_list" not in st.session_state:
        st.session_state.file_list = []
    if "combined_graph_id" not in st.session_state:
        st.session_state.combined_graph_id = None
    if "class_property_map" not in st.session_state:
        st.session_state.class_property_map = {}
    if "SHACL_content" not in st.session_state:
        st.session_state.SHACL_content = ""
    if "property_graph_id" not in st.session_state:
        st.session_state.property_graph_id = None
    if "property_constraints" not in st.session_state:
        st.session_state.property_constraints = {}
    if "existing_shacl_id" not in st.session_state:
        st.session_state.existing_shacl_id = None
    if "preloaded_ontology_loaded" not in st.session_state:
        st.session_state.preloaded_ontology_loaded = False
    if "preloaded_property_loaded" not in st.session_state:
        st.session_state.preloaded_property_loaded = False
    if "startup_complete" not in st.session_state:
        st.session_state.startup_complete = False

    # Auto-load preloaded files on first run
    if not st.session_state.startup_complete:
        load_preloaded_files()
        st.session_state.startup_complete = True


    page = st.sidebar.radio("Go to", ["Ontology Files", "Class and Property Menu", "Constraints", "SHACL"])

    if page == "Ontology Files":
        ontology_manager()
    elif page == "Class and Property Menu":
        display_classes_and_properties()
    elif page == "Constraints":
        display_constraints()
    elif page == "SHACL":   
        show_SHACL()


        
if __name__ == "__main__":
    app()
