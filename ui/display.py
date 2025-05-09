import streamlit as st
from main_pipeline import agents, demo, tools, prompts, state, rag, graph

# UI display helpers (e.g., display_graph_state) will go here

def display_graph_state(graph_state_dict):
    if not graph_state_dict:
        st.info("Pipeline has not run yet or no state to display.")
        return
    st.subheader("Pipeline State Overview")
    key_fields_ordered = [
        "initial_user_request", "current_error", "architectural_decision",
        "clarification_questions_for_user", "clarified_user_input",
        "planner_iteration_count", "max_planner_iterations", "planned_task_description",
        "planner_notes", "task_description", "refinement_count", "max_refinements",
        "generated_code", 
        "validation_status", "validation_issues", "critique", "feedback_history",
        "packaged_artifacts_info", "handoff_summary",
    ]
    for key in key_fields_ordered:
        if key in graph_state_dict and graph_state_dict[key] is not None and graph_state_dict[key] != []:
            with st.expander(f"{key.replace('_', ' ').title()}", expanded=True):
                value = graph_state_dict[key]
                if isinstance(value, (dict, list)) and key not in ["feedback_history", "validation_issues", "clarification_questions_for_user"]:
                    st.json(value)
                elif key == "generated_code": st.code(value, language="python")
                elif key == "feedback_history":
                    for i, item in enumerate(reversed(value)): st.markdown(f"```\nF{len(value)-i}: {item}\n```")
                elif key == "validation_issues" or key == "clarification_questions_for_user":
                    if value:
                        for item_val in value: st.warning(f"- {item_val}")
                    else: st.caption("None")
                else: st.markdown(f"```\n{value}\n```")

    # Special display for Test Case information
    if "generated_test_cases" in graph_state_dict and graph_state_dict["generated_test_cases"]:
        with st.expander("Test Cases & Results", expanded=True):
            st.markdown(f"**Total Generated Test Cases:** {len(graph_state_dict['generated_test_cases'])}")
            st.markdown(f"**Current Test Index (next to run):** {graph_state_dict.get('current_test_case_index', 0)}")
            st.markdown(f"**All Tests Passed (so far in current dev cycle):** {graph_state_dict.get('all_tests_passed', False)}")

            if "test_results_summary" in graph_state_dict and graph_state_dict["test_results_summary"]:
                st.markdown("**Individual Test Results:**")
                for i, result in enumerate(graph_state_dict["test_results_summary"]):
                    tc = result["test_case"]
                    status_icon = "✅" if result["status"] == "success" else "❌"
                    with st.container():
                        st.markdown(f"--- \n**Test {i+1}: {status_icon} {tc.get('description', 'N/A')}**")
                        st.caption(f"Function: `{tc['function_name']}`, Inputs: `{tc['inputs']}`, Expected: `{tc['expected_output']}`")
                        if result["status"] != "success":
                            st.error(f"Status: {result['status']} - Message: {result['message']}")
                            if "actual_output" in result:
                                st.caption(f"Actual Output: `{result['actual_output']}`")
                        else:
                             st.success(f"Status: {result['status']}")
            elif graph_state_dict.get("current_test_status"):
                 st.markdown(f"**Last Run Test Status:** {graph_state_dict['current_test_status']}")
                 st.markdown(f"**Message:** {graph_state_dict['current_test_message']}")

    # Display the pipeline steps as a multi-line list
    if "run_events_log" in st.session_state and st.session_state["run_events_log"]:
        steps = [f"{event.get('timestamp','')} - {event.get('node','') or ''}" for event in st.session_state["run_events_log"] if event.get('node')]
        if steps:
            st.markdown("**Pipeline Steps (in order):**")
            st.text("\n".join(steps))