import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from main_pipeline.state import GraphState
from main_pipeline.graph import decide_after_architect, decide_after_planner, decide_after_test_case_designer

def test_decide_after_architect_success():
    state = GraphState(
        initial_user_request='Test', architectural_decision={'chosen_language': 'python'}, clarified_user_input=None,
        clarification_questions_for_user=None, planner_iteration_count=0, max_planner_iterations=2,
        llm_models_config={}, planned_task_description=None, planner_notes=None, task_description='',
        generated_test_cases=None, current_test_case_index=0, all_tests_passed=False, generated_code=None,
        current_test_status=None, current_test_message=None, test_results_summary=[], critique=None,
        validation_status=None, validation_issues=None, packaged_artifacts_info=None, handoff_summary=None,
        feedback_history=[], refinement_count=0, max_refinements=2, current_error=None, qa_agent_messages=[]
    )
    assert decide_after_architect(state) == 'planner_agent_node'

def test_decide_after_planner_to_test_case_designer():
    state = GraphState(
        initial_user_request='Test', architectural_decision={'chosen_language': 'python'}, clarified_user_input=None,
        clarification_questions_for_user=None, planner_iteration_count=0, max_planner_iterations=2,
        llm_models_config={}, planned_task_description='desc', planner_notes=None, task_description='desc',
        generated_test_cases=None, current_test_case_index=0, all_tests_passed=False, generated_code=None,
        current_test_status=None, current_test_message=None, test_results_summary=[], critique=None,
        validation_status=None, validation_issues=None, packaged_artifacts_info=None, handoff_summary=None,
        feedback_history=[], refinement_count=0, max_refinements=2, current_error=None, qa_agent_messages=[]
    )
    assert decide_after_planner(state) == 'test_case_designer_node'

def test_decide_after_test_case_designer_success():
    state = GraphState(
        initial_user_request='Test', architectural_decision=None, clarified_user_input=None,
        clarification_questions_for_user=None, planner_iteration_count=0, max_planner_iterations=2,
        llm_models_config={}, planned_task_description=None, planner_notes=None, task_description='',
        generated_test_cases=[{'function_name': 'foo', 'inputs': (), 'expected_output': 1, 'description': 'desc'}],
        current_test_case_index=0, all_tests_passed=False, generated_code=None,
        current_test_status=None, current_test_message=None, test_results_summary=[], critique=None,
        validation_status=None, validation_issues=None, packaged_artifacts_info=None, handoff_summary=None,
        feedback_history=[], refinement_count=0, max_refinements=2, current_error=None, qa_agent_messages=[]
    )
    assert decide_after_test_case_designer(state) == 'developer_agent_node'