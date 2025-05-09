# UI session state helpers and initialization will go here
import streamlit as st
from main_pipeline.demo import initial_state

def initialize_ui_state():
    if 'pipeline_active' not in st.session_state:
        st.session_state.pipeline_active = False
    if 'current_graph_state' not in st.session_state or st.session_state.current_graph_state is None:
        st.session_state.current_graph_state = initial_state
    if 'run_events_log' not in st.session_state:
        st.session_state.run_events_log = []
    if 'stream_iterator' not in st.session_state:
        st.session_state.stream_iterator = None
    if 'current_step_message' not in st.session_state:
        st.session_state.current_step_message = ''
    if 'human_input_required_planner' not in st.session_state:
        st.session_state.human_input_required_planner = False
    if 'clarification_questions_cache' not in st.session_state:
        st.session_state.clarification_questions_cache = None
    if 'run_pipeline_clicked' not in st.session_state:
        st.session_state.run_pipeline_clicked = False