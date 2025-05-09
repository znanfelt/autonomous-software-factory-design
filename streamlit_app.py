# streamlit_app.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import streamlit as st
from ui.display import display_graph_state
from ui.pipeline_runner import run_pipeline
from ui.sidebar import render_sidebar
from ui.state import initialize_ui_state

# Main Streamlit entry point

def main():
    initialize_ui_state()
    render_sidebar()
    run_pipeline()

if __name__ == "__main__":
    main()
