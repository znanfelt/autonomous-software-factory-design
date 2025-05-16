# --- Streamlit Page Configuration ---
import streamlit as st
st.set_page_config(layout="wide")

# --- Imports ---
import os
import json
import logging
from pathlib import Path
import sys

# Ensure the package is discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pocketflow import Flow  # PocketFlow
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
)
from utils.database import (
    init_db, create_task, update_task_field, get_task_data,
    add_code_version, get_latest_code_version,
    log_test_run_result, get_test_results_for_version,
    log_validation_result, log_feedback, get_feedback_history_for_version,
    add_packaged_artifact
)
from utils.prompts import (
    ARCHITECT_PROMPT_TEMPLATE, PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
    PLANNER_CODEGEN_PROMPT_TEMPLATE, DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
    TEST_CASE_DESIGNER_PROMPT_TEMPLATE, VALIDATION_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT_TEMPLATE
)

# --- Logger Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constants ---
RAG_CONTEXTS_DIR = Path(__file__).parent / "rag_contexts"
MAX_PLANNER_ITERATIONS = int(os.getenv("MAX_PLANNER_ITERATIONS", "2"))
MAX_REFINEMENTS = int(os.getenv("MAX_REFINEMENTS", "3"))
LLM_MODELS_CONFIG = {
    "architect_llm":  os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o"),
    "planner_llm":    os.getenv("PLANNER_LLM_MODEL", "gpt-4o"),
    "developer_llm":  os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"), # Cheaper for code gen
    "test_designer_llm": os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"), # Re-use
    "qa_llm":         os.getenv("QA_LLM_MODEL", "gpt-4o"), # QA might need more capability for tool use prompt
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

ARCH_PRINCIPLES_CTX = load_rag_context("architectural_principles.txt")
PLAN_GUIDELINES_CTX = load_rag_context("planning_guidelines.txt")
CODE_STANDARDS_CTX = load_rag_context("coding_standards.txt")
VALIDATION_RULES_CTX = load_rag_context("validation_rules.txt")
DEBUGGING_TIPS_CTX = load_rag_context("debugging_tips.txt")

# --- PocketFlow Setup ---
# Instantiate nodes (could be done within flow creation too)
initial_request_node = InitialRequestNode()
architect_planner_node = ArchitectPlannerNode()
developer_node = DeveloperNode()
test_case_designer_node = TestCaseDesignerNode()
qa_node = QANode()
validation_node = ValidationNode()
critique_node = CritiqueNode()
package_node = PackageNode()

# Define elicitation flow
initial_request_node >> architect_planner_node
elicitation_flow = Flow(start=initial_request_node)

# Define test generation and execution flow segment
# Starts from test_case_designer, then dev, then QA loop, then validation
test_case_designer_node >> developer_node
developer_node - "code_ready_for_tests" >> qa_node
developer_node - "code_generation_failed" >> critique_node # Handle direct code gen failure
qa_node - "run_next_test" >> qa_node
qa_node - "testing_error_or_done" >> validation_node
validation_node - "validation_done" >> None # End of this segment, UI decides next
validation_node - "error_encountered" >> None
testing_flow_segment = Flow(start=test_case_designer_node) # Starts with designing tests for a plan

# Define refinement flow segment (Critique -> Developer)
critique_node - "refine_code" >> developer_node
refinement_flow_segment = Flow(start=critique_node)

# Define packaging flow
packaging_flow = Flow(start=package_node)


# --- Streamlit UI ---
st.title("🚧 Simple Autonomous Software Factory (MVP) 🏭")
st.caption("Describe a Python function, and AI agents will try to build, test, and validate it with your guidance.")

# --- Initialize Session State ---
if "ui_stage" not in st.session_state:
    st.session_state.ui_stage = "INPUT_REQUIREMENTS"
    st.session_state.active_task_id = None
    st.session_state.user_raw_request = ""
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
    init_db() # Ensure DB and tables exist

# --- RAG Contexts (Load once and store in session state if not already there) ---
if "rag_contexts_loaded" not in st.session_state:
    st.session_state.architectural_principles_context = ARCH_PRINCIPLES_CTX
    st.session_state.planning_guidelines_context = PLAN_GUIDELINES_CTX
    st.session_state.coding_standards_context = CODE_STANDARDS_CTX
    st.session_state.validation_rules_context = VALIDATION_RULES_CTX
    st.session_state.debugging_tips_context = DEBUGGING_TIPS_CTX
    st.session_state.rag_contexts_loaded = True


# --- Collapsible and Editable Agents Section ---
st.header("AI Agents Configuration")

with st.expander("Architect Agent Configuration", expanded=False):
    st.text_area(
        "Architect Agent Prompt Template",
        value=ARCHITECT_PROMPT_TEMPLATE,
        height=200,
        key="architect_prompt_template"
    )

with st.expander("Planner Agent Configuration", expanded=False):
    st.text_area(
        "Planner Clarification Prompt Template",
        value=PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
        height=200,
        key="planner_clarification_prompt_template"
    )
    st.text_area(
        "Planner Codegen Prompt Template",
        value=PLANNER_CODEGEN_PROMPT_TEMPLATE,
        height=200,
        key="planner_codegen_prompt_template"
    )

with st.expander("Developer Agent Configuration", expanded=False):
    st.text_area(
        "Developer Codegen Prompt Template",
        value=DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
        height=200,
        key="developer_codegen_prompt_template"
    )

with st.expander("Test Case Designer Agent Configuration", expanded=False):
    st.text_area(
        "Test Case Designer Prompt Template",
        value=TEST_CASE_DESIGNER_PROMPT_TEMPLATE,
        height=200,
        key="test_case_designer_prompt_template"
    )

with st.expander("Validation Agent Configuration", expanded=False):
    st.text_area(
        "Validation Prompt Template",
        value=VALIDATION_PROMPT_TEMPLATE,
        height=200,
        key="validation_prompt_template"
    )

with st.expander("Critique Agent Configuration", expanded=False):
    st.text_area(
        "Critique Prompt Template",
        value=CRITIQUE_PROMPT_TEMPLATE,
        height=200,
        key="critique_prompt_template"
    )

# --- Helper functions for UI stages ---
def reset_for_new_task():
    st.session_state.ui_stage = "INPUT_REQUIREMENTS"
    st.session_state.active_task_id = None
    st.session_state.user_raw_request = "" # Cleared for new input
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
        st.session_state.current_error_message = None # Clear after displaying

# --- UI Rendering based on Stage ---

if st.session_state.ui_stage == "INPUT_REQUIREMENTS":
    st.header("1. Describe Your Python Function")
    user_input = st.text_area("What function would you like the AI to create?", 
                              value=st.session_state.user_raw_request, height=150, key="raw_req_input")
    
    if st.button("Generate Function Plan"):
        if not user_input.strip():
            st.warning("Please describe the function you need.")
        else:
            st.session_state.user_raw_request = user_input
            st.session_state.current_request_for_planner = user_input # Initial request
            
            task_id = create_task(st.session_state.user_raw_request)
            if task_id:
                st.session_state.active_task_id = task_id
                logger.info(f"New task created with ID: {task_id} for request: {user_input[:50]}...")
                
                # Prepare shared state for PocketFlow
                shared_for_flow = {
                    "user_raw_request": st.session_state.user_raw_request,
                    "current_request_for_planner": st.session_state.current_request_for_planner,
                    "architectural_principles_context": st.session_state.architectural_principles_context,
                    "planning_guidelines_context": st.session_state.planning_guidelines_context,
                    "planner_iteration_count": 0, # Reset for new task
                    "llm_models_config": LLM_MODELS_CONFIG
                }
                
                with st.spinner("Architect & Planner are thinking..."):
                    try:
                        action = elicitation_flow.run(shared_for_flow)
                        # Update session state from shared_for_flow
                        st.session_state.update(shared_for_flow)
                        update_task_field(task_id, "architectural_decision", json.dumps(shared_for_flow.get("architectural_decision")) if shared_for_flow.get("architectural_decision") else None)
                        update_task_field(task_id, "planner_iteration_count", shared_for_flow.get("planner_iteration_count", 0))
                        
                        if action == "clarification_needed":
                            st.session_state.ui_stage = "CLARIFICATION"
                            update_task_field(task_id, "status", "clarification_needed")
                        elif action == "plan_ready_for_code":
                            st.session_state.ui_stage = "TEST_GENERATION"
                            update_task_field(task_id, "planned_task_description", json.dumps(shared_for_flow.get("planned_task_description")))
                            update_task_field(task_id, "planner_notes", shared_for_flow.get("planner_notes"))
                            update_task_field(task_id, "status", "plan_ready")
                        else: # Error or unexpected
                            st.session_state.current_error_message = shared_for_flow.get("current_error_message", "Planning failed.")
                            update_task_field(task_id, "current_error_message", st.session_state.current_error_message)
                            update_task_field(task_id, "status", "planning_error")
                    except Exception as e:
                        logger.error(f"Error during elicitation flow: {e}", exc_info=True)
                        st.session_state.current_error_message = f"Critical error in planning: {e}"
                        update_task_field(task_id, "current_error_message", st.session_state.current_error_message)
                        update_task_field(task_id, "status", "planning_error")
                st.rerun()
            else:
                st.error("Failed to create a new task in the database.")

elif st.session_state.ui_stage == "CLARIFICATION":
    st.header("1b. Clarification Needed")
    st.info("The planner needs more information to proceed. Please answer the questions below:")
    
    questions = st.session_state.get("clarification_questions_for_user", [])
    user_answers = {}
    for i, q_text in enumerate(questions):
        user_answers[f"answer_{i}"] = st.text_area(f"Question {i+1}: {q_text}", key=f"clar_q_{i}")

    if st.button("Submit Clarifications"):
        refined_request_parts = [st.session_state.current_request_for_planner] # Start with previous request
        for i, q_text in enumerate(questions):
            refined_request_parts.append(f"\nRegarding '{q_text}': {user_answers[f'answer_{i}']}")
        
        st.session_state.current_request_for_planner = " ".join(refined_request_parts)
        st.session_state.clarification_questions_for_user = None # Clear questions
        
        # Log this interaction (optional, could be a feedback log)
        log_feedback(st.session_state.active_task_id, None, "user_clarification", st.session_state.current_request_for_planner)
        
        if st.session_state.planner_iteration_count >= MAX_PLANNER_ITERATIONS:
            st.session_state.current_error_message = "Maximum planner iterations reached. Please refine your initial request and start over."
            st.session_state.ui_stage = "FAILED_PLANNING"
            update_task_field(st.session_state.active_task_id, "status", "failed_planning_max_iterations")
        else:
            # Re-run planner part of elicitation_flow
            shared_for_flow = {
                "user_raw_request": st.session_state.user_raw_request, # Keep original for reference
                "current_request_for_planner": st.session_state.current_request_for_planner,
                "architectural_decision": st.session_state.architectural_decision, # Pass existing
                "architectural_principles_context": st.session_state.architectural_principles_context,
                "planning_guidelines_context": st.session_state.planning_guidelines_context,
                "planner_iteration_count": st.session_state.planner_iteration_count,
                "llm_models_config": LLM_MODELS_CONFIG
            }
            with st.spinner("Planner is re-evaluating with your clarifications..."):
                try:
                    # Directly run architect_planner_node as we are iterating on planning
                    action = architect_planner_node.run(shared_for_flow) 
                    st.session_state.update(shared_for_flow) # Update session state with results
                    update_task_field(st.session_state.active_task_id, "planner_iteration_count", shared_for_flow.get("planner_iteration_count", 0))

                    if action == "clarification_needed":
                        st.session_state.ui_stage = "CLARIFICATION" # Stay if more questions
                        update_task_field(st.session_state.active_task_id, "status", "clarification_needed")
                    elif action == "plan_ready_for_code":
                        st.session_state.ui_stage = "TEST_GENERATION"
                        update_task_field(st.session_state.active_task_id, "planned_task_description", json.dumps(shared_for_flow.get("planned_task_description")))
                        update_task_field(st.session_state.active_task_id, "planner_notes", shared_for_flow.get("planner_notes"))
                        update_task_field(st.session_state.active_task_id, "status", "plan_ready")
                    else:
                        st.session_state.current_error_message = shared_for_flow.get("current_error_message", "Planning failed after clarification.")
                        update_task_field(st.session_state.active_task_id, "current_error_message", st.session_state.current_error_message)
                        update_task_field(st.session_state.active_task_id, "status", "planning_error")
                except Exception as e:
                    logger.error(f"Error during planner re-evaluation: {e}", exc_info=True)
                    st.session_state.current_error_message = f"Critical error in re-planning: {e}"
                    update_task_field(st.session_state.active_task_id, "current_error_message", st.session_state.current_error_message)
                    update_task_field(st.session_state.active_task_id, "status", "planning_error")
        st.rerun()

elif st.session_state.ui_stage == "TEST_GENERATION":
    st.header("2. Generating Code & Tests")
    st.info("AI is now generating test cases and the initial code based on the plan...")
    
    shared_for_flow = {
        "planned_task_description": st.session_state.planned_task_description,
        "planner_notes": st.session_state.planner_notes,
        "coding_standards_context": st.session_state.coding_standards_context,
        "feedback_history": [], # Fresh start for code gen
        "refinement_count": 0, # First attempt
        "llm_models_config": LLM_MODELS_CONFIG,
        # For QA node later
        "test_results_summary": [],
        "all_tests_passed": False,
        "current_test_case_index": 0
    }

    with st.spinner("Designing test cases and writing initial code..."):
        try:
            # Run the testing_flow_segment which starts with TestCaseDesignerNode
            # This flow will design tests, then generate code, then run QA, then validate
            action = testing_flow_segment.run(shared_for_flow)
            st.session_state.update(shared_for_flow) # Update with all results
            
            # Persist to DB
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "status", "review_pending")
                if shared_for_flow.get("generated_code"):
                    cv_id = add_code_version(st.session_state.active_task_id, shared_for_flow["generated_code"], shared_for_flow.get("refinement_count", 0))
                    st.session_state.active_code_version_id = cv_id
                    if shared_for_flow.get("test_results_summary"):
                        for res in shared_for_flow["test_results_summary"]:
                            log_test_run_result(st.session_state.active_task_id, cv_id, res["test_case"].get("description","N/A"), res["status"], res.get("actual_output"), res["message"])
                if shared_for_flow.get("validation_status"):
                     log_validation_result(st.session_state.active_task_id, st.session_state.active_code_version_id, shared_for_flow["validation_status"], shared_for_flow.get("validation_issues"))
            
            st.session_state.ui_stage = "HUMAN_REVIEW"
        except Exception as e:
            logger.error(f"Error during test generation/code/QA flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critical error in test/code/QA stage: {e}"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "current_error_message", str(e))
                update_task_field(st.session_state.active_task_id, "status", "error_in_test_code_qa")
    st.rerun()


elif st.session_state.ui_stage == "HUMAN_REVIEW":
    st.header("3. Review Code, Tests, and Validation")
    
    st.subheader("Generated Code:")
    st.code(st.session_state.get("generated_code", "# No code generated yet."), language="python")

    st.subheader("Test Cases & Results:")
    if st.session_state.get("generated_test_cases"):
        for i, tc_result in enumerate(st.session_state.get("test_results_summary", [])):
            tc = tc_result["test_case"]
            status_icon = "✅" if tc_result["status"] == "success" else "❌"
            with st.expander(f"Test {i+1}: {status_icon} {tc.get('description', 'N/A')}", expanded=(tc_result["status"] != "success")):
                st.json({"inputs": tc["inputs"], "expected_output": tc["expected_output"]})
                st.write(f"Status: {tc_result['status']}")
                st.write(f"Message: {tc_result['message']}")
                if tc_result["status"] != "success":
                    st.write(f"Actual Output: {tc_result.get('actual_output')}")
    else:
        st.info("No test cases were generated or run.")

    st.subheader("Validation Status:")
    val_status = st.session_state.get("validation_status", "Not run")
    if val_status == "pass":
        st.success("Validation Passed.")
    elif val_status in ["fail", "error"]:
        st.error(f"Validation Failed/Errored: {val_status}")
        issues = st.session_state.get("validation_issues", [])
        if issues:
            st.write("Issues Found:")
            for issue in issues: st.warning(f"- {issue}")
        else:
            st.write("No specific issues listed by validator.")
    else:
        st.info("Validation not yet run or status unknown.")

    overall_pass = st.session_state.get("all_tests_passed", False) and st.session_state.get("validation_status") == "pass"
    
    col1, col2, col3 = st.columns([1,1,3])
    with col1:
        if st.button("✅ Approve Code", disabled=not overall_pass):
            st.session_state.ui_stage = "COMPLETED"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "status", "approved_by_human")
                log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "user_approval", "Code approved by user.")
            st.rerun()
    
    with col2:
        if st.button("❌ Reject & Refine"):
            if st.session_state.refinement_count >= MAX_REFINEMENTS:
                st.session_state.ui_stage = "MAX_REFINEMENTS_FAILED"
                if st.session_state.active_task_id:
                     update_task_field(st.session_state.active_task_id, "status", "failed_max_refinements")
            else:
                st.session_state.ui_stage = "PROVIDE_REJECTION_FEEDBACK"
            st.rerun()

    if not overall_pass:
        st.warning("Code cannot be approved until all tests pass and validation is successful.")


elif st.session_state.ui_stage == "PROVIDE_REJECTION_FEEDBACK":
    st.header("3b. Provide Feedback for Refinement")
    st.info(f"This is refinement attempt {st.session_state.refinement_count + 1} of {MAX_REFINEMENTS}.")
    st.subheader("Current Code:")
    st.code(st.session_state.get("generated_code", ""), language="python")
    st.subheader("Test/Validation Issues:")
    if st.session_state.get("test_results_summary"):
        for res in st.session_state.test_results_summary:
            if res["status"] != "success": st.warning(f"Test Fail: {res['test_case'].get('description','N/A')} - {res['message']}")
    if st.session_state.get("validation_issues"):
        for issue in st.session_state.validation_issues: st.warning(f"Validation Issue: {issue}")

    rejection_reason = st.text_area("Reason for rejection / specific feedback for the AI developer:", 
                                    value=st.session_state.user_rejection_reason, height=100, key="rejection_input")
    if st.button("Submit Feedback & Retry Generation"):
        if not rejection_reason.strip() and not st.session_state.get("test_results_summary") and not st.session_state.get("validation_issues"):
            st.warning("Please provide a reason if there are no automated failures.")
        else:
            st.session_state.user_rejection_reason = rejection_reason
            st.session_state.ui_stage = "CRITIQUE_AND_REFINE"
            if st.session_state.active_task_id:
                log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "user_rejection", rejection_reason)
            st.rerun()

elif st.session_state.ui_stage == "CRITIQUE_AND_REFINE":
    st.header("4. AI Critiquing & Refining Code")
    st.info("The AI Critique Agent is reviewing the issues and providing feedback to the Developer Agent...")

    shared_for_flow = {
        "task_description": st.session_state.task_description,
        "planner_notes": st.session_state.planner_notes,
        "generated_code": st.session_state.generated_code,
        "current_test_message": "\n".join([f"{r['test_case'].get('description')}: {r['message']}" for r in st.session_state.test_results_summary if r['status'] != 'success']),
        "validation_issues": st.session_state.validation_issues,
        "user_rejection_reason": st.session_state.user_rejection_reason, # Added
        "debugging_tips_context": st.session_state.debugging_tips_context,
        "feedback_history": st.session_state.feedback_history, # Pass current history
        "refinement_count": st.session_state.refinement_count, # Pass current count
        "llm_models_config": LLM_MODELS_CONFIG
    }
    
    with st.spinner("AI agents are collaborating on a revision..."):
        try:
            # Run refinement_flow_segment (Critique -> Developer)
            action = refinement_flow_segment.run(shared_for_flow)
            st.session_state.update(shared_for_flow) # Update with critique and new code
            
            if st.session_state.active_task_id and shared_for_flow.get("critique_feedback"):
                log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "ai_critique", shared_for_flow["critique_feedback"])
            
            if action == "code_ready_for_tests": # Means DeveloperNode in refinement flow finished
                st.session_state.ui_stage = "TEST_GENERATION_REFINED" # New stage to re-run tests on new code
                if st.session_state.active_task_id:
                    update_task_field(st.session_state.active_task_id, "status", "refining_code")
                    update_task_field(st.session_state.active_task_id, "refinement_count", shared_for_flow.get("refinement_count"))
            else: # e.g. code_generation_failed from DeveloperNode
                st.session_state.current_error_message = shared_for_flow.get("current_error_message", "Refinement failed.")
                if st.session_state.active_task_id:
                    update_task_field(st.session_state.active_task_id, "current_error_message", st.session_state.current_error_message)
                    update_task_field(st.session_state.active_task_id, "status", "refinement_error")
        except Exception as e:
            logger.error(f"Error during critique/refinement flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critical error in critique/refinement: {e}"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "current_error_message", str(e))
                update_task_field(st.session_state.active_task_id, "status", "refinement_error")
    st.rerun()

elif st.session_state.ui_stage == "TEST_GENERATION_REFINED":
    st.header(f"2b. Testing Refined Code (Attempt {st.session_state.refinement_count})")
    st.info("AI is now re-running tests and validation on the refined code...")
    
    shared_for_flow = {
        "generated_code": st.session_state.generated_code, # Use the newly refined code
        "generated_test_cases": st.session_state.generated_test_cases, # Re-use same test cases
        "current_test_case_index": 0, # Reset test index
        "test_results_summary": [],   # Reset summary for this round
        "all_tests_passed": False,
        "task_description": st.session_state.task_description, # For validation
        "planner_notes": st.session_state.planner_notes, # For validation
        "validation_rules_context": st.session_state.validation_rules_context,
        "llm_models_config": LLM_MODELS_CONFIG
    }
    
    with st.spinner(f"Re-testing and validating code (Attempt {st.session_state.refinement_count})..."):
        try:
            # We need a flow that starts from QA, then goes to Validation.
            # The testing_flow_segment starts from TestCaseDesigner, which we don't want here.
            # Let's manually run qa_node and then validation_node.
            
            # Run QA loop
            current_test_idx = 0
            temp_test_results = []
            all_passed_this_round = True

            while current_test_idx < len(shared_for_flow["generated_test_cases"]):
                shared_for_flow["current_test_case_index"] = current_test_idx
                qa_action = qa_node.run(shared_for_flow) # shared_for_flow will be updated by qa_node
                temp_test_results.append(shared_for_flow["test_results_summary"][-1]) # Store latest result
                if shared_for_flow["current_test_status"] != "success":
                    all_passed_this_round = False
                    # No need to break, run all tests to get full feedback
                current_test_idx +=1 # qa_node post already increments, but for clarity
            
            shared_for_flow["test_results_summary"] = temp_test_results
            shared_for_flow["all_tests_passed"] = all_passed_this_round

            # Run Validation
            validation_action = validation_node.run(shared_for_flow) # shared_for_flow updated

            st.session_state.update(shared_for_flow) # Update main session state
            
            # Persist to DB
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "status", "review_pending_refined")
                if shared_for_flow.get("generated_code"): # This is the refined code
                    # We might want to log this as a new version tied to the same task_id but new refinement_count
                    cv_id = add_code_version(st.session_state.active_task_id, shared_for_flow["generated_code"], shared_for_flow.get("refinement_count", 0))
                    st.session_state.active_code_version_id = cv_id # Update active code version
                    if shared_for_flow.get("test_results_summary"):
                        for res in shared_for_flow["test_results_summary"]:
                             log_test_run_result(st.session_state.active_task_id, cv_id, res["test_case"].get("description","N/A"), res["status"], res.get("actual_output"), res["message"])
                if shared_for_flow.get("validation_status"):
                    log_validation_result(st.session_state.active_task_id, st.session_state.active_code_version_id, shared_for_flow["validation_status"], shared_for_flow.get("validation_issues"))

            st.session_state.ui_stage = "HUMAN_REVIEW" # Back to human review
        except Exception as e:
            logger.error(f"Error during refined test/validation flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critical error in refined test/validation: {e}"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "current_error_message", str(e))
                update_task_field(st.session_state.active_task_id, "status", "error_in_refined_test_qa")
    st.rerun()

elif st.session_state.ui_stage == "COMPLETED":
    st.header("5. Task Completed Successfully! 🎉")
    
    shared_for_flow = {
        "generated_code": st.session_state.generated_code,
        "planned_task_description": st.session_state.planned_task_description
    }
    with st.spinner("Packaging final artifacts..."):
        try:
            action = packaging_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            
            if st.session_state.active_task_id and shared_for_flow.get("packaged_artifacts_info"):
                add_packaged_artifact(st.session_state.active_task_id, shared_for_flow["packaged_artifacts_info"], shared_for_flow.get("handoff_summary", ""))
                update_task_field(st.session_state.active_task_id, "status", "completed")
        except Exception as e:
            logger.error(f"Error during packaging flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Error packaging artifacts: {e}"


    st.balloons()
    st.subheader("Final Generated Code:")
    st.code(st.session_state.get("generated_code", "# Error retrieving final code."), language="python")
    if st.session_state.get("packaged_artifacts_info"):
        st.subheader("Packaged Artifacts Info:")
        st.json(st.session_state.packaged_artifacts_info)
    if st.session_state.get("handoff_summary"):
        st.success(st.session_state.handoff_summary)
    
    if st.button("Start New Function Request"):
        reset_for_new_task()
        st.rerun()

elif st.session_state.ui_stage in ["MAX_REFINEMENTS_FAILED", "FAILED_PLANNING"]:
    if st.session_state.ui_stage == "MAX_REFINEMENTS_FAILED":
        st.header("😔 Task Failed: Maximum Refinements Reached")
        st.error(f"The AI could not produce a satisfactory function after {MAX_REFINEMENTS} refinement attempts.")
        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "failed_max_refinements")
    elif st.session_state.ui_stage == "FAILED_PLANNING":
        st.header("😔 Task Failed: Planning Stage")
        st.error(f"The AI planner could not create a satisfactory plan after {st.session_state.planner_iteration_count} iterations or encountered an error.")
        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "failed_planning")

    st.subheader("Last Generated Code (if any):")
    st.code(st.session_state.get("generated_code", "# No code was generated or an error occurred before code generation."), language="python")
    st.subheader("Last Critique/Feedback (if any):")
    st.warning(st.session_state.get("critique_feedback", "No specific critique available."))
    if st.session_state.get("current_error_message"):
        st.error(f"Last Error: {st.session_state.current_error_message}")
    
    if st.button("Start New Function Request"):
        reset_for_new_task()
        st.rerun()

# Display any error messages at the bottom
display_error()

# --- Sidebar for Task History / Load (Future Enhancement) ---
# st.sidebar.title("Task History")
# task_list = get_all_tasks_summary() # New DB function needed
# if task_list:
#     for task_info in task_list:
#         if st.sidebar.button(f"Load Task {task_info['task_id']}: {task_info['initial_request'][:30]}...", key=f"load_{task_info['task_id']}"):
#             load_task_into_session_state(task_info['task_id']) # New helper needed
#             st.rerun()
# else:
#     st.sidebar.info("No tasks yet.")

with st.sidebar:
    st.header("Debug Info")
    if st.session_state.active_task_id:
        st.write(f"Active Task ID: {st.session_state.active_task_id}")
    st.write(f"Current UI Stage: {st.session_state.ui_stage}")
    st.write(f"Planner Iterations: {st.session_state.planner_iteration_count}/{MAX_PLANNER_ITERATIONS}")
    st.write(f"Refinement Iterations: {st.session_state.refinement_count}/{MAX_REFINEMENTS}")
    if st.button("Force Reset Full State"):
        for key in list(st.session_state.keys()): # Iterate over a copy of keys
            del st.session_state[key]
        st.rerun() # Re-initializes to default

    with st.expander("Session State Details"):
        st.json({k: str(v)[:200] + '...' if isinstance(v, str) and len(str(v)) > 200 else v for k,v in st.session_state.items()})

# hide_element_css = """
# <style>
# .stHelp {
#     display: none;
# }
# </style>
# """

# # Inject the CSS into the Streamlit app
# st.markdown(hide_element_css, unsafe_allow_html=True)