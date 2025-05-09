import streamlit as st
from ui.display import display_graph_state
import main_pipeline

def run_pipeline():
    # Incremental pipeline execution logic (port of original event loop)
    if 'pipeline_active' not in st.session_state:
        st.session_state.pipeline_active = False
    if 'current_graph_state' not in st.session_state:
        st.session_state.current_graph_state = None
    if st.session_state.pipeline_active:
        app = main_pipeline.build_graph()
        if st.session_state.stream_iterator is None:
            current_input_state_for_stream = st.session_state.current_graph_state
            st.session_state.stream_iterator = app.stream(current_input_state_for_stream, {"recursion_limit": 250})
        if st.session_state.stream_iterator:
            event_chunk = next(st.session_state.stream_iterator, "STREAM_ENDED_SENTINEL")
            if event_chunk and event_chunk != "STREAM_ENDED_SENTINEL":
                node_name = list(event_chunk.keys())[0]
                node_output = event_chunk[node_name]
                if isinstance(node_output, dict):
                    st.session_state.current_graph_state.update(node_output)
                st.session_state.run_events_log.append({
                    "timestamp": "now",  # Replace with real timestamp if needed
                    "node": node_name,
                    "message": f"Output from {node_name} received."
                })
                display_graph_state(st.session_state.current_graph_state)
                st.rerun()
            else:
                st.session_state.pipeline_active = False
                st.session_state.stream_iterator = None
                display_graph_state(st.session_state.current_graph_state)
    else:
        st.info('Pipeline is not active. Click start to begin.')