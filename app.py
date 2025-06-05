"""
Main Streamlit app for the SDLC PocketFlow system.
"""
import os
import json
import logging
from pathlib import Path
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
import streamlit as st

from pocketflow import Flow
from nodes import (
    InitialRequestNode,
    ArchitectPlannerNode,
    DeveloperNode,
    TestCaseDesignerNode,
    QANode,
    ValidationNode,
    CritiqueNode,
    PackageNode,
    SecurityComplianceNode,
)
from utils.database import (
    init_db,
    create_task,
    update_task_field,
    get_task_data,
    add_code_version,
    get_latest_code_version,
    log_test_run_result,
    get_test_results_for_version,
    log_validation_result,
    get_validation_log_for_version,
    log_feedback,
    get_feedback_history_for_task,
    add_packaged_artifact,
    DB_FILE,
    get_all_tasks_summary,
    load_task_state_from_db,
)
from utils.prompts import (
    ARCHITECT_PROMPT_TEMPLATE,
    PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
    PLANNER_CODEGEN_PROMPT_TEMPLATE,
    DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
    TEST_CASE_DESIGNER_PROMPT_TEMPLATE,
    VALIDATION_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT_TEMPLATE,
    SECURITY_COMPLIANCE_PROMPT_TEMPLATE,
)
from flow import (
    elicitation_flow,
    test_design_flow,
    code_generation_flow,
    qa_validation_security_flow,
    critique_generation_flow,
    packaging_flow,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

RAG_CONTEXTS_DIR = Path(__file__).parent / "rag_contexts"
RAG_CONTEXT_KEYS = [
    "architectural_principles_context",
    "planning_guidelines_context",
    "coding_standards_context",
    "validation_rules_context",
    "debugging_tips_context",
    "security_compliance_rules_context",
]
MAX_PLANNER_ITERATIONS = int(os.getenv("MAX_PLANNER_ITERATIONS", "2"))
MAX_REFINEMENTS = int(os.getenv("MAX_REFINEMENTS", "3"))
LLM_MODELS_CONFIG = {
    "architect_llm": os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o"),
    "planner_llm": os.getenv("PLANNER_LLM_MODEL", "gpt-4o"),
    "developer_llm": os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"),
    "test_designer_llm": os.getenv("TEST_DESIGNER_LLM_MODEL", "gpt-3.5-turbo"),
    "validation_llm": os.getenv("VALIDATION_LLM_MODEL", "gpt-3.5-turbo"),
    "security_llm": os.getenv(
        "SECURITY_LLM_MODEL", "gpt-3.5-turbo"
    ),
    "critique_llm": os.getenv("CRITIQUE_LLM_MODEL", "gpt-4o-mini"),
}


def load_rag_context(filename: str) -> str:
    try:
        with open(RAG_CONTEXTS_DIR / filename, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error RAG {filename}: {e}")
        return f"Error RAG {filename}: {e}"


if "app_initialized" not in st.session_state:
    init_db()
    st.session_state.ui_stage = "TASK_SELECTION"
    st.session_state.active_task_id = None
    st.session_state.user_raw_request = ""
    st.session_state.current_request_for_planner = ""
    st.session_state.architectural_decision = None
    st.session_state.planner_iteration_count = 0
    st.session_state.clarification_questions_for_user = None
    st.session_state.planned_task_description = None
    st.session_state.suggested_project_outline = None
    st.session_state.planner_notes = None
    st.session_state.generated_project_structure = None
    st.session_state.active_code_version_id = None
    st.session_state.generated_test_cases = None
    st.session_state.current_test_case_index = 0
    st.session_state.test_results_summary = []
    st.session_state.all_tests_passed = False
    st.session_state.validation_status = None
    st.session_state.validation_issues = []
    st.session_state.security_compliance_status = None
    st.session_state.security_compliance_issues = []
    st.session_state.user_rejection_reason = ""
    st.session_state.critique_feedback = None
    st.session_state.feedback_history = []
    st.session_state.refinement_count = 0
    st.session_state.packaged_artifacts_info = None
    st.session_state.handoff_summary = None
    st.session_state.current_error_message = None
    for key in RAG_CONTEXT_KEYS:
        st.session_state[key] = load_rag_context(f"{key.replace('_context', '')}.txt")
    st.session_state.rag_contexts_loaded = True
    st.session_state.app_initialized = True
    logger.info("Streamlit App Initialized.")


def reset_for_new_task(go_to_input_stage=True):
    preserve_keys = RAG_CONTEXT_KEYS + ["app_initialized", "rag_contexts_loaded"]
    preserved_values = {k: st.session_state.get(k) for k in preserve_keys}
    st.session_state.clear()
    st.session_state.update(preserved_values)
    if go_to_input_stage:
        st.session_state.ui_stage = "INPUT_REQUIREMENTS"
    else:
        st.session_state.ui_stage = "TASK_SELECTION"
    st.session_state.active_task_id = None
    st.session_state.user_raw_request = ""
    st.session_state.current_request_for_planner = ""
    st.session_state.architectural_decision = None
    st.session_state.planner_iteration_count = 0
    st.session_state.clarification_questions_for_user = None
    st.session_state.planned_task_description = None
    st.session_state.suggested_project_outline = None
    st.session_state.planner_notes = None
    st.session_state.generated_project_structure = None
    st.session_state.active_code_version_id = None
    st.session_state.generated_test_cases = None
    st.session_state.current_test_case_index = 0
    st.session_state.test_results_summary = []
    st.session_state.all_tests_passed = False
    st.session_state.validation_status = None
    st.session_state.validation_issues = []
    st.session_state.security_compliance_status = None
    st.session_state.security_compliance_issues = []
    st.session_state.user_rejection_reason = ""
    st.session_state.critique_feedback = None
    st.session_state.feedback_history = []
    st.session_state.refinement_count = 0
    st.session_state.packaged_artifacts_info = None
    st.session_state.handoff_summary = None
    st.session_state.current_error_message = None
    logger.info(f"UI state reset. New stage: {st.session_state.ui_stage}")


def display_error():
    if st.session_state.current_error_message:
        st.error(f"Error: {st.session_state.current_error_message}")


def get_shared_for_flow() -> Dict[str, Any]:
    shared = {}
    keys_to_copy = [
        "user_raw_request",
        "current_request_for_planner",
        "architectural_decision",
        "planner_iteration_count",
        "clarification_questions_for_user",
        "planned_task_description",
        "suggested_project_outline",
        "planner_notes",
        "generated_project_structure",
        "active_code_version_id",
        "generated_test_cases",
        "current_test_case_index",
        "test_results_summary",
        "all_tests_passed",
        "validation_status",
        "validation_issues",
        "security_compliance_status",
        "security_compliance_issues",
        "user_rejection_reason",
        "critique_feedback",
        "feedback_history",
        "refinement_count",
        "packaged_artifacts_info",
        "handoff_summary",
        "current_error_message",
        "active_task_id",
    ] + RAG_CONTEXT_KEYS
    for key in keys_to_copy:
        if key in st.session_state:
            shared[key] = st.session_state[key]
    shared["llm_models_config"] = LLM_MODELS_CONFIG
    shared["max_planner_iterations"] = MAX_PLANNER_ITERATIONS
    shared["max_refinements"] = MAX_REFINEMENTS
    if isinstance(shared.get("planned_task_description"), dict):
        shared["task_description_json_str"] = json.dumps(
            shared["planned_task_description"], indent=2
        )
    if isinstance(shared.get("generated_project_structure"), dict):
        shared["project_structure_json_str"] = json.dumps(
            shared["generated_project_structure"], indent=2
        )
    shared["suggested_project_outline_json_str"] = json.dumps(
        shared.get("suggested_project_outline", []), indent=2
    )

    return shared


def load_task_into_session(task_id: int):
    logger.info(f"LOAD_TASK: Attempting for task_id: {task_id}")
    loaded_db_data = load_task_state_from_db(task_id)
    if loaded_db_data:
        logger.info(
            f"LOAD_TASK: Data found in DB for task {task_id}. DB status: {loaded_db_data.get('ui_stage')}"
        )
        preserve_keys = RAG_CONTEXT_KEYS + ["app_initialized", "rag_contexts_loaded"]
        preserved_values = {k: st.session_state.get(k) for k in preserve_keys}
        st.session_state.clear()
        st.session_state.update(preserved_values)
        st.session_state.update(loaded_db_data)
        st.session_state.active_task_id = task_id
        db_status = loaded_db_data.get("ui_stage", "HUMAN_REVIEW")
        st.session_state.ui_stage = db_status
        if not isinstance(st.session_state.get("feedback_history"), list):
            st.session_state.feedback_history = []
        if not isinstance(st.session_state.get("validation_issues"), list):
            st.session_state.validation_issues = []
        if not isinstance(st.session_state.get("security_compliance_issues"), list):
            st.session_state.security_compliance_issues = []
        logger.info(
            f"LOAD_TASK: Successfully loaded task {st.session_state.active_task_id}. UI stage set to: {st.session_state.ui_stage}"
        )
        st.session_state.current_error_message = None
    else:
        st.error(f"LOAD_TASK: Could not load data for task {task_id}.")
        st.session_state.active_task_id = None
        st.session_state.ui_stage = "TASK_SELECTION"
        logger.error(
            f"LOAD_TASK: Failed to load data for task {task_id}. Staying on TASK_SELECTION."
        )


st.set_page_config(layout="wide")
st.title("🚧 SDLC Factory (MVP) 🏭")
st.caption(
    "Describe a Python project. AI agents will build, test, & validate with your guidance."
)
active_task_id = st.session_state.get("active_task_id")
current_ui_stage = st.session_state.get("ui_stage", "TASK_SELECTION")
logger.info(
    f"Top of app.py: active_task_id = {active_task_id}, ui_stage = {current_ui_stage}"
)

if current_ui_stage == "TASK_SELECTION":
    st.header("Manage Tasks")
    if st.button("🚀 Start New Project Request", key="start_new_task_btn_v8"):
        reset_for_new_task(go_to_input_stage=True)
        st.rerun()
    st.subheader("Previous Tasks:")
    tasks_summary = get_all_tasks_summary()
    if not tasks_summary:
        st.info("No previous tasks found.")
    else:
        for task_item in tasks_summary:
            col1, col2, col3, col4 = st.columns([0.5, 2, 1, 1])
            with col1:
                st.write(f"ID: {task_item['task_id']}")
            with col2:
                st.caption(task_item["initial_request"])
            with col3:
                st.caption(f"Status: {task_item['status']}")
            if col4.button("Load & Resume", key=f"load_task_{task_item['task_id']}_v8"):
                load_task_into_session(task_item["task_id"])
                st.rerun()
            st.divider()

elif current_ui_stage == "INPUT_REQUIREMENTS":
    st.header("1. Describe Your Python Project/Function")
    user_input_key = f"raw_req_v8_{st.session_state.get('active_task_id', 'new')}"
    user_input = st.text_area(
        "What would you like AI to create?",
        value=st.session_state.get("user_raw_request", ""),
        height=150,
        key=user_input_key,
    )
    if st.button(
        "Start Planning",
        key=f"submit_init_req_v8_{st.session_state.get('active_task_id', 'new')}",
    ):
        if not user_input.strip():
            st.warning("Please describe.")
        else:
            if st.session_state.active_task_id is None:
                st.session_state.user_raw_request = user_input
                st.session_state.current_request_for_planner = user_input
                st.session_state.planner_iteration_count = 0
                st.session_state.refinement_count = 0
                task_id_new = create_task(st.session_state.user_raw_request)
                if not task_id_new:
                    st.error("Failed to create task in DB.")
                    st.stop()
                st.session_state.active_task_id = task_id_new
                active_task_id = task_id_new
            else:
                active_task_id = st.session_state.active_task_id
                st.session_state.user_raw_request = user_input
                st.session_state.current_request_for_planner = user_input
                update_task_field(active_task_id, "initial_request", user_input)
            logger.info(
                f"Task {active_task_id}: Starting/Continuing planning for request: {user_input[:50]}..."
            )
            shared_for_flow = get_shared_for_flow()
            with st.spinner("Architect & Planner thinking..."):
                try:
                    action = elicitation_flow.run(shared_for_flow)
                    st.session_state.update(shared_for_flow)
                    st.session_state.planner_iteration_count = shared_for_flow.get(
                        "planner_iteration_count",
                        st.session_state.planner_iteration_count,
                    )
                    update_task_field(
                        active_task_id,
                        "architectural_decision",
                        st.session_state.architectural_decision,
                    )
                    update_task_field(
                        active_task_id,
                        "planner_iteration_count",
                        st.session_state.planner_iteration_count,
                    )
                    next_ui_stage = "FAILED_PLANNING"
                    if action == "clarification_needed":
                        next_ui_stage = "CLARIFICATION"
                    elif action == "plan_ready_for_code":
                        next_ui_stage = "DESIGN_TESTS"
                        update_task_field(
                            active_task_id,
                            "planned_task_description",
                            st.session_state.planned_task_description,
                        )
                        update_task_field(
                            active_task_id,
                            "planner_notes",
                            st.session_state.planner_notes,
                        )
                    else:
                        st.session_state.current_error_message = st.session_state.get(
                            "current_error_message", "Planning fail."
                        )
                    st.session_state.ui_stage = next_ui_stage
                    update_task_field(active_task_id, "status", next_ui_stage)
                except Exception as e:
                    logger.error(f"Elicitation error: {e}", exc_info=True)
                    st.session_state.current_error_message = f"Planning error: {e}"
                    st.session_state.ui_stage = "FAILED_PLANNING"
                    update_task_field(active_task_id, "status", "FAILED_PLANNING")
            st.rerun()

elif st.session_state.ui_stage == "DESIGN_TESTS" and active_task_id:
    st.header("2a. Designing Test Cases")
    shared_for_flow = get_shared_for_flow()
    with st.spinner("Designing tests..."):
        try:
            action = test_design_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            if st.session_state.generated_test_cases:
                update_task_field(
                    active_task_id,
                    "generated_test_cases_json",
                    st.session_state.generated_test_cases,
                )
            if (
                st.session_state.current_error_message
                or not st.session_state.generated_test_cases
            ):
                st.session_state.current_error_message = st.session_state.get(
                    "current_error_message", "Test design failed."
                )
                st.session_state.ui_stage = "FAILED_PLANNING"
                update_task_field(active_task_id, "status", "FAILED_PLANNING")
            else:
                st.session_state.ui_stage = "INITIAL_CODE_GEN"
                update_task_field(active_task_id, "status", "INITIAL_CODE_GEN")
        except Exception as e:
            logger.error(f"Test design error: {e}", exc_info=True)
            st.session_state.current_error_message = f"Test design error: {e}"
            st.session_state.ui_stage = "FAILED_PLANNING"
            update_task_field(active_task_id, "status", "FAILED_PLANNING")
    st.rerun()

elif st.session_state.ui_stage == "INITIAL_CODE_GEN" and active_task_id:
    st.header(
        f"2b. AI Generating Code (Attempt {st.session_state.refinement_count + 1})"
    )
    shared_for_flow = get_shared_for_flow()
    with st.spinner("AI generating code..."):
        try:
            action = code_generation_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            st.session_state.refinement_count = shared_for_flow.get(
                "refinement_count", st.session_state.refinement_count
            )
            update_task_field(
                active_task_id, "refinement_count", st.session_state.refinement_count
            )
            if action == "code_ready_for_tests":
                cv_id = add_code_version(
                    active_task_id,
                    json.dumps(st.session_state.generated_project_structure),
                    st.session_state.refinement_count,
                )
                st.session_state.active_code_version_id = cv_id
                st.session_state.ui_stage = "QA_VALIDATE_REVIEW"
                update_task_field(active_task_id, "status", "QA_VALIDATE_REVIEW")
            else:
                st.session_state.current_error_message = st.session_state.get(
                    "current_error_message", "Initial code generation failed."
                )
                st.session_state.ui_stage = "FAILED_PLANNING"
                update_task_field(active_task_id, "status", "FAILED_PLANNING")
        except Exception as e:
            logger.error(f"Initial code gen error: {e}", exc_info=True)
            st.session_state.current_error_message = f"Initial code gen error: {e}"
            st.session_state.ui_stage = "FAILED_PLANNING"
            update_task_field(active_task_id, "status", "FAILED_PLANNING")
    st.rerun()

elif (
    current_ui_stage == "QA_VALIDATE_REVIEW" and active_task_id
):
    st.header(
        f"2c. Automated QA, Validation & Security Scan (Attempt {st.session_state.refinement_count})"
    )
    st.info("AI agents are at work...")
    shared_for_flow = get_shared_for_flow()
    shared_for_flow["current_test_case_index"] = 0
    shared_for_flow["test_results_summary"] = []
    shared_for_flow["all_tests_passed"] = True
    shared_for_flow["validation_issues"] = []
    shared_for_flow["security_compliance_issues"] = []

    if not shared_for_flow.get(
        "generated_project_structure"
    ) or not shared_for_flow.get("generated_test_cases"):
        st.session_state.current_error_message = (
            "Missing code/tests for QA & Validation."
        )
        st.session_state.ui_stage = "HUMAN_REVIEW"
        update_task_field(active_task_id, "status", "HUMAN_REVIEW")
        st.rerun()
    else:
        with st.spinner(
            f"Running tests, validation & security scan (Attempt {st.session_state.refinement_count})..."
        ):
            try:
                action = qa_validation_security_flow.run(
                    shared_for_flow
                )
                st.session_state.update(shared_for_flow)
                if st.session_state.active_code_version_id:
                    for res in st.session_state.test_results_summary:
                        log_test_run_result(
                            active_task_id,
                            st.session_state.active_code_version_id,
                            res.get("test_case", {}).get("description", "N/A"),
                            res.get("status", "error"),
                            res.get("actual_output"),
                            res.get("message", "N/A"),
                        )
                    if st.session_state.validation_status:
                        log_validation_result(
                            active_task_id,
                            st.session_state.active_code_version_id,
                            st.session_state.validation_status,
                            st.session_state.validation_issues,
                        )
                update_task_field(
                    active_task_id,
                    "security_status",
                    st.session_state.get("security_compliance_status"),
                )
                update_task_field(
                    active_task_id,
                    "security_issues",
                    st.session_state.get("security_compliance_issues", []),
                )

                st.session_state.ui_stage = "HUMAN_REVIEW"
                update_task_field(active_task_id, "status", "HUMAN_REVIEW")
            except Exception as e:
                logger.error(f"QA/Validation/Security error: {e}", exc_info=True)
                st.session_state.current_error_message = f"QA/Val/Sec error: {e}"
                update_task_field(active_task_id, "status", "qa_val_sec_error_critical")
                st.session_state.ui_stage = "HUMAN_REVIEW"
        st.rerun()

elif current_ui_stage == "HUMAN_REVIEW" and active_task_id:
    st.header(
        f"3. Your Review (Code Version from Attempt {st.session_state.refinement_count})"
    )
    project_structure = st.session_state.generated_project_structure
    if isinstance(project_structure, dict) and project_structure.get("files"):
        st.subheader("Generated Project Files:")
        file_names = [f["name"] for f in project_structure["files"]]
        tabs = st.tabs(file_names)
        for i, file_info in enumerate(project_structure["files"]):
            with tabs[i]:
                st.code(file_info.get("content", "# Empty file"), language="python")
    else:
        st.warning("No project code available.")

    st.subheader("Test Cases & Results:")
    test_summary = st.session_state.test_results_summary
    if test_summary:
        for i, tc_res in enumerate(test_summary):
            tc = tc_res.get("test_case", {})
            icon = "✅" if tc_res.get("status") == "success" else "❌"
            with st.expander(
                f"Test {i+1}: {icon} {tc.get('description','N/A')}",
                expanded=(tc_res.get("status") != "success"),
            ):
                st.json(
                    {
                        "inputs": tc.get("inputs"),
                        "expected": tc.get("expected_output"),
                        "target_file": tc.get("target_file"),
                        "target_func": tc.get("target_function"),
                    }
                )
                st.write(
                    f"Status: {tc_res.get('status','?')}, Msg: {tc_res.get('message','N/A')}"
                )
                if tc_res.get("status") != "success":
                    st.write(f"Actual: {tc_res.get('actual_output')}")
    else:
        st.info("No test results.")

    st.subheader("Validation Status:")
    val_status = st.session_state.validation_status
    if val_status == "pass":
        st.success("Validation Passed.")
    elif val_status in ["fail", "error"]:
        st.error(f"Validation: {val_status.capitalize()}")
        [st.warning(f"- {issue}") for issue in st.session_state.validation_issues or []]
    else:
        st.info("Validation not run or status unknown.")

    st.subheader("Security & Compliance Check:")
    sec_status = st.session_state.get("security_compliance_status")
    sec_issues = st.session_state.get("security_compliance_issues", [])
    if sec_status == "pass":
        st.success("Security & Compliance Checks Passed.")
    elif sec_status in ["fail", "error"]:
        st.error(f"Security & Compliance: {sec_status.capitalize()}")
        if sec_issues:
            [st.warning(f"- {issue}") for issue in sec_issues]
        else:
            st.warning("No specific security/compliance issues listed by agent.")
    else:
        st.info(
            "Security & Compliance check not run or status unknown for this version."
        )

    overall_pass = (
        st.session_state.all_tests_passed
        and val_status == "pass"
        and sec_status == "pass"
    )

    c1, c2 = st.columns(2)
    if c1.button(
        "✅ Approve Project",
        disabled=not overall_pass,
        key=f"approve_v8_{active_task_id}_{st.session_state.refinement_count}",
    ):
        st.session_state.ui_stage = "PACKAGING_COMPLETED"
        update_task_field(active_task_id, "status", "PACKAGING_COMPLETED")
        log_feedback(
            active_task_id,
            st.session_state.active_code_version_id,
            "user_approval",
            "Project approved.",
        )
        st.rerun()
    if c2.button(
        "❌ Reject & Request Refinement",
        key=f"reject_v8_{active_task_id}_{st.session_state.refinement_count}",
    ):
        if st.session_state.refinement_count >= MAX_REFINEMENTS:
            st.session_state.ui_stage = "MAX_REFINEMENTS_FAILED"
            update_task_field(active_task_id, "status", "MAX_REFINEMENTS_FAILED")
        else:
            st.session_state.ui_stage = "PROVIDE_REJECTION_FEEDBACK"
            update_task_field(active_task_id, "status", "PROVIDE_REJECTION_FEEDBACK")
        st.rerun()
    if not overall_pass:
        st.warning(
            "Cannot approve until all tests, validation, and security checks pass."
        )

elif st.session_state.ui_stage == "PROVIDE_REJECTION_FEEDBACK" and active_task_id:
    st.header(
        f"3b. Provide Feedback (for next Attempt {st.session_state.refinement_count + 1})"
    )
    rejection_reason = st.text_area(
        "Reason for rejection/feedback:",
        value=st.session_state.user_rejection_reason,
        height=100,
        key=f"reject_reason_v8_{active_task_id}",
    )
    if st.button(
        "Submit Feedback & Trigger Refinement",
        key=f"submit_feedback_v8_{active_task_id}",
    ):
        st.session_state.user_rejection_reason = rejection_reason
        st.session_state.ui_stage = "CRITIQUE_CODE"
        log_feedback(
            active_task_id,
            st.session_state.active_code_version_id,
            "user_rejection",
            rejection_reason,
        )
        update_task_field(active_task_id, "status", "CRITIQUE_CODE")
        st.rerun()

elif st.session_state.ui_stage == "CRITIQUE_CODE" and active_task_id:
    st.header(
        f"4a. AI Critiquing Code (for Attempt {st.session_state.refinement_count + 1})"
    )
    shared_for_flow = get_shared_for_flow()
    with st.spinner("AI generating critique..."):
        try:
            action = critique_generation_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            if st.session_state.critique_feedback:
                log_feedback(
                    active_task_id,
                    st.session_state.active_code_version_id,
                    "ai_critique",
                    st.session_state.critique_feedback,
                )
            if action == "refine_code" and not shared_for_flow.get(
                "current_error_message"
            ):
                st.session_state.ui_stage = "REFINE_CODE_POST_CRITIQUE"
                update_task_field(active_task_id, "status", "REFINE_CODE_POST_CRITIQUE")
            else:
                st.session_state.current_error_message = shared_for_flow.get(
                    "current_error_message", "Critique fail."
                )
                st.session_state.ui_stage = "HUMAN_REVIEW"
                update_task_field(active_task_id, "status", "HUMAN_REVIEW")
        except Exception as e:
            logger.error(f"Critique error: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critique error: {e}"
            update_task_field(active_task_id, "status", "critique_error_critical")
    st.rerun()

elif st.session_state.ui_stage == "REFINE_CODE_POST_CRITIQUE" and active_task_id:
    st.header(f"4b. AI Refining Code (Attempt {st.session_state.refinement_count + 1})")
    shared_for_flow = get_shared_for_flow()
    with st.spinner(
        f"AI Developer revising (Attempt {st.session_state.refinement_count + 1})..."
    ):
        try:
            action = code_generation_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            st.session_state.refinement_count = shared_for_flow.get(
                "refinement_count", st.session_state.refinement_count
            )
            update_task_field(
                active_task_id, "refinement_count", st.session_state.refinement_count
            )
            if action == "code_ready_for_tests":
                cv_id = add_code_version(
                    active_task_id,
                    json.dumps(st.session_state.generated_project_structure),
                    st.session_state.refinement_count,
                )
                st.session_state.active_code_version_id = cv_id
                update_task_field(
                    active_task_id, "status", "REDESIGN_TESTS_POST_REFINE"
                )
                st.session_state.ui_stage = "REDESIGN_TESTS_POST_REFINE"
            else:
                st.session_state.current_error_message = st.session_state.get(
                    "current_error_message", "Dev refine fail."
                )
                update_task_field(active_task_id, "status", "refine_codegen_fail")
                st.session_state.ui_stage = "HUMAN_REVIEW"
        except Exception as e:
            logger.error(f"Refine error: {e}", exc_info=True)
            st.session_state.current_error_message = f"Refine error: {e}"
            update_task_field(active_task_id, "status", "refine_error_crit")
    st.rerun()

elif st.session_state.ui_stage == "REDESIGN_TESTS_POST_REFINE" and active_task_id:
    st.header(
        f"4c. Re-Designing Test Cases (for Code Attempt {st.session_state.refinement_count})"
    )
    shared_for_flow = get_shared_for_flow()
    with st.spinner("Re-designing tests..."):
        try:
            action = test_design_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            if st.session_state.generated_test_cases:
                update_task_field(
                    active_task_id,
                    "generated_test_cases_json",
                    st.session_state.generated_test_cases,
                )
            if (
                st.session_state.current_error_message
                or not st.session_state.generated_test_cases
            ):
                st.session_state.current_error_message = st.session_state.get(
                    "current_error_message", "Test re-design fail."
                )
                st.session_state.ui_stage = "HUMAN_REVIEW"
                update_task_field(active_task_id, "status", "HUMAN_REVIEW")
            else:
                st.session_state.ui_stage = "QA_VALIDATE_REVIEW"
                update_task_field(active_task_id, "status", "QA_VALIDATE_REVIEW")
        except Exception as e:
            logger.error(f"Test re-design error: {e}", exc_info=True)
            st.session_state.current_error_message = f"Test re-design error: {e}"
            update_task_field(active_task_id, "status", "test_redesign_error_crit")
    st.rerun()

elif st.session_state.ui_stage == "PACKAGING_COMPLETED" and active_task_id:
    st.header("5. Task Completed! 🎉")
    shared_for_flow = get_shared_for_flow()
    with st.spinner("Packaging..."):
        try:
            action = packaging_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            if st.session_state.packaged_artifacts_info:
                add_packaged_artifact(
                    active_task_id,
                    st.session_state.packaged_artifacts_info,
                    st.session_state.handoff_summary,
                )
                update_task_field(active_task_id, "status", "completed")
        except Exception as e:
            logger.error(f"Packaging error: {e}", exc_info=True)
            st.session_state.current_error_message = f"Packaging error: {e}"
    st.balloons()
    if st.session_state.packaged_artifacts_info:
        st.subheader("Final Project:")
        proj_info = st.session_state.packaged_artifacts_info.get("project_files", [])
        if proj_info:
            tabs = st.tabs(
                [
                    f_info.get("name", f"File {i+1}")
                    for i, f_info in enumerate(proj_info)
                ]
            )
            for i, f_info in enumerate(proj_info):
                with tabs[i]:
                    st.code(f_info.get("content", "#Empty"), language="python")
        else:
            st.info("No files packaged.")
    if st.session_state.handoff_summary:
        st.success(st.session_state.handoff_summary)
    if st.button("Start New Project Request", key="start_new_comp_v8_app"):
        reset_for_new_task(go_to_input_stage=False)
        st.rerun()

elif (
    st.session_state.ui_stage in ["FAILED_PLANNING", "MAX_REFINEMENTS_FAILED"]
    and active_task_id
):
    header = (
        "Max Refinements Reached"
        if st.session_state.ui_stage == "MAX_REFINEMENTS_FAILED"
        else "Planning Stage"
    )
    st.header(f"😔 Task Failed: {header}")
    error_detail = f"Details: Planner Its: {st.session_state.planner_iteration_count}, Refinements: {st.session_state.refinement_count}."
    if st.session_state.current_error_message:
        error_detail += f" Last Error: {st.session_state.current_error_message}"
    st.error(error_detail)
    proj_struct_fail = st.session_state.get("generated_project_structure")
    if isinstance(proj_struct_fail, dict) and proj_struct_fail.get("files"):
        st.subheader("Last Generated Project (if any):")
        tabs = st.tabs([f["name"] for f in proj_struct_fail["files"]])
        for i, f_info in enumerate(proj_struct_fail["files"]):
            with tabs[i]:
                st.code(f_info.get("content", ""), language="python")
    else:
        st.warning("No code available from last attempt.")
    if st.session_state.critique_feedback:
        st.subheader("Last AI Critique:")
        st.warning(st.session_state.critique_feedback)
    if st.button("Start New Request", key="start_new_fail_v8_app"):
        reset_for_new_task(go_to_input_stage=False)
        st.rerun()

elif (
    not active_task_id and current_ui_stage != "INPUT_REQUIREMENTS"
):
    logger.info(
        f"No active task ID (current stage: {current_ui_stage}). Ensuring TASK_SELECTION."
    )
    if current_ui_stage != "TASK_SELECTION":
        st.session_state.ui_stage = "TASK_SELECTION"
        st.rerun()

display_error()
with st.sidebar:
    st.header("Dev Info")
    if active_task_id:
        st.write(f"Task ID: {st.session_state.active_task_id}")
    st.write(f"UI Stage: {st.session_state.ui_stage}")
    st.write(
        f"Planner Its: {st.session_state.planner_iteration_count}/{MAX_PLANNER_ITERATIONS}"
    )
    st.write(f"Refinements Done: {st.session_state.refinement_count}/{MAX_REFINEMENTS}")
    if st.button("Force Reset App (Task Selection)", key="reset_sidebar_v8_app"):
        reset_for_new_task(go_to_input_stage=False)
        st.rerun()
    with st.expander("Session State (Truncated)", expanded=False):
        display_dict = {
            k: (
                str(v)[:150] + "..."
                if isinstance(v, (str, list, dict)) and len(str(v)) > 150
                else v
            )
            for k, v in st.session_state.items()
            if k not in RAG_CONTEXT_KEYS + ["app_initialized", "rag_contexts_loaded"]
        }
        st.json(display_dict)
