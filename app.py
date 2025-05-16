# app.py
from typing import Dict
from typing import Any
import streamlit as st
import os
import json
import logging
from pathlib import Path
import sys
from datetime import datetime # Ensure datetime is imported

# Ensure the package is discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))) 
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) 

from pocketflow import Flow 
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
)
from utils.database import (
    init_db, create_task, update_task_field, get_task_data,
    add_code_version, get_latest_code_version,
    log_test_run_result, get_test_results_for_version,
    log_validation_result, log_feedback, get_feedback_history_for_task, # Changed to _for_task
    add_packaged_artifact, DB_FILE # Ensure DB_FILE is imported if used directly
)
from utils.prompts import (
    ARCHITECT_PROMPT_TEMPLATE, PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
    PLANNER_CODEGEN_PROMPT_TEMPLATE, DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
    TEST_CASE_DESIGNER_PROMPT_TEMPLATE, VALIDATION_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT_TEMPLATE
)
from flow import (
    elicitation_flow, test_design_flow, initial_code_gen_flow,
    qa_validation_flow, critique_refine_flow, packaging_flow
)

# --- Logger Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constants ---
RAG_CONTEXTS_DIR = Path(__file__).parent / "rag_contexts"
RAG_CONTEXT_KEYS = [
    "architectural_principles_context",
    "planning_guidelines_context",
    "coding_standards_context",
    "validation_rules_context",
    "debugging_tips_context"
]
MAX_PLANNER_ITERATIONS = int(os.getenv("MAX_PLANNER_ITERATIONS", "2"))
MAX_REFINEMENTS = int(os.getenv("MAX_REFINEMENTS", "3"))
LLM_MODELS_CONFIG = {
    "architect_llm":  os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o"),
    "planner_llm":    os.getenv("PLANNER_LLM_MODEL", "gpt-4o"),
    "developer_llm":  os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"),
    "test_designer_llm": os.getenv("TEST_DESIGNER_LLM_MODEL", "gpt-3.5-turbo"),
    "qa_llm":         os.getenv("QA_LLM_MODEL", "gpt-4o"),
    "validation_llm": os.getenv("VALIDATION_LLM_MODEL", "gpt-3.5-turbo"),
    "critique_llm":   os.getenv("CRITIQUE_LLM_MODEL", "gpt-4o-mini")
}

# --- RAG Context Loading ---
def load_rag_context(filename: str) -> str:
    try:
        with open(RAG_CONTEXTS_DIR / filename, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading RAG context {filename}: {e}")
        return f"Error loading {filename}: {e}"

# --- Streamlit UI ---
st.set_page_config(layout="wide")
st.title("🚧 Simple Autonomous Software Factory (MVP) 🏭")
st.caption("Describe a Python function, and AI agents will try to build, test, and validate it with your guidance.")

# --- Initialize Session State & DB ---
if "app_initialized" not in st.session_state:
    init_db() # Uses DB_FILE from database.py
    st.session_state.ui_stage = "INPUT_REQUIREMENTS"
    st.session_state.active_task_id = None
    st.session_state.user_raw_request = ""
    st.session_state.current_request_for_planner = ""
    st.session_state.architectural_decision = None
    st.session_state.planner_iteration_count = 0
    st.session_state.clarification_questions_for_user = None
    st.session_state.planned_task_description = None # This will store the dict/JSON plan
    st.session_state.planner_notes = None
    st.session_state.generated_code = None
    st.session_state.active_code_version_id = None
    st.session_state.generated_test_cases = None
    st.session_state.current_test_case_index = 0
    st.session_state.test_results_summary = []
    st.session_state.all_tests_passed = False
    st.session_state.validation_status = None
    st.session_state.validation_issues = None
    st.session_state.user_rejection_reason = ""
    st.session_state.critique_feedback = None
    st.session_state.feedback_history = []
    st.session_state.refinement_count = 0
    st.session_state.packaged_artifacts_info = None
    st.session_state.handoff_summary = None
    st.session_state.current_error_message = None
    
    st.session_state.architectural_principles_context = load_rag_context("architectural_principles.txt")
    st.session_state.planning_guidelines_context = load_rag_context("planning_guidelines.txt")
    st.session_state.coding_standards_context = load_rag_context("coding_standards.txt")
    st.session_state.validation_rules_context = load_rag_context("validation_rules.txt")
    st.session_state.debugging_tips_context = load_rag_context("debugging_tips.txt")
    st.session_state.app_initialized = True
    logger.info("Streamlit App Initialized.")

# --- Helper functions ---
def reset_for_new_task():
    rag_contexts_keys = [
        "architectural_principles_context", "planning_guidelines_context",
        "coding_standards_context", "validation_rules_context", "debugging_tips_context"
    ]
    rag_contexts_values = {k: st.session_state.get(k) for k in rag_contexts_keys}
    
    st.session_state.clear() 
    st.session_state.update(rag_contexts_values) 
    st.session_state.app_initialized = True 

    st.session_state.ui_stage = "INPUT_REQUIREMENTS"
    st.session_state.active_task_id = None # Reset active task
    st.session_state.user_raw_request = ""
    # ... (re-initialize all other relevant session state variables as in the initial setup)
    st.session_state.current_request_for_planner = ""
    st.session_state.architectural_decision = None
    st.session_state.planner_iteration_count = 0
    st.session_state.clarification_questions_for_user = None
    st.session_state.planned_task_description = None
    st.session_state.planner_notes = None
    st.session_state.generated_code = None
    st.session_state.active_code_version_id = None
    st.session_state.generated_test_cases = None
    st.session_state.current_test_case_index = 0
    st.session_state.test_results_summary = []
    st.session_state.all_tests_passed = False
    st.session_state.validation_status = None
    st.session_state.validation_issues = None
    st.session_state.user_rejection_reason = ""
    st.session_state.critique_feedback = None
    st.session_state.feedback_history = []
    st.session_state.refinement_count = 0
    st.session_state.packaged_artifacts_info = None
    st.session_state.handoff_summary = None
    st.session_state.current_error_message = None
    logger.info("UI state reset for new task.")

def display_error():
    if st.session_state.current_error_message:
        st.error(f"An error occurred: {st.session_state.current_error_message}")

def get_shared_for_flow() -> Dict[str, Any]:
    # Selectively copy relevant parts of st.session_state to shared_for_flow
    # This prevents passing large or irrelevant Streamlit-internal objects
    shared = {
        "user_raw_request": st.session_state.user_raw_request,
        "current_request_for_planner": st.session_state.current_request_for_planner,
        "architectural_decision": st.session_state.architectural_decision,
        "planner_iteration_count": st.session_state.planner_iteration_count,
        "clarification_questions_for_user": st.session_state.clarification_questions_for_user,
        "planned_task_description": st.session_state.planned_task_description,
        "planner_notes": st.session_state.planner_notes,
        "developer_task_description": st.session_state.get("developer_task_description"), # Ensure this is set before dev node
        "generated_code": st.session_state.generated_code,
        "active_code_version_id": st.session_state.active_code_version_id,
        "generated_test_cases": st.session_state.generated_test_cases,
        "current_test_case_index": st.session_state.current_test_case_index,
        "test_results_summary": st.session_state.test_results_summary,
        "all_tests_passed": st.session_state.all_tests_passed,
        "validation_status": st.session_state.validation_status,
        "validation_issues": st.session_state.validation_issues,
        "user_rejection_reason": st.session_state.user_rejection_reason,
        "critique_feedback": st.session_state.critique_feedback,
        "feedback_history": st.session_state.feedback_history,
        "refinement_count": st.session_state.refinement_count,
        "packaged_artifacts_info": st.session_state.packaged_artifacts_info,
        "handoff_summary": st.session_state.handoff_summary,
        "current_error_message": st.session_state.current_error_message,
        # RAG Contexts
        "architectural_principles_context": st.session_state.architectural_principles_context,
        "planning_guidelines_context": st.session_state.planning_guidelines_context,
        "coding_standards_context": st.session_state.coding_standards_context,
        "validation_rules_context": st.session_state.validation_rules_context,
        "debugging_tips_context": st.session_state.debugging_tips_context,
        # Configs
        "llm_models_config": LLM_MODELS_CONFIG,
        "max_planner_iterations": MAX_PLANNER_ITERATIONS,
        "max_refinements": MAX_REFINEMENTS,
        "active_task_id": st.session_state.active_task_id # Pass task_id for context if needed by nodes
    }
    return shared

# --- UI Rendering and Flow Logic ---

if st.session_state.ui_stage == "INPUT_REQUIREMENTS":
    st.header("1. Describe Your Python Function")
    user_input = st.text_area("What function would you like the AI to create?", 
                              value=st.session_state.user_raw_request, height=150, key="raw_req_input_key")
    
    if st.button("Generate Function Plan", key="submit_initial_request_btn"):
        if not user_input.strip():
            st.warning("Please describe the function you need.")
        else:
            reset_for_new_task() 
            st.session_state.user_raw_request = user_input
            st.session_state.current_request_for_planner = user_input 
            
            task_id = create_task(st.session_state.user_raw_request)
            if task_id:
                st.session_state.active_task_id = task_id
                logger.info(f"New task {task_id} for request: {user_input[:50]}...")
                
                shared_for_flow = get_shared_for_flow()
                # Explicitly ensure planner_iteration_count is fresh for this task's elicitation
                shared_for_flow["planner_iteration_count"] = 0 
                
                with st.spinner("Architect & Planner are thinking..."):
                    try:
                        action = elicitation_flow.run(shared_for_flow)
                        st.session_state.update(shared_for_flow) 
                        
                        update_task_field(task_id, "architectural_decision", json.dumps(st.session_state.get("architectural_decision")) if st.session_state.get("architectural_decision") else None)
                        update_task_field(task_id, "planner_iteration_count", st.session_state.get("planner_iteration_count",0))
                        
                        if action == "clarification_needed":
                            st.session_state.ui_stage = "CLARIFICATION"
                            update_task_field(task_id, "status", "clarification_needed")
                        elif action == "plan_ready_for_code":
                            st.session_state.ui_stage = "DESIGN_TESTS"
                            update_task_field(task_id, "planned_task_description", json.dumps(st.session_state.get("planned_task_description")))
                            update_task_field(task_id, "planner_notes", st.session_state.get("planner_notes"))
                            update_task_field(task_id, "status", "plan_ready")
                        else: 
                            st.session_state.current_error_message = st.session_state.get("current_error_message", "Planning failed.")
                            update_task_field(task_id, "status", "planning_error")
                            update_task_field(task_id, "current_error_message", st.session_state.current_error_message)
                    except Exception as e:
                        logger.error(f"Error during elicitation flow: {e}", exc_info=True)
                        st.session_state.current_error_message = f"Critical error in planning: {e}"
                        if task_id: update_task_field(task_id, "status", "planning_error_critical")
                st.rerun()
            else:
                st.error("Failed to create a new task in the database.")

elif st.session_state.ui_stage == "CLARIFICATION":
    st.header("1b. Clarification Needed")
    st.info("The planner needs more information. Please answer the questions below:")
    questions = st.session_state.get("clarification_questions_for_user", [])
    user_answers_map = {} 
    for i, q_text in enumerate(questions):
        user_answers_map[f"answer_{i}"] = st.text_area(f"Q{i+1}: {q_text}", key=f"clar_q_{i}")

    if st.button("Submit Clarifications", key="submit_clarifications_btn"):
        refined_parts = [st.session_state.current_request_for_planner] # Start with current (which was initial or previously refined)
        for i, q_text in enumerate(questions): refined_parts.append(f"\nRegarding '{q_text}': {user_answers_map[f'answer_{i}']}")
        st.session_state.current_request_for_planner = " ".join(refined_parts) # Update current request
        st.session_state.clarification_questions_for_user = None 
        if st.session_state.active_task_id: log_feedback(st.session_state.active_task_id, None, "user_clarification", st.session_state.current_request_for_planner)

        if st.session_state.planner_iteration_count >= MAX_PLANNER_ITERATIONS:
            st.session_state.current_error_message = "Maximum planner iterations reached."
            st.session_state.ui_stage = "FAILED_PLANNING"
            if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "failed_planning_max_iterations")
        else:
            shared_for_flow = get_shared_for_flow()
            # ArchitectPlannerNode can be run directly here if its prep handles existing arch_decision
            # Or we can create a sub-flow just for PlannerNode if Architect part is truly one-off
            # For simplicity, ArchitectPlannerNode's prep can use existing arch_decision if present.
            
            with st.spinner("Planner re-evaluating..."):
                try:
                    action = architect_planner_node.run(shared_for_flow) 
                    st.session_state.update(shared_for_flow)
                    
                    if st.session_state.active_task_id:
                        update_task_field(st.session_state.active_task_id, "planner_iteration_count", st.session_state.planner_iteration_count)

                    if action == "clarification_needed": st.session_state.ui_stage = "CLARIFICATION"
                    elif action == "plan_ready_for_code":
                        st.session_state.ui_stage = "DESIGN_TESTS"
                        if st.session_state.active_task_id:
                            update_task_field(st.session_state.active_task_id, "planned_task_description", json.dumps(st.session_state.planned_task_description))
                            update_task_field(st.session_state.active_task_id, "planner_notes", st.session_state.planner_notes)
                            update_task_field(st.session_state.active_task_id, "status", "plan_ready")
                    else: 
                        st.session_state.current_error_message = st.session_state.get("current_error_message", "Planning failed post-clarification.")
                        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "planning_error")
                except Exception as e:
                    logger.error(f"Error in planner re-eval: {e}", exc_info=True)
                    st.session_state.current_error_message = f"Critical error in re-planning: {e}"
                    if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "planning_error_critical")
        st.rerun()

elif st.session_state.ui_stage == "DESIGN_TESTS":
    st.header("2a. Designing Test Cases")
    st.info("AI Test Case Designer is creating tests...")
    shared_for_flow = get_shared_for_flow()
    
    if not st.session_state.get("planned_task_description"):
        st.session_state.current_error_message = "Cannot design tests: Planned task description is missing."
        st.session_state.ui_stage = "FAILED_PLANNING" 
        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "error_missing_plan_for_tests")
        st.rerun()
    else:
        with st.spinner("Designing test cases..."):
            try:
                action = test_design_flow.run(shared_for_flow)
                st.session_state.update(shared_for_flow)
                if st.session_state.active_task_id and st.session_state.get("generated_test_cases"):
                    update_task_field(st.session_state.active_task_id, "generated_test_cases_json", json.dumps(st.session_state.generated_test_cases))
                
                if st.session_state.get("current_error_message") or not st.session_state.get("generated_test_cases"):
                    st.session_state.current_error_message = st.session_state.get("current_error_message", "Failed to design test cases.")
                    if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "test_design_error")
                    st.session_state.ui_stage = "FAILED_PLANNING" 
                else:
                    st.session_state.ui_stage = "INITIAL_CODE_GENERATION"
            except Exception as e:
                logger.error(f"Error during test design flow: {e}", exc_info=True)
                st.session_state.current_error_message = f"Critical error in test design: {e}"
                if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "test_design_error_critical")
        st.rerun()

elif st.session_state.ui_stage == "INITIAL_CODE_GENERATION":
    st.header("2b. Generating Initial Code")
    st.info("AI Developer is writing the first version of the code...")
    
    shared_for_flow = get_shared_for_flow()
    
    planned_desc = st.session_state.get("planned_task_description")
    if isinstance(planned_desc, dict):
        shared_for_flow["developer_task_description"] = json.dumps(planned_desc, indent=2)
    elif isinstance(planned_desc, str): 
        try: json.loads(planned_desc); shared_for_flow["developer_task_description"] = planned_desc
        except json.JSONDecodeError:
            st.session_state.current_error_message = "Critical: Planned task description is invalid JSON string."
            st.session_state.ui_stage = "FAILED_PLANNING"
            if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "error_invalid_plan_format")
            st.rerun(); sys.exit()
    else:
        st.session_state.current_error_message = "Critical: Planned task description missing for code generation."
        st.session_state.ui_stage = "FAILED_PLANNING" 
        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "error_missing_plan")
        st.rerun(); sys.exit()

    if not shared_for_flow.get("developer_task_description"): # Should be caught above
        st.session_state.current_error_message = "Internal Error: developer_task_description not prepared."
        st.session_state.ui_stage = "FAILED_PLANNING"
        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "internal_dev_prep_error")
        st.rerun(); sys.exit()
    
    # Reset for initial code generation
    shared_for_flow["critique_feedback"]= "N/A (first attempt)" 
    shared_for_flow["feedback_history"]= []
    shared_for_flow["refinement_count"]= 0 

    logger.debug(f"Passing to initial_code_gen_flow. Developer task description (first 100 chars): {shared_for_flow['developer_task_description'][:100]}")

    with st.spinner("Developer agent is coding..."):
        try:
            action = initial_code_gen_flow.run(shared_for_flow) 
            st.session_state.update(shared_for_flow)
            
            if action == "code_generation_failed" or not st.session_state.get("generated_code"):
                st.session_state.current_error_message = st.session_state.get("current_error_message", "Developer failed to generate code.")
                st.session_state.ui_stage = "HUMAN_REVIEW" 
                if st.session_state.active_task_id:
                     update_task_field(st.session_state.active_task_id, "status", "initial_code_failed")
                     if st.session_state.current_error_message: 
                        log_feedback(st.session_state.active_task_id, None, "system_error_dev", st.session_state.current_error_message)
            else: 
                st.session_state.ui_stage = "QA_VALIDATE_REVIEW"
                if st.session_state.active_task_id:
                    cv_id = add_code_version(st.session_state.active_task_id, st.session_state.generated_code, 0)
                    st.session_state.active_code_version_id = cv_id
                    update_task_field(st.session_state.active_task_id, "status", "code_ready_for_qa")
                    update_task_field(st.session_state.active_task_id, "refinement_count", 0)
        except Exception as e:
            logger.error(f"Error during initial code gen flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critical error in initial code gen: {e}"
            if st.session_state.active_task_id: 
                update_task_field(st.session_state.active_task_id, "status", "initial_code_error_critical")
                update_task_field(st.session_state.active_task_id, "current_error_message", str(e))
    st.rerun()

elif st.session_state.ui_stage == "QA_VALIDATE_REVIEW":
    st.header(f"2c. Automated QA & Validation (Attempt {st.session_state.refinement_count + 1})")
    st.info("AI QA Agent is running tests and Validation Agent is checking standards...")
    
    shared_for_flow = get_shared_for_flow()
    shared_for_flow["current_test_case_index"] = 0 
    shared_for_flow["test_results_summary"] = []   
    shared_for_flow["all_tests_passed"] = False # Reset for this round
    
    if not shared_for_flow.get("generated_code") or not shared_for_flow.get("generated_test_cases"):
        st.session_state.current_error_message = "Cannot run QA/Validation: Missing generated code or test cases."
        st.session_state.ui_stage = "HUMAN_REVIEW" # Or an error stage
        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "error_missing_qa_inputs")
        st.rerun()
    else:
        with st.spinner(f"Running tests and validation (Attempt {st.session_state.refinement_count + 1})..."):
            try:
                action = qa_validation_flow.run(shared_for_flow) 
                st.session_state.update(shared_for_flow)

                if st.session_state.active_task_id and st.session_state.active_code_version_id:
                    for res in st.session_state.get("test_results_summary", []):
                        log_test_run_result(st.session_state.active_task_id, st.session_state.active_code_version_id, 
                                            res.get("test_case",{}).get("description","N/A"), res.get("status","error"), 
                                            res.get("actual_output"), res.get("message","N/A"))
                    if st.session_state.get("validation_status"):
                         log_validation_result(st.session_state.active_task_id, st.session_state.active_code_version_id, 
                                               st.session_state.validation_status, st.session_state.get("validation_issues"))
                    update_task_field(st.session_state.active_task_id, "status", "human_review_pending")
                
                st.session_state.ui_stage = "HUMAN_REVIEW"
            except Exception as e:
                logger.error(f"Error during QA/Validation flow: {e}", exc_info=True)
                st.session_state.current_error_message = f"Critical error in QA/Validation: {e}"
                if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "qa_validation_error_critical")
        st.rerun()

elif st.session_state.ui_stage == "HUMAN_REVIEW":
    st.header(f"3. Your Review (Attempt {st.session_state.get('refinement_count', 0) +1})")
    st.info("Please review the generated code, test results, and validation notes.")
    
    # Display code, tests, validation (as before)
    st.subheader("Generated Code:"); st.code(st.session_state.get("generated_code", "# No code generated yet."), language="python")
    st.subheader("Test Cases & Results:")
    test_summary = st.session_state.get("test_results_summary", [])
    if test_summary:
        for i, tc_result in enumerate(test_summary):
            tc = tc_result.get("test_case", {})
            status_icon = "✅" if tc_result.get("status") == "success" else "❌"
            with st.expander(f"Test {i+1}: {status_icon} {tc.get('description', 'N/A')}", expanded=(tc_result.get("status") != "success")):
                st.json({"inputs": tc.get("inputs"), "expected_output": tc.get("expected_output")})
                st.write(f"Status: {tc_result.get('status', 'Unknown')}")
                st.write(f"Message: {tc_result.get('message', 'N/A')}")
                if tc_result.get("status") != "success": st.write(f"Actual Output: {tc_result.get('actual_output')}")
    else: st.info("No test results available for this version.")

    st.subheader("Validation Status:")
    val_status = st.session_state.get("validation_status")
    if val_status == "pass": st.success("Validation Passed.")
    elif val_status in ["fail", "error"]:
        st.error(f"Validation: {val_status.capitalize()}")
        if st.session_state.get("validation_issues"):
            for issue in st.session_state.validation_issues: st.warning(f"- {issue}")
    else: st.info("Validation not run or status unknown for this version.")

    # Determine overall pass based on the most recent test and validation run
    overall_pass = st.session_state.get("all_tests_passed", False) and val_status == "pass"
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Approve Code", disabled=not overall_pass, key="approve_btn_key"):
            st.session_state.ui_stage = "PACKAGING_COMPLETED"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "status", "approved_by_human")
                log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "user_approval", "Code approved by user.")
            st.rerun()
    with col2:
        if st.button("❌ Reject & Request Refinement", key="reject_btn_key"):
            # Increment refinement count happens in DeveloperNode's post,
            # but we check against MAX_REFINEMENTS based on *current* count before critique.
            if st.session_state.refinement_count >= MAX_REFINEMENTS:
                st.session_state.ui_stage = "MAX_REFINEMENTS_FAILED"
                if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "failed_max_refinements")
            else:
                st.session_state.ui_stage = "PROVIDE_REJECTION_FEEDBACK"
            st.rerun()
    if not overall_pass:
        st.warning("Code cannot be approved until all automated tests pass and validation is successful.")

elif st.session_state.ui_stage == "PROVIDE_REJECTION_FEEDBACK":
    st.header("3b. Provide Feedback for Refinement")
    st.info(f"This will be refinement attempt {st.session_state.refinement_count + 1} of {MAX_REFINEMENTS}.")
    st.subheader("Current Code (that was rejected/failed):")
    st.code(st.session_state.get("generated_code", "# No code available."), language="python")
    
    rejection_reason = st.text_area("Reason for rejection / specific feedback for the AI developer:", 
                                    value=st.session_state.user_rejection_reason, height=100, key="rejection_input_key_feedback")
    if st.button("Submit Feedback & Trigger AI Refinement", key="submit_feedback_refine_btn"):
        automated_failures_exist = not st.session_state.get("all_tests_passed", False) or \
                                 st.session_state.get("validation_status") != "pass"
        if not rejection_reason.strip() and not automated_failures_exist:
            st.warning("Please provide a reason for rejection if there were no automated test/validation failures.")
        else:
            st.session_state.user_rejection_reason = rejection_reason
            st.session_state.ui_stage = "CRITIQUE_AND_REFINE_CODE"
            if st.session_state.active_task_id:
                log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "user_rejection", rejection_reason)
                update_task_field(st.session_state.active_task_id, "status", "refinement_pending_critique")
            st.rerun()

elif st.session_state.ui_stage == "CRITIQUE_AND_REFINE_CODE":
    st.header(f"4. AI Critiquing & Refining Code (Attempt {st.session_state.refinement_count + 1})")
    st.info("AI agents are working on a revision...")
    
    shared_for_flow = get_shared_for_flow()
    # DeveloperNode's prep expects 'developer_task_description', not 'task_description' from older stages
    shared_for_flow["developer_task_description"] = str(st.session_state.get("planned_task_description"))

    with st.spinner("AI Critique and Developer agents are revising..."):
        try:
            action = critique_refine_flow.run(shared_for_flow) 
            st.session_state.update(shared_for_flow) 

            if st.session_state.active_task_id:
                if st.session_state.get("critique_feedback"): # critique_feedback is set by CritiqueNode
                    log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "ai_critique", st.session_state.critique_feedback)
                
                # refinement_count is incremented inside DeveloperNode.post
                update_task_field(st.session_state.active_task_id, "refinement_count", st.session_state.refinement_count)

                if action == "code_ready_for_tests":
                    # Save new code version
                    cv_id = add_code_version(st.session_state.active_task_id, st.session_state.generated_code, st.session_state.refinement_count)
                    st.session_state.active_code_version_id = cv_id 
                    update_task_field(st.session_state.active_task_id, "status", "code_ready_for_qa_refined")
                    st.session_state.ui_stage = "QA_VALIDATE_REVIEW" 
                else: # e.g. code_generation_failed
                    st.session_state.current_error_message = st.session_state.get("current_error_message", "Developer failed to refine code.")
                    update_task_field(st.session_state.active_task_id, "status", "refinement_failed_codegen")
                    update_task_field(st.session_state.active_task_id, "current_error_message", st.session_state.current_error_message)
                    st.session_state.ui_stage = "HUMAN_REVIEW" 
        except Exception as e:
            logger.error(f"Error during critique/refine: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critical error in critique/refine: {e}"
            if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "refinement_error_critical")
    st.rerun()

elif st.session_state.ui_stage == "PACKAGING_COMPLETED":
    st.header("5. Task Completed Successfully! 🎉")
    shared_for_flow = get_shared_for_flow() # Contains final approved code

    with st.spinner("Packaging final artifacts..."):
        try:
            action = packaging_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            if st.session_state.active_task_id and st.session_state.get("packaged_artifacts_info"):
                add_packaged_artifact(st.session_state.active_task_id, st.session_state.packaged_artifacts_info, st.session_state.get("handoff_summary", ""))
                update_task_field(st.session_state.active_task_id, "status", "completed")
        except Exception as e:
            logger.error(f"Error during packaging: {e}", exc_info=True); st.session_state.current_error_message = f"Error packaging: {e}"
    st.balloons()
    st.subheader("Final Generated Code:"); st.code(st.session_state.get("generated_code", "# Error."), language="python")
    if st.session_state.get("packaged_artifacts_info"): st.subheader("Packaged Info:"); st.json(st.session_state.packaged_artifacts_info)
    if st.session_state.get("handoff_summary"): st.success(st.session_state.handoff_summary)
    if st.button("Start New Function Request", key="start_new_completed_btn"): reset_for_new_task(); st.rerun()

elif st.session_state.ui_stage in ["FAILED_PLANNING", "MAX_REFINEMENTS_FAILED"]:
    if st.session_state.ui_stage == "MAX_REFINEMENTS_FAILED":
        st.header("😔 Task Failed: Maximum Refinements Reached")
        st.error(f"The AI could not produce satisfactory code after {st.session_state.refinement_count} refinement attempt(s).")
    elif st.session_state.ui_stage == "FAILED_PLANNING":
        st.header("😔 Task Failed: Planning Stage")
        st.error(f"The AI planner couldn't create a plan after {st.session_state.planner_iteration_count} iteration(s), or encountered an unrecoverable error.")
    
    if st.session_state.get("generated_code"): st.subheader("Last Generated Code:"); st.code(st.session_state.generated_code, language="python")
    if st.session_state.get("critique_feedback"): st.subheader("Last AI Critique:"); st.warning(st.session_state.critique_feedback)
    # display_error() will show current_error_message
    if st.button("Start New Request", key="start_new_failed_btn"): reset_for_new_task(); st.rerun()

# Display any global error messages at the bottom
display_error() 

# Sidebar for debug info (mostly unchanged from previous version)
with st.sidebar:
    st.header("Debug Info")
    if st.session_state.active_task_id: st.write(f"Active Task ID: {st.session_state.active_task_id}")
    st.write(f"Current UI Stage: {st.session_state.ui_stage}")
    st.write(f"Planner Iterations: {st.session_state.planner_iteration_count}/{MAX_PLANNER_ITERATIONS}")
    st.write(f"Refinement Count: {st.session_state.refinement_count}/{MAX_REFINEMENTS}") # Shows current attempts vs max allowed
    
    if st.button("Force Reset Full UI State", key="force_reset_sidebar_btn"):
        st.session_state.clear() 
        st.session_state.app_initialized = False 
        st.rerun()
    with st.expander("Session State Details (Truncated)", expanded=False):
        display_dict = {}
        for k,v in st.session_state.items():
            if k not in RAG_CONTEXT_KEYS: # Exclude large RAG contexts
                 display_dict[k] = (str(v)[:150] + '...' if isinstance(v, str) and len(str(v)) > 150 else v)
        st.json(display_dict)