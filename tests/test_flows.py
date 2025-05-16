import unittest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from flow import elicitation_flow, test_design_flow, initial_code_gen_flow, qa_validation_flow, critique_refine_flow, packaging_flow

class TestElicitationFlow(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_elicitation_plan_ready_first_try(self, mock_call_llm):
        mock_call_llm.side_effect = [
            '{"chosen_language": "python", "framework_hint": "standard_library", "high_level_notes": "Simple function."}',
            '{"planned_task_description": {"function_name": "greet"}, "planner_notes": "Be polite.", "clarification_questions": []}'
        ]
        shared_state = {
            "user_raw_request": "Make a greet function",
            "current_request_for_planner": "Make a greet function",
            "architectural_principles_context": "Keep it simple.",
            "planning_guidelines_context": "Be specific.",
            "planner_iteration_count": 0,
            "llm_models_config": {}
        }
        action = elicitation_flow.run(shared_state)
        self.assertEqual(action, "plan_ready_for_code")
        self.assertIsNotNone(shared_state.get("planned_task_description"))
        self.assertIsNone(shared_state.get("clarification_questions_for_user"))
        self.assertEqual(shared_state.get("planner_iteration_count"), 1)
        self.assertEqual(mock_call_llm.call_count, 2)

    @patch('nodes.call_llm')
    def test_elicitation_needs_clarification(self, mock_call_llm):
        mock_call_llm.side_effect = [
            '{"chosen_language": "python", "framework_hint": "standard_library", "high_level_notes": "Simple function."}',
            '{"clarification_questions": ["What should the function do?"]}',
            '{"clarification_questions": ["What should the function do?"]}'
        ]
        shared_state = {
            "user_raw_request": "Make a greet function",
            "current_request_for_planner": "Make a greet function",
            "architectural_principles_context": "Keep it simple.",
            "planning_guidelines_context": "Be specific.",
            "planner_iteration_count": 0,
            "llm_models_config": {}
        }
        action = elicitation_flow.run(shared_state)
        self.assertEqual(action, "clarification_needed")
        self.assertIsNotNone(shared_state.get("clarification_questions_for_user"))

class TestTestDesignFlow(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_test_design_flow_success(self, mock_call_llm):
        mock_call_llm.return_value = '{"test_cases": [{"inputs": [1,2], "expected_output": 3, "description": "Add."}]}'
        shared_state = {
            "planned_task_description": {"function_name": "add"},
            "planner_notes": "",
            "llm_models_config": {"developer_llm": "mock"}
        }
        action = test_design_flow.run(shared_state)
        self.assertEqual(action, "tests_ready")
        self.assertIsInstance(shared_state.get("generated_test_cases"), list)

class TestInitialCodeGenFlow(unittest.TestCase):
    @patch('nodes.call_llm')
    @patch('utils.tools.extract_python_code')
    def test_initial_code_gen_flow_success(self, mock_extract_code, mock_call_llm):
        mock_call_llm.return_value = "```python\ndef add(a, b):\n  return a + b\n```"
        mock_extract_code.return_value = "def add(a, b):\n  return a + b"
        shared_state = {
            "task_description": "Add two numbers.",
            "planner_notes": "",
            "coding_standards_context": "Use snake_case.",
            "critique_feedback": "N/A",
            "feedback_history": [],
            "llm_models_config": {"developer_llm": "mock"}
        }
        action = initial_code_gen_flow.run(shared_state)
        self.assertEqual(action, "code_ready_for_tests")
        self.assertIn("generated_code", shared_state)

class TestQAValidationFlow(unittest.TestCase):
    @patch('nodes.code_tester_tool')
    @patch('nodes.call_llm')
    def test_qa_validation_flow_success(self, mock_call_llm, mock_code_tester_tool):
        mock_code_tester_tool.return_value = [{"status": "success", "message": "OK", "test_case": {"description": "desc"}, "actual_output": 1}]
        mock_call_llm.return_value = '{"validation_passed": true, "issues_found": []}'
        shared_state = {
            "generated_code": "def foo(): return 1",
            "generated_test_cases": [{"inputs": [1], "expected_output": 1, "description": "desc", "function_name": "foo"}],
            "current_test_case_index": 0,
            "test_results_summary": [],
            "all_tests_passed": False,
            "task_description": "desc",
            "planner_notes": "notes",
            "validation_rules_context": "rules",
            "llm_models_config": {"validation_llm": "mock"}
        }
        action = qa_validation_flow.run(shared_state)
        self.assertEqual(action, "testing_error_or_done")
        self.assertIn("test_results_summary", shared_state)

class TestCritiqueRefineFlow(unittest.TestCase):
    @patch('nodes.call_llm')
    @patch('utils.tools.extract_python_code')
    def test_critique_refine_flow_success(self, mock_extract_code, mock_call_llm):
        mock_call_llm.side_effect = [
            '{"critique_feedback": "Try again."}',
            "```python\ndef add(a, b):\n  return a + b\n```"
        ]
        mock_extract_code.return_value = "def add(a, b):\n  return a + b"
        shared_state = {
            "task_description": "Add two numbers.",
            "planner_notes": "",
            "coding_standards_context": "Use snake_case.",
            "critique_feedback": "Try again.",
            "feedback_history": [],
            "llm_models_config": {"developer_llm": "mock", "critique_llm": "mock"}
        }
        action = critique_refine_flow.run(shared_state)
        self.assertIn(action, ["code_ready_for_tests", "code_generation_failed"])
        self.assertIn("generated_code", shared_state)

class TestPackagingFlow(unittest.TestCase):
    def test_packaging_flow_success(self):
        shared_state = {
            "generated_code": "def foo(): pass",
            "planned_task_description": {"function_name": "foo"}
        }
        action = packaging_flow.run(shared_state)
        self.assertEqual(action, "done")
        self.assertIn("packaged_artifacts_info", shared_state)