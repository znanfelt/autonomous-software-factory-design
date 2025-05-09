import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from main_pipeline.state import GraphState

def test_graph_state_fields():
    state = GraphState(
        initial_user_request="test",
        architectural_decision=None,
        clarified_user_input=None,
        clarification_questions_for_user=None,
        planner_iteration_count=0,
        max_planner_iterations=2,
        llm_models_config={},
        planned_task_description=None,
        planner_notes=None,
        task_description="",
        generated_test_cases=None,
        current_test_case_index=0,
        all_tests_passed=False,
        generated_code=None,
        current_test_status=None,
        current_test_message=None,
        test_results_summary=[],
        critique=None,
        validation_status=None,
        validation_issues=None,
        packaged_artifacts_info=None,
        handoff_summary=None,
        feedback_history=[],
        refinement_count=0,
        max_refinements=2,
        current_error=None,
        qa_agent_messages=[]
    )
    assert state["initial_user_request"] == "test"
    assert state["planner_iteration_count"] == 0