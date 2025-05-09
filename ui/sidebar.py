import streamlit as st

def render_sidebar():
    st.sidebar.title("Autonomous Software Factory")
    if st.sidebar.button("Start Pipeline"):
        st.session_state.pipeline_active = True
        st.experimental_rerun()
    if st.sidebar.button("Reset State"):
        st.session_state.pipeline_active = False
        st.session_state.current_graph_state = None
        st.experimental_rerun()