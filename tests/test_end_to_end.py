import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from main_pipeline.state import GraphState
from main_pipeline.graph import build_graph

class DummyApp:
    def __init__(self, states):
        self.states = states
        self.idx = 0
    def stream(self, state, _):
        for s in self.states:
            yield s
        yield "STREAM_ENDED_SENTINEL"

def test_end_to_end_pipeline(monkeypatch):
    # Simulate a pipeline with 3 steps and a final state
    states = [
        {'architect_agent_node': {'architectural_decision': {'chosen_language': 'python'}}},
        {'planner_agent_node': {'planned_task_description': 'desc'}},
        {'test_case_designer_node': {'generated_test_cases': [{'function_name': 'foo', 'inputs': (), 'expected_output': 1, 'description': 'desc'}]}},
        {'developer_agent_node': {'generated_code': 'def foo(): return 1'}},
        {'qa_agent_node': {'current_test_status': 'success'}},
        {'validation_agent_node': {'validation_status': 'pass'}},
        {'artifact_packaging_node': {'packaged_artifacts_info': {'code_file': 'foo.py'}}},
        {'handoff_node': {'handoff_summary': 'done'}}
    ]
    monkeypatch.setattr('main_pipeline.graph.build_graph', lambda: DummyApp(states))
    state = GraphState(
        initial_user_request='Test', architectural_decision=None, clarified_user_input=None,
        clarification_questions_for_user=None, planner_iteration_count=0, max_planner_iterations=2,
        llm_models_config={}, planned_task_description=None, planner_notes=None, task_description='',
        generated_test_cases=None, current_test_case_index=0, all_tests_passed=False, generated_code=None,
        current_test_status=None, current_test_message=None, test_results_summary=[], critique=None,
        validation_status=None, validation_issues=None, packaged_artifacts_info=None, handoff_summary=None,
        feedback_history=[], refinement_count=0, max_refinements=2, current_error=None, qa_agent_messages=[]
    )
    app = build_graph()
    stream = app.stream(state, {})
    outputs = list(stream)
    assert outputs[-1] == "STREAM_ENDED_SENTINEL"