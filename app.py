# app.py
import streamlit as st
import os
import json
import logging
from pathlib import Path
import sys
from datetime import datetime 
from typing import Dict, Any, List, Optional 

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
    log_validation_result, log_feedback, get_feedback_history_for_task, 
    add_packaged_artifact, DB_FILE
)
from utils.prompts import ( 
    ARCHITECT_PROMPT_TEMPLATE, PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
    PLANNER_CODEGEN_PROMPT_TEMPLATE, DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
    TEST_CASE_DESIGNER_PROMPT_TEMPLATE, VALIDATION_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT_TEMPLATE
)
# Corrected import from flow.py:
from flow import ( 
    elicitation_flow, 
    test_design_flow, 
    code_generation_flow, # Ensure this is imported
    qa_validation_flow, 
    critique_generation_flow, # This was critique_refine_flow, let's ensure flow.py matches
    packaging_flow
)

# ... rest of the app.py code from the previous response ...
# (No other changes needed in app.py besides this import fix, 
# assuming flow.py defines code_generation_flow and critique_generation_flow)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

RAG_CONTEXTS_DIR = Path(__file__).parent / "rag_contexts"
RAG_CONTEXT_KEYS = [
    "architectural_principles_context", "planning_guidelines_context",
    "coding_standards_context", "validation_rules_context", "debugging_tips_context"
]
MAX_PLANNER_ITERATIONS = int(os.getenv("MAX_PLANNER_ITERATIONS", "2"))
MAX_REFINEMENTS = int(os.getenv("MAX_REFINEMENTS", "3"))
LLM_MODELS_CONFIG = {
    "architect_llm":  os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o"),
    "planner_llm":    os.getenv("PLANNER_LLM_MODEL", "gpt-4o"),
    "developer_llm":  os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"),
    "test_designer_llm": os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"),
    "validation_llm": os.getenv("VALIDATION_LLM_MODEL", "gpt-3.5-turbo"),
    "critique_llm":   os.getenv("CRITIQUE_LLM_MODEL", "gpt-4o-mini")
}

def load_rag_context(filename: str) -> str:
    try:
        with open(RAG_CONTEXTS_DIR / filename, "r", encoding="utf-8") as f: return f.read()
    except Exception as e: logger.error(f"Error RAG {filename}: {e}"); return f"Error RAG {filename}: {e}"

if "app_initialized" not in st.session_state:
    init_db() 
    st.session_state.ui_stage = "INPUT_REQUIREMENTS"; st.session_state.active_task_id = None
    st.session_state.user_raw_request = ""; st.session_state.current_request_for_planner = ""
    st.session_state.architectural_decision = None; st.session_state.planner_iteration_count = 0
    st.session_state.clarification_questions_for_user = None; st.session_state.planned_task_description = None
    st.session_state.suggested_project_outline = None; st.session_state.planner_notes = None
    st.session_state.generated_project_structure = None; st.session_state.active_code_version_id = None
    st.session_state.generated_test_cases = None; st.session_state.current_test_case_index = 0
    st.session_state.test_results_summary = []; st.session_state.all_tests_passed = False
    st.session_state.validation_status = None; st.session_state.validation_issues = None
    st.session_state.user_rejection_reason = ""; st.session_state.critique_feedback = None
    st.session_state.feedback_history = []; st.session_state.refinement_count = 0
    st.session_state.packaged_artifacts_info = None; st.session_state.handoff_summary = None
    st.session_state.current_error_message = None
    for key in RAG_CONTEXT_KEYS: st.session_state[key] = load_rag_context(f"{key.replace('_context', '')}.txt")
    st.session_state.rag_contexts_loaded = True; st.session_state.app_initialized = True
    logger.info("Streamlit App Initialized.")

def reset_for_new_task():
    preserve_keys = RAG_CONTEXT_KEYS + ["app_initialized", "rag_contexts_loaded"]
    preserved_values = {k: st.session_state.get(k) for k in preserve_keys}
    st.session_state.clear(); st.session_state.update(preserved_values)
    st.session_state.ui_stage = "INPUT_REQUIREMENTS"; st.session_state.active_task_id = None
    st.session_state.user_raw_request = ""; st.session_state.current_request_for_planner = ""
    st.session_state.architectural_decision = None; st.session_state.planner_iteration_count = 0
    st.session_state.clarification_questions_for_user = None; st.session_state.planned_task_description = None
    st.session_state.suggested_project_outline = None; st.session_state.planner_notes = None
    st.session_state.generated_project_structure = None; st.session_state.active_code_version_id = None
    st.session_state.generated_test_cases = None; st.session_state.current_test_case_index = 0
    st.session_state.test_results_summary = []; st.session_state.all_tests_passed = False
    st.session_state.validation_status = None; st.session_state.validation_issues = None
    st.session_state.user_rejection_reason = ""; st.session_state.critique_feedback = None
    st.session_state.feedback_history = []; st.session_state.refinement_count = 0
    st.session_state.packaged_artifacts_info = None; st.session_state.handoff_summary = None
    st.session_state.current_error_message = None; logger.info("UI state reset for new task.")

def display_error():
    if st.session_state.current_error_message: st.error(f"Error: {st.session_state.current_error_message}")

def get_shared_for_flow() -> Dict[str, Any]:
    shared = {}
    keys_to_copy = [
        "user_raw_request", "current_request_for_planner", "architectural_decision",
        "planner_iteration_count", "clarification_questions_for_user",
        "planned_task_description", "suggested_project_outline", "planner_notes",
        "generated_project_structure", "active_code_version_id", "generated_test_cases",
        "current_test_case_index", "test_results_summary", "all_tests_passed",
        "validation_status", "validation_issues", "user_rejection_reason",
        "critique_feedback", "feedback_history", "refinement_count",
        "packaged_artifacts_info", "handoff_summary", "current_error_message",
        "active_task_id"
    ] + RAG_CONTEXT_KEYS
    for key in keys_to_copy:
        if key in st.session_state: shared[key] = st.session_state[key]
    shared["llm_models_config"] = LLM_MODELS_CONFIG
    shared["max_planner_iterations"] = MAX_PLANNER_ITERATIONS
    shared["max_refinements"] = MAX_REFINEMENTS
    if isinstance(shared.get("planned_task_description"), dict):
        shared["developer_task_description"] = json.dumps(shared["planned_task_description"], indent=2)
        shared["task_description_json_str"] = json.dumps(shared["planned_task_description"], indent=2)
    if isinstance(shared.get("architectural_decision"), dict):
        shared["architect_decision_json_str"] = json.dumps(shared["architectural_decision"], indent=2)
    shared["suggested_project_outline_json_str"] = json.dumps(shared.get("suggested_project_outline",[]), indent=2)
    if isinstance(shared.get("generated_project_structure"), dict):
        shared["project_structure_json_str"] = json.dumps(shared["generated_project_structure"], indent=2)
    return shared

st.set_page_config(layout="wide"); st.title("🚧 SDLC Factory (MVP) 🏭")
st.caption("Describe a Python project. AI agents will build, test, & validate with your guidance.")
active_task_id = st.session_state.active_task_id

if st.session_state.ui_stage == "INPUT_REQUIREMENTS":
    st.header("1. Describe Your Python Project/Function")
    user_input = st.text_area("What would you like AI to create?", value=st.session_state.user_raw_request, height=150, key="raw_req_v5_app_fix1")
    if st.button("Start Planning", key="submit_init_req_v5_app_fix1"):
        if not user_input.strip(): st.warning("Please describe.")
        else:
            reset_for_new_task(); st.session_state.user_raw_request=user_input; st.session_state.current_request_for_planner=user_input 
            task_id = create_task(st.session_state.user_raw_request)
            if task_id:
                st.session_state.active_task_id=task_id; active_task_id=task_id
                logger.info(f"New task {task_id}: {user_input[:50]}...")
                shared_for_flow=get_shared_for_flow(); shared_for_flow["planner_iteration_count"]=0 
                with st.spinner("Architect & Planner thinking..."):
                    try:
                        action=elicitation_flow.run(shared_for_flow); st.session_state.update(shared_for_flow) 
                        st.session_state.planner_iteration_count = shared_for_flow.get("planner_iteration_count",0)
                        update_task_field(task_id,"architectural_decision",st.session_state.architectural_decision)
                        update_task_field(task_id,"planner_iteration_count",st.session_state.planner_iteration_count)
                        if action=="clarification_needed": st.session_state.ui_stage="CLARIFICATION"; update_task_field(task_id,"status","clarification_needed")
                        elif action=="plan_ready_for_code": 
                            st.session_state.ui_stage="DESIGN_TESTS"; update_task_field(task_id,"status","plan_ready")
                            update_task_field(task_id,"planned_task_description",st.session_state.planned_task_description); update_task_field(task_id,"planner_notes",st.session_state.planner_notes)
                        else: st.session_state.current_error_message=st.session_state.get("current_error_message","Planning fail."); update_task_field(task_id,"status","planning_error")
                    except Exception as e: logger.error(f"Elicitation error: {e}",exc_info=True); st.session_state.current_error_message=f"Planning error: {e}"; update_task_field(task_id,"status","planning_error_critical")
                st.rerun()
            else: st.error("Failed to create task in DB.")

elif st.session_state.ui_stage == "CLARIFICATION" and active_task_id:
    st.header("1b. Clarification Needed"); st.info("Planner needs more info:")
    questions = st.session_state.clarification_questions_for_user or []; ans_map = {} 
    for i, q in enumerate(questions): ans_map[f"ans_{i}"] = st.text_area(f"Q{i+1}: {q}", key=f"clar_q_{i}_task{active_task_id}_v5_app_fix1")
    if st.button("Submit Clarifications", key="submit_clar_btn_v5_app_fix1"):
        parts=[st.session_state.current_request_for_planner]; [parts.append(f"\nQ:'{q}' A:'{ans_map[f'ans_{i}']}'") for i,q in enumerate(questions)]
        st.session_state.current_request_for_planner=" ".join(parts); st.session_state.clarification_questions_for_user=None
        log_feedback(active_task_id,None,"user_clarification",st.session_state.current_request_for_planner)
        if st.session_state.planner_iteration_count>=MAX_PLANNER_ITERATIONS: st.session_state.current_error_message="Max planner iterations."; st.session_state.ui_stage="FAILED_PLANNING"; update_task_field(active_task_id,"status","failed_plan_max_iter")
        else:
            shared_for_flow=get_shared_for_flow()
            with st.spinner("Planner re-evaluating..."):
                try:
                    action=elicitation_flow.run(shared_for_flow); st.session_state.update(shared_for_flow)
                    st.session_state.planner_iteration_count = shared_for_flow.get("planner_iteration_count", st.session_state.planner_iteration_count)
                    update_task_field(active_task_id,"planner_iteration_count",st.session_state.planner_iteration_count)
                    if action=="clarification_needed": st.session_state.ui_stage="CLARIFICATION"
                    elif action=="plan_ready_for_code": st.session_state.ui_stage="DESIGN_TESTS"; update_task_field(active_task_id,"planned_task_description",st.session_state.planned_task_description); update_task_field(active_task_id,"planner_notes",st.session_state.planner_notes); update_task_field(active_task_id,"status","plan_ready")
                    else: st.session_state.current_error_message=st.session_state.get("current_error_message","Plan fail post-clarify.");update_task_field(active_task_id,"status","planning_error")
                except Exception as e: logger.error(f"Re-plan error: {e}",exc_info=True); st.session_state.current_error_message=f"Re-plan error: {e}"; update_task_field(active_task_id,"status","planning_error_critical")
        st.rerun()

elif st.session_state.ui_stage == "DESIGN_TESTS" and active_task_id:
    st.header("2a. Designing Test Cases"); st.info("AI Test Case Designer creating tests...")
    shared_for_flow = get_shared_for_flow()
    if not st.session_state.planned_task_description: st.session_state.current_error_message="Plan missing."; st.session_state.ui_stage="FAILED_PLANNING"; update_task_field(active_task_id,"status","error_miss_plan_tests"); st.rerun()
    else:
        with st.spinner("Designing tests..."):
            try:
                action=test_design_flow.run(shared_for_flow); st.session_state.update(shared_for_flow)
                if st.session_state.generated_test_cases: update_task_field(active_task_id,"generated_test_cases_json",st.session_state.generated_test_cases)
                if st.session_state.current_error_message or not st.session_state.generated_test_cases:
                    st.session_state.current_error_message=st.session_state.get("current_error_message","Test design fail."); st.session_state.ui_stage="FAILED_PLANNING"; update_task_field(active_task_id,"status","test_design_error")
                else: st.session_state.ui_stage="INITIAL_CODE_GENERATION"; update_task_field(active_task_id,"status","tests_designed")
            except Exception as e: logger.error(f"Test design error: {e}",exc_info=True); st.session_state.current_error_message=f"Test design error: {e}"; update_task_field(active_task_id,"status","test_design_error_critical")
        st.rerun()

elif st.session_state.ui_stage == "INITIAL_CODE_GENERATION" and active_task_id: # Uses code_generation_flow
    st.header("2b. Generating Initial Code"); st.info("AI Developer writing first code version...")
    shared_for_flow = get_shared_for_flow(); 
    shared_for_flow["critique_feedback"]="N/A (Initial Code Gen)"; 
    shared_for_flow["feedback_history"]=get_feedback_history_for_task(active_task_id) or [] 
    shared_for_flow["refinement_count"]=0 
    logger.info(f"Initial code gen. Shared refinement_count: {shared_for_flow['refinement_count']}")
    with st.spinner("Developer coding..."):
        try:
            action=code_generation_flow.run(shared_for_flow); st.session_state.update(shared_for_flow) # CORRECTED
            st.session_state.refinement_count = shared_for_flow.get("refinement_count",0)
            logger.info(f"After initial_code_gen. st.session_state.refinement_count: {st.session_state.refinement_count}")
            if action=="code_generation_failed" or not st.session_state.generated_project_structure:
                st.session_state.current_error_message=st.session_state.get("current_error_message","Dev fail gen code."); st.session_state.ui_stage="HUMAN_REVIEW"; update_task_field(active_task_id,"status","initial_code_failed")
                if st.session_state.current_error_message: log_feedback(active_task_id,None,"system_error_dev",st.session_state.current_error_message)
            else:
                st.session_state.ui_stage="QA_VALIDATE_REVIEW"
                cv_id=add_code_version(active_task_id,json.dumps(st.session_state.generated_project_structure),st.session_state.refinement_count)
                st.session_state.active_code_version_id=cv_id; update_task_field(active_task_id,"status","code_ready_for_qa"); update_task_field(active_task_id,"refinement_count",st.session_state.refinement_count)
        except Exception as e: logger.error(f"Initial code gen error: {e}",exc_info=True); st.session_state.current_error_message=f"Code gen error: {e}"; update_task_field(active_task_id,"status","initial_code_error_critical")
    st.rerun()

elif st.session_state.ui_stage == "QA_VALIDATE_REVIEW" and active_task_id:
    st.header(f"2c. Automated QA & Validation (Attempt {st.session_state.refinement_count})")
    st.info("AI QA & Validation Agents at work...")
    shared_for_flow = get_shared_for_flow(); shared_for_flow["current_test_case_index"]=0; shared_for_flow["test_results_summary"]=[]; shared_for_flow["all_tests_passed"]=True
    if not shared_for_flow.get("generated_project_structure") or not shared_for_flow.get("generated_test_cases"):
        st.session_state.current_error_message="Missing code/tests for QA."; st.session_state.ui_stage="HUMAN_REVIEW"; update_task_field(active_task_id,"status","error_missing_qa_inputs"); st.rerun()
    else:
        with st.spinner(f"Running tests & validation (Attempt {st.session_state.refinement_count})..."):
            try:
                action=qa_validation_flow.run(shared_for_flow); st.session_state.update(shared_for_flow)
                if st.session_state.active_code_version_id:
                    for res in st.session_state.test_results_summary: log_test_run_result(active_task_id,st.session_state.active_code_version_id,res.get("test_case",{}).get("description","N/A"), res.get("status","error"), res.get("actual_output"), res.get("message","N/A"))
                    if st.session_state.validation_status: log_validation_result(active_task_id,st.session_state.active_code_version_id,st.session_state.validation_status,st.session_state.validation_issues)
                update_task_field(active_task_id,"status","human_review_pending"); st.session_state.ui_stage="HUMAN_REVIEW"
            except Exception as e: logger.error(f"QA/Validation error: {e}",exc_info=True); st.session_state.current_error_message=f"QA/Validation error: {e}"; update_task_field(active_task_id,"status","qa_validation_error_critical")
        st.rerun()

elif st.session_state.ui_stage == "HUMAN_REVIEW" and active_task_id:
    st.header(f"3. Your Review (Code Version from Attempt {st.session_state.refinement_count})")
    project_structure=st.session_state.generated_project_structure
    if project_structure and project_structure.get("files"):
        st.subheader("Generated Project Files:")
        file_names = [f["name"] for f in project_structure["files"]]
        if file_names:
            tabs = st.tabs(file_names)
            for i, file_info in enumerate(project_structure["files"]):
                with tabs[i]: st.code(file_info.get("content", "# Empty file"), language="python")
        else: st.info("No files in the project structure.")
    else: st.warning("No project code available for review.")

    st.subheader("Test Cases & Results:"); test_summary=st.session_state.test_results_summary
    if test_summary:
        for i,tc_res in enumerate(test_summary):
            tc=tc_res.get("test_case",{}); icon="✅" if tc_res.get("status")=="success" else "❌"
            with st.expander(f"Test {i+1}: {icon} {tc.get('description','N/A')}",expanded=(tc_res.get("status")!="success")):
                st.json({"inputs":tc.get("inputs"),"expected":tc.get("expected_output"),"target_file":tc.get("target_file"),"target_func":tc.get("target_function")})
                st.write(f"Status: {tc_res.get('status','?')}, Msg: {tc_res.get('message','N/A')}"); 
                if tc_res.get("status")!="success":st.write(f"Actual: {tc_res.get('actual_output')}")
    else:st.info("No test results.")
    st.subheader("Validation Status:");val_status=st.session_state.validation_status
    if val_status=="pass":st.success("Validation Passed.")
    elif val_status in ["fail","error"]:st.error(f"Validation: {val_status.capitalize()}"); [st.warning(f"- {issue}") for issue in st.session_state.validation_issues or []]
    else:st.info("Validation not run or status unknown.")
    overall_pass=st.session_state.all_tests_passed and val_status=="pass"
    c1,c2=st.columns(2)
    if c1.button("✅ Approve Project",disabled=not overall_pass,key="approve_v5_app_fix1"): st.session_state.ui_stage="PACKAGING_COMPLETED";update_task_field(active_task_id,"status","approved_human");log_feedback(active_task_id,st.session_state.active_code_version_id,"user_approval","Project approved.");st.rerun()
    if c2.button("❌ Reject & Request Refinement",key="reject_v5_app_fix1"):
        if st.session_state.refinement_count>=MAX_REFINEMENTS:st.session_state.ui_stage="MAX_REFINEMENTS_FAILED";update_task_field(active_task_id,"status","failed_max_refine")
        else:st.session_state.ui_stage="PROVIDE_REJECTION_FEEDBACK"
        st.rerun()
    if not overall_pass:st.warning("Cannot approve until tests & validation pass.")

elif st.session_state.ui_stage == "PROVIDE_REJECTION_FEEDBACK" and active_task_id:
    st.header(f"3b. Provide Feedback (for next Attempt {st.session_state.refinement_count + 1})")
    st.info(f"This will be refinement attempt {st.session_state.refinement_count + 1} of {MAX_REFINEMENTS}.")
    rejection_reason=st.text_area("Reason for rejection/feedback:",value=st.session_state.user_rejection_reason,height=100,key="reject_reason_v5_app_fix1")
    if st.button("Submit Feedback & Trigger Refinement",key="submit_feedback_v5_app_fix1"):
        st.session_state.user_rejection_reason=rejection_reason;st.session_state.ui_stage="CRITIQUE_CODE"
        log_feedback(active_task_id,st.session_state.active_code_version_id,"user_rejection",rejection_reason)
        update_task_field(active_task_id,"status","refinement_pending_critique");st.rerun()

elif st.session_state.ui_stage == "CRITIQUE_CODE" and active_task_id:
    st.header(f"4a. AI Critiquing Code (for Attempt {st.session_state.refinement_count + 1})")
    st.info("AI Critique Agent analyzing feedback and code...")
    shared_for_flow = get_shared_for_flow()
    with st.spinner("AI generating critique..."):
        try:
            action = critique_generation_flow.run(shared_for_flow); st.session_state.update(shared_for_flow)
            if st.session_state.critique_feedback: log_feedback(active_task_id,st.session_state.active_code_version_id,"ai_critique",st.session_state.critique_feedback)
            if action=="refine_code" and not shared_for_flow.get("current_error_message"): st.session_state.ui_stage="REFINE_CODE_POST_CRITIQUE"
            else: st.session_state.current_error_message=shared_for_flow.get("current_error_message","Critique fail."); st.session_state.ui_stage="HUMAN_REVIEW"; update_task_field(active_task_id,"status","critique_error")
        except Exception as e: logger.error(f"Critique error: {e}",exc_info=True); st.session_state.current_error_message=f"Critique error: {e}"; update_task_field(active_task_id,"status","critique_error_critical")
    st.rerun()

elif st.session_state.ui_stage == "REFINE_CODE_POST_CRITIQUE" and active_task_id:
    st.header(f"4b. AI Refining Code (Attempt {st.session_state.refinement_count + 1})") 
    st.info("AI Developer revising code based on critique...")
    shared_for_flow = get_shared_for_flow()



    logger.info(f"Refining code. Current completed refinements: {st.session_state.refinement_count}")
    logger.info(f"Refining code. Refinement_count to be used by DeveloperNode: {shared_for_flow['refinement_count']}")
    with st.spinner(f"AI Developer revising (Attempt {st.session_state.refinement_count + 1})..."):
        try:
            logger.info(f"REFINE_CODE_POST_CRITIQUE: Before code_generation_flow. st.session_state.refinement_count = {st.session_state.refinement_count}, shared_for_flow['refinement_count'] = {shared_for_flow.get('refinement_count')}")
            action = code_generation_flow.run(shared_for_flow) 
            logger.info(f"REFINE_CODE_POST_CRITIQUE: After code_generation_flow. shared_for_flow['refinement_count'] = {shared_for_flow.get('refinement_count')}") # Should be old_value + 1
            st.session_state.update(shared_for_flow) 
            st.session_state.refinement_count = shared_for_flow.get("refinement_count", st.session_state.refinement_count)
            logger.info(f"REFINE_CODE_POST_CRITIQUE: After explicit update. st.session_state.refinement_count = {st.session_state.refinement_count}")
            


            # action=code_generation_flow.run(shared_for_flow); st.session_state.update(shared_for_flow) # CORRECTED
            # st.session_state.refinement_count = shared_for_flow.get("refinement_count", st.session_state.refinement_count) 
            logger.info(f"After refine. st.session_state.refinement_count: {st.session_state.refinement_count}")
            update_task_field(active_task_id,"refinement_count",st.session_state.refinement_count)
            if action=="code_ready_for_tests":
                cv_id=add_code_version(active_task_id,json.dumps(st.session_state.generated_project_structure),st.session_state.refinement_count)
                st.session_state.active_code_version_id=cv_id; update_task_field(active_task_id,"status","code_ready_qa_refined"); st.session_state.ui_stage="REDESIGN_TESTS_POST_REFINE"
            else: st.session_state.current_error_message=st.session_state.get("current_error_message","Dev refine fail.");update_task_field(active_task_id,"status","refine_codegen_fail");st.session_state.ui_stage="HUMAN_REVIEW"
        except Exception as e: logger.error(f"Refine error: {e}",exc_info=True); st.session_state.current_error_message=f"Refine error: {e}";update_task_field(active_task_id,"status","refine_error_crit")
    st.rerun()

elif st.session_state.ui_stage == "REDESIGN_TESTS_POST_REFINE" and active_task_id:
    st.header(f"4c. Re-Designing Test Cases (for Code Attempt {st.session_state.refinement_count})")
    st.info("AI Test Designer updating/creating tests for refined code...")
    shared_for_flow = get_shared_for_flow()
    with st.spinner("Re-designing tests..."):
        try:
            action = test_design_flow.run(shared_for_flow); st.session_state.update(shared_for_flow)
            if st.session_state.generated_test_cases: update_task_field(active_task_id,"generated_test_cases_json",st.session_state.generated_test_cases)
            if st.session_state.current_error_message or not st.session_state.generated_test_cases:
                st.session_state.current_error_message=st.session_state.get("current_error_message","Test re-design fail."); st.session_state.ui_stage="HUMAN_REVIEW"; update_task_field(active_task_id,"status","test_redesign_error")
            else: st.session_state.ui_stage="QA_VALIDATE_REVIEW"; update_task_field(active_task_id,"status","tests_redesigned_ready_qa")
        except Exception as e: logger.error(f"Test re-design error: {e}",exc_info=True); st.session_state.current_error_message=f"Test re-design error: {e}"; update_task_field(active_task_id,"status","test_redesign_error_crit")
    st.rerun()

elif st.session_state.ui_stage == "PACKAGING_COMPLETED" and active_task_id:
    st.header("5. Task Completed! 🎉");shared_for_flow=get_shared_for_flow() 
    with st.spinner("Packaging..."):
        try:
            action=packaging_flow.run(shared_for_flow);st.session_state.update(shared_for_flow)
            if st.session_state.packaged_artifacts_info:add_packaged_artifact(active_task_id,st.session_state.packaged_artifacts_info,st.session_state.handoff_summary);update_task_field(active_task_id,"status","completed")
        except Exception as e: logger.error(f"Packaging error: {e}",exc_info=True);st.session_state.current_error_message=f"Packaging error: {e}"
    st.balloons()
    if st.session_state.packaged_artifacts_info:
        st.subheader("Final Project:"); proj_info=st.session_state.packaged_artifacts_info.get("project_files",[])
        if proj_info:
            tabs = st.tabs([f_info.get("name", f"File {i+1}") for i, f_info in enumerate(proj_info)])
            for i, f_info in enumerate(proj_info):
                with tabs[i]: st.code(f_info.get('content','#Empty'),language="python")
        else: st.info("No files packaged.")
    if st.session_state.handoff_summary:st.success(st.session_state.handoff_summary)
    if st.button("Start New",key="start_new_comp_v5_app_fix1"):reset_for_new_task();st.rerun()

elif st.session_state.ui_stage in ["FAILED_PLANNING","MAX_REFINEMENTS_FAILED"] and active_task_id:
    header = "Max Refinements Reached" if st.session_state.ui_stage == "MAX_REFINEMENTS_FAILED" else "Planning Stage"
    st.header(f"😔 Task Failed: {header}"); error_detail = f"Details: Planner Its: {st.session_state.planner_iteration_count}, Refinements: {st.session_state.refinement_count}."
    st.error(error_detail)
    proj_struct_fail=st.session_state.generated_project_structure
    if proj_struct_fail and proj_struct_fail.get("files"):
        st.subheader("Last Generated Project (if any):")
        tabs = st.tabs([f["name"] for f in proj_struct_fail["files"]])
        for i, f_info in enumerate(proj_struct_fail["files"]):
            with tabs[i]: st.code(f_info.get('content',''),language="python")
    else: st.warning("No code available from last attempt.")
    if st.session_state.critique_feedback:st.subheader("Last AI Critique:");st.warning(st.session_state.critique_feedback)
    if st.button("Start New",key="start_new_fail_v5_app_fix1"):reset_for_new_task();st.rerun()

elif not active_task_id and st.session_state.ui_stage != "INPUT_REQUIREMENTS":
    st.warning("No active task. Resetting."); reset_for_new_task(); st.rerun()

display_error() 
with st.sidebar:
    st.header("Dev Info");
    if active_task_id: st.write(f"Task ID: {active_task_id}")
    st.write(f"Current UI Stage: {st.session_state.ui_stage}")
    st.write(f"Planner Its: {st.session_state.planner_iteration_count}/{MAX_PLANNER_ITERATIONS}")
    st.write(f"Refinements Done: {st.session_state.refinement_count}/{MAX_REFINEMENTS}") 
    if st.button("Force Reset UI State",key="reset_sidebar_v5_app_fix1"):reset_for_new_task();st.rerun()
    with st.expander("Session State (Truncated)",expanded=False):
        display_dict={k:(str(v)[:150]+'...' if isinstance(v,(str,list,dict))and len(str(v))>150 else v) for k,v in st.session_state.items() if k not in RAG_CONTEXT_KEYS+["app_initialized","rag_contexts_loaded"]}
        st.json(display_dict)