import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from main_pipeline.state import GraphState
from main_pipeline.agents import architect_agent_node, planner_agent_node, developer_agent_node

class MockLLM:
    def __init__(self, response):
        self.response = response
    def invoke(self, *args, **kwargs):
        return self.response

def test_architect_agent_node_basic(monkeypatch):
    # Patch get_llm_instance to return a mock LLM
    monkeypatch.setattr('main_pipeline.agents.get_llm_instance', lambda *a, **kw: MockLLM({
        'chosen_language': 'python', 'framework_hint': 'standard_library', 'high_level_notes': 'Test notes.'
    }))
    state = GraphState(
        initial_user_request='Test', architectural_decision=None, clarified_user_input=None,
        clarification_questions_for_user=None, planner_iteration_count=0, max_planner_iterations=2,
        llm_models_config={}, planned_task_description=None, planner_notes=None, task_description='',
        generated_test_cases=None, current_test_case_index=0, all_tests_passed=False, generated_code=None,
        current_test_status=None, current_test_message=None, test_results_summary=[], critique=None,
        validation_status=None, validation_issues=None, packaged_artifacts_info=None, handoff_summary=None,
        feedback_history=[], refinement_count=0, max_refinements=2, current_error=None, qa_agent_messages=[]
    )
    result = architect_agent_node(state)
    assert result['architectural_decision']['chosen_language'] == 'python'

def test_planner_agent_node_clarification(monkeypatch):
    monkeypatch.setattr('main_pipeline.agents.get_llm_instance', lambda *a, **kw: MockLLM({
        'clarification_questions': ['What should the function return?'], 'planned_task_description': None, 'planner_notes': None
    }))
    state = GraphState(
        initial_user_request='Test', architectural_decision={'chosen_language': 'python', 'framework_hint': 'standard_library', 'high_level_notes': 'Test'}, clarified_user_input=None,
        clarification_questions_for_user=None, planner_iteration_count=0, max_planner_iterations=2,
        llm_models_config={}, planned_task_description=None, planner_notes=None, task_description='',
        generated_test_cases=None, current_test_case_index=0, all_tests_passed=False, generated_code=None,
        current_test_status=None, current_test_message=None, test_results_summary=[], critique=None,
        validation_status=None, validation_issues=None, packaged_artifacts_info=None, handoff_summary=None,
        feedback_history=[], refinement_count=0, max_refinements=2, current_error=None, qa_agent_messages=[]
    )
    result = planner_agent_node(state)
    assert result['clarification_questions_for_user'] == ['What should the function return?']

def test_developer_agent_node_success(monkeypatch):
    monkeypatch.setattr('main_pipeline.agents.get_llm_instance', lambda *a, **kw: MockLLM('''```python\ndef foo():\n    return 42\n```'''))
    monkeypatch.setattr('main_pipeline.agents.extract_python_code', lambda x: 'def foo():\n    return 42')
    state = GraphState(
        initial_user_request='Test', architectural_decision=None, clarified_user_input=None,
        clarification_questions_for_user=None, planner_iteration_count=0, max_planner_iterations=2,
        llm_models_config={}, planned_task_description='def foo(): return 42', planner_notes=None, task_description='def foo(): return 42',
        generated_test_cases=None, current_test_case_index=0, all_tests_passed=False, generated_code=None,
        current_test_status=None, current_test_message=None, test_results_summary=[], critique=None,
        validation_status=None, validation_issues=None, packaged_artifacts_info=None, handoff_summary=None,
        feedback_history=[], refinement_count=0, max_refinements=2, current_error=None, qa_agent_messages=[]
    )
    result = developer_agent_node(state)
    assert 'def foo()' in result['generated_code']