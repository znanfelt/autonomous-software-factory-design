import logging
import shutil
import os
from pathlib import Path
from .graph import build_graph
from .state import GraphState
from .rag import initialize_rag_engines, architect_rag_query_engine_global
from main_pipeline import agents, tools, prompts, state, rag, graph

# Move initial_state to the module level for accessibility
initial_user_req = "Can you make a python function? It should be for greeting people. Needs good docs."
initial_state: GraphState = {
    "initial_user_request": initial_user_req,
    "architectural_decision": None,
    "clarified_user_input": None, "clarification_questions_for_user": None,
    "planner_iteration_count": 0, "max_planner_iterations": int(os.getenv("MAX_PLANNER_ITERATIONS", "2")),
    "llm_models_config": {
        "architect_llm":  os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o"),
        "planner_llm":    os.getenv("PLANNER_LLM_MODEL", "gpt-4o"),
        "developer_llm":  os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"),
        "qa_llm":         os.getenv("QA_LLM_MODEL", "gpt-4o"),
        "validation_llm": os.getenv("VALIDATION_LLM_MODEL", "gpt-3.5-turbo"),
        "critique_llm":   os.getenv("CRITIQUE_LLM_MODEL", "gpt-4o-mini")
    },
    "task_description": "", "planned_task_description": None, "planner_notes": None,
    "generated_test_cases": [{"function_name": "greet_user", "inputs": ("Alice",), "expected_output": "Hello, Alice!", "description": "Test greeting for Alice"}],
    "current_test_case_index": 0,
    "all_tests_passed": False,
    "generated_code": None, "current_test_status": None, "current_test_message": None, "critique": None,
    "validation_status": None, "validation_issues": [],
    "test_results_summary": [],
    "packaged_artifacts_info": None, "handoff_summary": None,
    "feedback_history": [], "refinement_count": 0, "max_refinements": int(os.getenv("MAX_REFINEMENTS", "3")),
    "current_error": None, "qa_agent_messages": []
}

def run_demo(cleanup_artifacts=True):
    logger = logging.getLogger(__name__)
    logger.info("🚀 Starting Autonomous Code Generation Demo (with Architect Agent) 🚀")
    ARTIFACTS_BASE_DIR = Path("output_artifacts_demo")
    if cleanup_artifacts and ARTIFACTS_BASE_DIR.exists():
        logger.info(f"Cleaning up previous artifacts in {ARTIFACTS_BASE_DIR}...")
        shutil.rmtree(ARTIFACTS_BASE_DIR)
    ARTIFACTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    if architect_rag_query_engine_global is None:
        initialize_rag_engines()
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not found in environment. LLM calls may fail or use mocks.")
    logger.info(f"Using LLM Configuration: {initial_state['llm_models_config']}")
    logger.info(f"Max Developer Refinements: {initial_state['max_refinements']}, Max Planner Iterations: {initial_state['max_planner_iterations']}")
    app = build_graph()
    logger.info("Invoking the graph...")
    final_state = app.invoke(initial_state)
    logger.info("🏁 Demo Finished. Final State (Key Fields): 🏁")
    for key, value in final_state.items():
        if key in ["generated_code", "architectural_decision", "planned_task_description", 
                   "planner_notes", "critique", "handoff_summary", "clarified_user_input", 
                   "packaged_artifacts_info", "validation_issues", "feedback_history", "current_error"] and value:
             logger.info(f"  {key}: {value}")
        elif key not in ["qa_agent_messages", "llm_models_config"] and value is not None :
             logger.debug(f"  {key}: {value}")
    logger.info("--- End-to-End Demo Test Verification ---")
    final_success = (final_state.get("current_test_status") == "success" and
                     final_state.get("validation_status") == "pass" and
                     final_state.get("packaged_artifacts_info") is not None and
                     final_state.get("handoff_summary") is not None and
                     not final_state.get("current_error"))
    if final_success:
        logger.info(f"✅ PASSED: Full pipeline successful. Handoff: {final_state.get('handoff_summary')}")
        pkg_info = final_state.get("packaged_artifacts_info")
        if pkg_info and pkg_info.get("code_file") and Path(ARTIFACTS_BASE_DIR.parent / pkg_info["code_file"]).exists():
            logger.info("✅ VERIFIED: Artifact code file was created.")
        else:
            logger.warning("⚠️ WARNING: Artifact code file not found where expected.")
    elif final_state.get("current_error"):
        logger.error(f"❌ FAILED: Pipeline ended with error: {final_state.get('current_error')}")
    else:
        logger.error(f"❌ FAILED: Pipeline did not complete successfully. Final Test: {final_state.get('current_test_status')}, Validation: {final_state.get('validation_status')}")
    return final_state