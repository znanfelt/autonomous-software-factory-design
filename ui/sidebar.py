import streamlit as st

def render_sidebar():
    st.sidebar.title("Autonomous Software Factory")
    if 'initial_user_request' not in st.session_state:
        st.session_state.initial_user_request = "Can you make a python function? It should be for greeting people. Needs good docs."

    st.sidebar.text_area("Initial User Request", key="initial_user_request")

    if st.sidebar.button("Start Pipeline"):
        st.session_state.pipeline_active = True
        st.rerun()
    if st.sidebar.button("Reset State"):
        st.session_state.pipeline_active = False
        st.session_state.current_graph_state = None
        st.rerun()