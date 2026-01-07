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
    sync_namespaces_from_graph,
    show_graph_visualization,
    copy_graph
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
    
    # Show loading screen with animated network graph
    loading_container = st.empty()
    with loading_container.container():
        st.markdown("""
        <style>
        .loading-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px;
        }
        .loading-title {
            font-size: 28px;
            font-weight: bold;
            margin-top: 25px;
            color: #1f77b4;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        /* Network Graph Animation */
        .network-container {
            width: 220px;
            height: 220px;
            position: relative;
        }
        
        /* Nodes - enhanced with gradients and shadows */
        .node {
            position: absolute;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: linear-gradient(135deg, #4da3ff 0%, #1f77b4 50%, #0d4f80 100%);
            box-shadow: 
                0 4px 8px rgba(31, 119, 180, 0.4),
                inset 0 2px 4px rgba(255,255,255,0.3),
                inset 0 -2px 4px rgba(0,0,0,0.2);
            opacity: 0;
            transform: scale(0);
        }
        
        /* Center node - orange/gold gradient */
        .node.center { 
            left: 96px; top: 96px; 
            width: 32px; height: 32px; 
            background: linear-gradient(135deg, #ffb347 0%, #ff7f0e 50%, #cc5500 100%);
            box-shadow: 
                0 4px 12px rgba(255, 127, 14, 0.5),
                0 0 20px rgba(255, 127, 14, 0.3),
                inset 0 2px 4px rgba(255,255,255,0.4),
                inset 0 -2px 4px rgba(0,0,0,0.2);
        }
        
        /* Outer nodes positioned in hexagon pattern around center (112,112) */
        .node.n1 { left: 98px; top: 20px; }    /* top */
        .node.n2 { left: 168px; top: 56px; }   /* top-right */
        .node.n3 { left: 168px; top: 140px; }  /* bottom-right */
        .node.n4 { left: 98px; top: 176px; }   /* bottom */
        .node.n5 { left: 28px; top: 140px; }   /* bottom-left */
        .node.n6 { left: 28px; top: 56px; }    /* top-left */
        
        /* Edges - start from center (112,112) and connect to each node */
        .edge {
            position: absolute;
            height: 3px;
            background: linear-gradient(90deg, rgba(255,127,14,0.9) 0%, rgba(31,119,180,0.9) 100%);
            border-radius: 2px;
            transform-origin: left center;
            opacity: 0;
            box-shadow: 0 0 6px rgba(31, 119, 180, 0.4);
        }
        
        /* Each edge: starts at center, rotates to point at target node */
        /* Center is at (112, 112), edges start there */
        .edge.e1 { left: 112px; top: 112px; width: 68px; transform: rotate(-90deg); }   /* to n1 (top) */
        .edge.e2 { left: 112px; top: 112px; width: 74px; transform: rotate(-37deg); }   /* to n2 (top-right) */
        .edge.e3 { left: 112px; top: 112px; width: 74px; transform: rotate(37deg); }    /* to n3 (bottom-right) */
        .edge.e4 { left: 112px; top: 112px; width: 68px; transform: rotate(90deg); }    /* to n4 (bottom) */
        .edge.e5 { left: 112px; top: 112px; width: 74px; transform: rotate(143deg); }   /* to n5 (bottom-left) */
        .edge.e6 { left: 112px; top: 112px; width: 74px; transform: rotate(-143deg); }  /* to n6 (top-left) */
        
        /* Looping animation - builds up then fades and repeats */
        @keyframes nodeLoop {
            0% { opacity: 0; transform: scale(0); }
            10% { opacity: 1; transform: scale(1.15); }
            15% { opacity: 1; transform: scale(1); }
            75% { opacity: 1; transform: scale(1); }
            85% { opacity: 0; transform: scale(0.8); }
            100% { opacity: 0; transform: scale(0); }
        }
        
        @keyframes centerNodeLoop {
            0% { opacity: 0; transform: scale(0); }
            8% { opacity: 1; transform: scale(1.2); }
            12% { opacity: 1; transform: scale(1); }
            75% { opacity: 1; transform: scale(1); }
            85% { opacity: 0; transform: scale(0.8); }
            100% { opacity: 0; transform: scale(0); }
        }
        
        @keyframes edgeLoopShort {
            0% { opacity: 0; width: 0; }
            15% { opacity: 1; width: 68px; }
            75% { opacity: 1; width: 68px; }
            85% { opacity: 0; width: 68px; }
            100% { opacity: 0; width: 0; }
        }
        
        @keyframes edgeLoopLong {
            0% { opacity: 0; width: 0; }
            15% { opacity: 1; width: 74px; }
            75% { opacity: 1; width: 74px; }
            85% { opacity: 0; width: 74px; }
            100% { opacity: 0; width: 0; }
        }
        
        /* 4 second total loop */
        .node.center { animation: centerNodeLoop 4s ease-in-out 0s infinite; }
        .node.n1 { animation: nodeLoop 4s ease-in-out 0.15s infinite; }
        .node.n2 { animation: nodeLoop 4s ease-in-out 0.3s infinite; }
        .node.n3 { animation: nodeLoop 4s ease-in-out 0.45s infinite; }
        .node.n4 { animation: nodeLoop 4s ease-in-out 0.6s infinite; }
        .node.n5 { animation: nodeLoop 4s ease-in-out 0.75s infinite; }
        .node.n6 { animation: nodeLoop 4s ease-in-out 0.9s infinite; }
        
        .edge.e1 { animation: edgeLoopShort 4s ease-in-out 0.1s infinite; }
        .edge.e2 { animation: edgeLoopLong 4s ease-in-out 0.25s infinite; }
        .edge.e3 { animation: edgeLoopLong 4s ease-in-out 0.4s infinite; }
        .edge.e4 { animation: edgeLoopShort 4s ease-in-out 0.55s infinite; }
        .edge.e5 { animation: edgeLoopLong 4s ease-in-out 0.7s infinite; }
        .edge.e6 { animation: edgeLoopLong 4s ease-in-out 0.85s infinite; }
        </style>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("""
            <div class="loading-container">
                <div class="network-container">
                    <!-- Edges (drawn first, behind nodes) -->
                    <div class="edge e1"></div>
                    <div class="edge e2"></div>
                    <div class="edge e3"></div>
                    <div class="edge e4"></div>
                    <div class="edge e5"></div>
                    <div class="edge e6"></div>
                    <!-- Nodes -->
                    <div class="node center"></div>
                    <div class="node n1"></div>
                    <div class="node n2"></div>
                    <div class="node n3"></div>
                    <div class="node n4"></div>
                    <div class="node n5"></div>
                    <div class="node n6"></div>
                </div>
                <div class="loading-title">Initializing CEDS SHACL Generator</div>
            </div>
            """, unsafe_allow_html=True)
            
            status_text = st.empty()
        
        # Load ontology if available
        if preload_status["ontology"] and not st.session_state.preloaded_ontology_loaded:
            status_text.markdown("<p style='text-align: center; font-size: 16px; color: #888;'>📚 Loading CEDS Ontology (this may take a moment)...</p>", unsafe_allow_html=True)
            preloaded_graph = _load_preloaded_ontology()
            if preloaded_graph and len(preloaded_graph) > 0:
                # IMPORTANT: Copy the cached graph to avoid mutating the global cache
                session_graph = copy_graph(preloaded_graph)
                graph_hash = hashlib.md5(session_graph.serialize(format='nt').encode()).hexdigest()[:16]
                graph_id = f"combined_preload_{graph_hash}_{len(session_graph)}"
                store_graph(graph_id, session_graph)
                st.session_state.combined_graph_id = graph_id
                st.session_state.preloaded_ontology_loaded = True
                # Auto-extract namespaces from the loaded ontology
                sync_namespaces_from_graph(session_graph)
        
        # Load property shapes if available
        if preload_status["property_shapes"] and not st.session_state.preloaded_property_loaded:
            status_text.markdown("<p style='text-align: center; font-size: 16px; color: #888;'>📋 Loading Property Shapes...</p>", unsafe_allow_html=True)
            preloaded_props = _load_preloaded_property_shapes()
            if preloaded_props and len(preloaded_props) > 0:
                # IMPORTANT: Copy the cached graph to avoid mutating the global cache
                session_props = copy_graph(preloaded_props)
                prop_hash = hashlib.md5(session_props.serialize(format='nt').encode()).hexdigest()[:16]
                prop_id = f"property_preload_{prop_hash}_{len(session_props)}"
                store_graph(prop_id, session_props)
                st.session_state.property_graph_id = prop_id
                st.session_state.preloaded_property_loaded = True
                # Auto-extract namespaces from property shapes too
                sync_namespaces_from_graph(session_props)
        
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


    page = st.sidebar.radio("Go to", ["Ontology Files", "Class and Property Menu", "Constraints", "SHACL", "Graph View"])

    if page == "Ontology Files":
        ontology_manager()
    elif page == "Class and Property Menu":
        display_classes_and_properties()
    elif page == "Constraints":
        display_constraints()
    elif page == "SHACL":   
        show_SHACL()
    elif page == "Graph View":
        show_graph_visualization()


        
if __name__ == "__main__":
    app()
