# streamlit_app.py
import streamlit as st
import V1.main_pipeline as main_pipeline # Import the original script
from V1.main_pipeline import GraphState, ARTIFACTS_BASE_DIR, END # Import specifics
import os
import shutil
import logging
from io import StringIO
from pathlib import Path

# --- Logging Setup for UI ---
# Capture logs to display in Streamlit
log_stringio = StringIO()
# Get the root logger (main_pipeline.py configures logging.basicConfig for the root logger)
root_logger = logging.getLogger()
ui_log_handler = logging.StreamHandler(log_stringio)
# Ensure the formatter matches or is similar to the console output for consistency
ui_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s'))
root_logger.addHandler(ui_log_handler)
# Ensure root logger level is appropriate (main_pipeline sets it to INFO)
# If main_pipeline.py might change its level, set it explicitly here too for the handler or root.
# root_logger.setLevel(logging.INFO) # Usually set by main_pipeline.basicConfig

# --- Helper to display state ---
def display_graph_state(graph_state_dict):
    if not graph_state_dict:
        st.info("Pipeline has not run yet or no state to display.")
        return

    st.subheader("Pipeline State Overview")
    # Key fields to display prominently
    key_fields_ordered = [
        "initial_user_request", "current_error",
        "architectural_decision",
        "clarification_questions_for_user", "clarified_user_input",
        "planner_iteration_count", "max_planner_iterations",
        "planned_task_description", "planner_notes", "task_description",
        "refinement_count", "max_refinements",
        "generated_code",
        "current_test_case", "test_status", "test_message",
        "validation_status", "validation_issues",
        "critique", "feedback_history",
        "packaged_artifacts_info", "handoff_summary",
    ]
    for key in key_fields_ordered:
        if key in graph_state_dict and graph_state_dict[key] is not None and graph_state_dict[key] != []:
            # Determine if expander should be open by default for certain key fields
            expanded_by_default = key in ["current_error", "handoff_summary", "planned_task_description", "generated_code", "test_message", "validation_issues", "critique"]
            
            with st.expander(f"{key.replace('_', ' ').title()}", expanded=expanded_by_default):
                value = graph_state_dict[key]
                if isinstance(value, (dict, list)) and key not in ["feedback_history", "validation_issues"]: # Prettier display for these
                    st.json(value)
                elif key == "generated_code":
                    st.code(value, language="python")
                elif key == "feedback_history":
                    for i, item in enumerate(reversed(value)): # Show latest first
                        st.markdown(f"```\nAttempt {len(value)-i}: {item}\n```")
                elif key == "validation_issues":
                    for item in value:
                        st.warning(f"- {item}")
                else:
                    st.markdown(f"```\n{value}\n```")

# --- Main UI ---
st.set_page_config(layout="wide")
st.title("🧩 Autonomous Code Generation Pipeline UI 🧩")

# Initialize RAG engines once
if 'rag_initialized' not in st.session_state:
    if not os.getenv("OPENAI_API_KEY"):
         st.sidebar.warning("OPENAI_API_KEY not found. LLMs may use mocks or fail.")
    else:
         st.sidebar.success("OPENAI_API_KEY found.")
    with st.spinner("Initializing RAG engines..."):
        main_pipeline.initialize_rag_engines()
    st.session_state.rag_initialized = True

# Initialize session state variables
if "pipeline_app" not in st.session_state:
    st.session_state.pipeline_app = None
if "current_graph_state" not in st.session_state:
    st.session_state.current_graph_state = {}
if "run_events_log" not in st.session_state: # To store events from stream for display
    st.session_state.run_events_log = []
if "pipeline_active" not in st.session_state: # True while stream is being consumed
    st.session_state.pipeline_active = False
if "human_input_required_planner" not in st.session_state:
    st.session_state.human_input_required_planner = False
if "clarification_questions_cache" not in st.session_state:
    st.session_state.clarification_questions_cache = []


# --- Sidebar for Configuration ---
st.sidebar.header("⚙️ Configuration")
DEFAULT_INITIAL_REQUEST = "Can you make a python function? It should be for greeting people. Needs good docs."
DEFAULT_MAX_REFINEMENTS = int(os.getenv("MAX_REFINEMENTS", "3"))
DEFAULT_MAX_PLANNER_ITERATIONS = int(os.getenv("MAX_PLANNER_ITERATIONS", "2"))
DEFAULT_LLM_MODELS = {
    "architect_llm":  os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o"),
    "planner_llm":    os.getenv("PLANNER_LLM_MODEL", "gpt-4o"),
    "developer_llm":  os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"),
    "qa_llm":         os.getenv("QA_LLM_MODEL", "gpt-4o"),
    "validation_llm": os.getenv("VALIDATION_LLM_MODEL", "gpt-3.5-turbo"),
    "critique_llm":   os.getenv("CRITIQUE_LLM_MODEL", "gpt-4o")
}

initial_user_request_ui = st.sidebar.text_area("Initial User Request:", value=st.session_state.get("ui_initial_request", DEFAULT_INITIAL_REQUEST), height=100, key="ui_initial_request")
max_refinements_ui = st.sidebar.number_input("Max Developer Refinements:", min_value=0, max_value=10, value=st.session_state.get("ui_max_refinements", DEFAULT_MAX_REFINEMENTS), key="ui_max_refinements")
max_planner_iterations_ui = st.sidebar.number_input("Max Planner Iterations:", min_value=1, max_value=5, value=st.session_state.get("ui_max_planner_iterations", DEFAULT_MAX_PLANNER_ITERATIONS), key="ui_max_planner_iterations")

st.sidebar.markdown("---")
st.sidebar.subheader("Test Case Configuration")
test_case_function_name_ui = st.sidebar.text_input("Function Name:", value=st.session_state.get("ui_test_func_name", "greet_user"), key="ui_test_func_name")
test_case_inputs_ui = st.sidebar.text_input("Inputs (Python tuple str):", value=st.session_state.get("ui_test_inputs", "('Alice',)"), key="ui_test_inputs", help="Example: `('Alice',)` or `(1, 2)`")
test_case_expected_output_ui = st.sidebar.text_input("Expected Output (Python literal str):", value=st.session_state.get("ui_test_expected_output", "'Hello, Alice!'"), key="ui_test_expected_output", help="Example: `'Hello, Alice!'` or `3`")

with st.sidebar.expander("LLM Model Configuration"):
    llm_models_ui = {}
    for key, default_value in DEFAULT_LLM_MODELS.items():
        llm_models_ui[key] = st.text_input(f"{key.replace('_', ' ').title()}:", value=st.session_state.get(f"ui_llm_{key}", default_value), key=f"ui_llm_{key}")

cleanup_artifacts_ui = st.sidebar.checkbox("Clean up previous run's artifacts before new run", True)

# --- Main Area for Controls and Display ---
main_col, events_col = st.columns([2,1])

with main_col:
    st.subheader("▶️ Pipeline Controls")
    if st.button("🚀 Initialize & Run Pipeline", disabled=st.session_state.pipeline_active, type="primary"):
        st.session_state.pipeline_active = True # Lock button
        st.session_state.human_input_required_planner = False
        st.session_state.clarification_questions_cache = []
        st.session_state.run_events_log = [{"message": "Pipeline run initiated by user."}]
        log_stringio.truncate(0) # Clear previous logs
        log_stringio.seek(0)

        if cleanup_artifacts_ui and main_pipeline.ARTIFACTS_BASE_DIR.exists():
            try:
                shutil.rmtree(main_pipeline.ARTIFACTS_BASE_DIR)
                st.session_state.run_events_log.append({"message": f"Cleaned up artifacts in {main_pipeline.ARTIFACTS_BASE_DIR}"})
            except Exception as e:
                st.error(f"Could not clean up artifacts: {e}")
        main_pipeline.ARTIFACTS_BASE_DIR.mkdir(parents=True, exist_ok=True)

        st.session_state.pipeline_app = main_pipeline.build_graph()

        try:
            parsed_test_inputs = eval(test_case_inputs_ui)
            if not isinstance(parsed_test_inputs, tuple): raise ValueError("Inputs must be a tuple.")
        except Exception as e:
            st.error(f"Error parsing test case inputs: {e}. Using default `('TestUser',)`.")
            parsed_test_inputs = ('TestUser',)
        try:
            parsed_expected_output = eval(test_case_expected_output_ui)
        except Exception as e:
            st.error(f"Error parsing test case expected output: {e}. Using default `None`.")
            parsed_expected_output = None

        initial_state_dict: GraphState = {
            "initial_user_request": initial_user_request_ui,
            "architectural_decision": None,
            "clarified_user_input": None, "clarification_questions_for_user": None,
            "planner_iteration_count": 0, "max_planner_iterations": max_planner_iterations_ui,
            "llm_models_config": llm_models_ui,
            "task_description": "", "planned_task_description": None, "planner_notes": None,
            "current_test_case": {"function_name": test_case_function_name_ui, "inputs": parsed_test_inputs, "expected_output": parsed_expected_output},
            "generated_code": None, "test_status": None, "test_message": None, "critique": None,
            "validation_status": None, "validation_issues": [],
            "packaged_artifacts_info": None, "handoff_summary": None,
            "feedback_history": [], "refinement_count": 0, "max_refinements": max_refinements_ui,
            "current_error": None, "qa_agent_messages": []
        }
        st.session_state.current_graph_state = initial_state_dict
        st.info("Pipeline initialized. Streaming events...")
        st.rerun()

    # --- Pipeline Execution Loop (if active and not waiting for human) ---
    if st.session_state.pipeline_active and not st.session_state.human_input_required_planner:
        app = st.session_state.pipeline_app
        current_input_state = st.session_state.current_graph_state
        
        st.session_state.run_events_log.append({"message": f"Invoking graph stream with current state. Planner iteration: {current_input_state.get('planner_iteration_count',0)}, Refinement count: {current_input_state.get('refinement_count',0)}."})
        
        with st.spinner("Pipeline is running... consuming stream..."):
            try:
                for event_chunk in app.stream(current_input_state, {"recursion_limit": 250}): # Increased limit
                    # event_chunk is Dict[str, Any], key is node name, value is node output
                    node_name = list(event_chunk.keys())[0]
                    node_output = event_chunk[node_name]

                    st.session_state.run_events_log.append({f"Node '{node_name}' output": node_output})

                    # Update our view of the graph state
                    if isinstance(node_output, dict) and node_name != END: # END node's output is the full final state
                        st.session_state.current_graph_state.update(node_output)
                    elif node_name == END: # Graph finished
                        st.session_state.current_graph_state = node_output # This is the final state
                        st.session_state.pipeline_active = False
                        st.session_state.run_events_log.append({"message": "Graph stream ended."})
                        st.balloons()
                        break # Exit stream loop

                    # Check for HITL condition after planner
                    if node_name == "planner_agent_node":
                        if st.session_state.current_graph_state.get("clarification_questions_for_user"):
                            st.session_state.clarification_questions_cache = st.session_state.current_graph_state["clarification_questions_for_user"]
                            st.session_state.human_input_required_planner = True
                            st.session_state.run_events_log.append({"message": "Planner requires human input. Pausing stream."})
                            break # Exit stream loop to ask human

                # If stream exhausted without END and not for HITL, implies completion or unexpected stop
                if st.session_state.pipeline_active and not st.session_state.human_input_required_planner:
                    st.session_state.pipeline_active = False # Assume finished if stream ends
                    st.session_state.run_events_log.append({"message": "Graph stream exhausted (not via END node, or already handled)."})


            except Exception as e:
                st.error(f"Critical error during pipeline stream: {e}")
                main_pipeline.logger.error(f"Pipeline stream critical error: {e}", exc_info=True)
                if "current_graph_state" in st.session_state and st.session_state.current_graph_state:
                     st.session_state.current_graph_state["current_error"] = f"Stream Exception: {str(e)}"
                st.session_state.pipeline_active = False # Stop pipeline on critical error
                st.session_state.run_events_log.append({"error": f"Pipeline stream critical error: {e}"})
        
        st.rerun() # Rerun to update UI based on new state / human input requirement

    # --- Human Interaction for Planner ---
    if st.session_state.human_input_required_planner:
        st.subheader("❓ Planner Needs Clarification")
        st.warning("The Planner agent requires more information to proceed. Please answer the questions below.")
        questions = st.session_state.clarification_questions_cache
        
        # Ensure current_graph_state is available
        if not st.session_state.current_graph_state:
            st.error("Error: Graph state not found for human interaction. Please restart.")
            st.session_state.human_input_required_planner = False # Reset to avoid loop
            st.stop()

        answers_form = st.form(key="planner_clarification_form")
        submitted_answers = {}
        if questions:
            for i, q_text in enumerate(questions):
                submitted_answers[q_text] = answers_form.text_input(f"Q{i+1}: {q_text}", key=f"planner_q_{i}")
        
        submit_button = answers_form.form_submit_button("Submit Clarifications to Planner")

        if submit_button:
            full_answers_list = []
            all_answered = True
            for q_text, answer_text in submitted_answers.items():
                if not answer_text.strip():
                    st.warning(f"Please provide an answer for: {q_text}")
                    all_answered = False
                    break
                full_answers_list.append(f"Answer to '{q_text}': {answer_text}")
            
            if all_answered:
                clarified_input_str = (
                    f"Original Request: '{st.session_state.current_graph_state['initial_user_request']}'. "
                    f"User Clarifications: {'; '.join(full_answers_list)}"
                )
                st.session_state.current_graph_state["clarified_user_input"] = clarified_input_str
                st.session_state.current_graph_state["clarification_questions_for_user"] = None # Mark as answered
                
                # Planner iteration count is incremented by the planner node itself if it runs again.
                # However, the human_interaction_node in the original graph might have done this.
                # For UI-driven HITL, we are bypassing that node.
                # The planner node will increment its own internal counter when it runs.
                # Let's ensure the `planner_iteration_count` in the state is accurate for the *next* planner run.
                # The planner node itself does `state['planner_iteration_count'] + 1`.
                # So, we don't need to increment it here before re-feeding to the stream.

                st.session_state.human_input_required_planner = False
                st.session_state.clarification_questions_cache = []
                st.session_state.pipeline_active = True # Ensure pipeline continues
                st.session_state.run_events_log.append({"message": "User submitted clarifications. Resuming pipeline stream."})
                st.info("Clarifications submitted. Resuming pipeline...")
                st.rerun()
            else: # Not all answered
                st.error("Please answer all questions before submitting.")


    # --- Display Area ---
    st.subheader("📝 Pipeline Output & State")
    display_graph_state(st.session_state.current_graph_state)

    if st.session_state.current_graph_state and st.session_state.current_graph_state.get("packaged_artifacts_info"):
        st.subheader("📦 Packaged Artifacts")
        artifacts = st.session_state.current_graph_state["packaged_artifacts_info"]
        # st.json(artifacts) # Already shown in display_graph_state

        code_file_rel_path_str = artifacts.get("code_file")
        readme_file_rel_path_str = artifacts.get("readme_file")

        # ARTIFACTS_BASE_DIR.parent is the directory where "output_artifacts_demo" folder resides.
        # The paths in artifacts["code_file"] are relative to this parent.
        base_path_for_artifacts = main_pipeline.ARTIFACTS_BASE_DIR.parent

        if code_file_rel_path_str:
            actual_code_file_path = Path(base_path_for_artifacts / code_file_rel_path_str).resolve()
            if actual_code_file_path.exists():
                with st.expander(f"View Code: {Path(code_file_rel_path_str).name}", expanded=False):
                    st.code(actual_code_file_path.read_text(), language="python")
            else:
                st.warning(f"Code file not found at: {actual_code_file_path} (Relative: {code_file_rel_path_str})")

        if readme_file_rel_path_str:
            actual_readme_file_path = Path(base_path_for_artifacts / readme_file_rel_path_str).resolve()
            if actual_readme_file_path.exists():
                with st.expander(f"View README: {Path(readme_file_rel_path_str).name}", expanded=False):
                    st.markdown(actual_readme_file_path.read_text())
            else:
                st.warning(f"README file not found at: {actual_readme_file_path} (Relative: {readme_file_rel_path_str})")

with events_col:
    st.subheader("🔄 Stream Events")
    with st.container(height=600): # Makes this section scrollable
        if not st.session_state.run_events_log:
            st.caption("No pipeline events yet for this run.")
        for i, event_info in enumerate(reversed(st.session_state.run_events_log)): # Show latest first
            st.caption(f"Event {len(st.session_state.run_events_log) - i}")
            st.write(event_info)
            st.divider()
    
    st.subheader("📜 Pipeline Logs")
    with st.container(height=400): # Makes this section scrollable
        log_content = log_stringio.getvalue()
        if not log_content:
            st.caption("No logs generated yet for this run.")
        else:
            st.text_area("Logs:", value=log_content, height=380, disabled=True, key="log_display_area")