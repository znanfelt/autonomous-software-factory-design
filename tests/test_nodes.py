import unittest
from unittest.mock import patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from nodes import DeveloperNode, InitialRequestNode, ArchitectPlannerNode, TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
from utils.prompts import DEVELOPER_CODEGEN_PROMPT_TEMPLATE

class TestDeveloperNode(unittest.TestCase):
    def setUp(self):
        self.node = DeveloperNode()
        self.shared_state = {
            "developer_task_description": "Create a function to add two numbers.",
            "planner_notes": "Ensure it handles integers.",
            "coding_standards_context": "Use snake_case.",
            "critique_feedback": "N/A",
            "feedback_history": [],
            "llm_models_config": {"developer_llm": "mock_model"}
        }

    def test_prep_success(self):
        prep_result = self.node.prep(self.shared_state.copy())
        self.assertIsNotNone(prep_result)
        self.assertEqual(prep_result["task_description"], "Create a function to add two numbers.")

    def test_prep_missing_task_description(self):
        invalid_shared = self.shared_state.copy()
        del invalid_shared["developer_task_description"]
        prep_result = self.node.prep(invalid_shared)
        self.assertIsNotNone(prep_result) # prep now returns a dict even on error
        self.assertIn("error", prep_result)
        self.assertIn("Developer task description missing", prep_result["error"])

    @patch('nodes.call_llm') # Mocks call_llm within the nodes.py module
    def test_exec_success_code_extraction(self, mock_call_llm):
        mock_call_llm.return_value = "```python\ndef add(a, b):\n  return a + b\n```"
        prep_data = self.node.prep(self.shared_state.copy()) # Get valid prep_res
        
        # Test the formatting part that caused issues, if it's complex within exec
        # For DEVELOPER_CODEGEN_PROMPT_TEMPLATE, it is complex
        try:
            DEVELOPER_CODEGEN_PROMPT_TEMPLATE.format(
                developer_task_description=prep_data["task_description"],
                developer_notes=prep_data["planner_notes"],
                coding_standards_context=prep_data["coding_standards_context"],
                critique_message=prep_data["critique_feedback"],
                full_feedback_history=prep_data["feedback_history"]
            )
        except KeyError as e:
            self.fail(f"Prompt formatting failed in test with KeyError: {e}")

        exec_result = self.node.exec(prep_data)
        self.assertEqual(exec_result, "def add(a, b):\n  return a + b")
        mock_call_llm.assert_called_once()

    @patch('nodes.call_llm')
    def test_exec_llm_returns_error_json(self, mock_call_llm):
        mock_call_llm.return_value = '{"error": "LLM API limit reached"}' # call_llm itself returns this
        prep_data = self.node.prep(self.shared_state.copy())
        exec_result = self.node.exec(prep_data)
        self.assertIn("Error: LLM call failed.", exec_result)

    @patch('nodes.call_llm')
    def test_exec_no_code_block(self, mock_call_llm):
        mock_call_llm.return_value = "This is not code."
        prep_data = self.node.prep(self.shared_state.copy())
        exec_result = self.node.exec(prep_data)
        self.assertIn("Error: No code block found.", exec_result)
        
    def test_post_success(self):
        local_shared = self.shared_state.copy()
        # Simulate a successful exec result
        action = self.node.post(local_shared, {"task_description": "..."}, "def test_func(): pass")
        self.assertEqual(local_shared["generated_code"], "def test_func(): pass")
        self.assertEqual(action, "code_ready_for_tests")

    def test_post_code_generation_failure(self):
        local_shared = self.shared_state.copy()
        exec_error_msg = "Error: No code block found."
        action = self.node.post(local_shared, {"task_description": "..."}, exec_error_msg)
        self.assertIsNone(local_shared["generated_code"])
        self.assertEqual(local_shared["current_error_message"], exec_error_msg)
        self.assertEqual(action, "code_generation_failed")

class TestInitialRequestNode(unittest.TestCase):
    def setUp(self):
        self.node = InitialRequestNode()
        self.shared_state = {"user_raw_request": "Test function request."}

    def test_prep(self):
        result = self.node.prep(self.shared_state)
        self.assertEqual(result, "Test function request.")

    def test_exec(self):
        result = self.node.exec("Test function request.")
        self.assertEqual(result, "Test function request.")
        result_none = self.node.exec(None)
        self.assertIsNone(result_none)

    def test_post(self):
        shared = {}
        action = self.node.post(shared, "Test function request.", "Test function request.")
        self.assertEqual(action, "default")
        self.assertEqual(shared["initial_user_request"], "Test function request.")
        self.assertEqual(shared["current_request_for_planner"], "Test function request.")
        # Test error case
        shared2 = {}
        action2 = self.node.post(shared2, "Test function request.", None)
        self.assertEqual(action2, "error_encountered")
        self.assertIn("current_error_message", shared2)

class TestArchitectPlannerNode(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_exec_success_and_clarification(self, mock_call_llm):
        from nodes import ArchitectPlannerNode
        node = ArchitectPlannerNode()
        # Simulate architect LLM returns valid JSON
        mock_call_llm.side_effect = [
            '{"chosen_language": "python", "framework_hint": "standard_library", "high_level_notes": "Simple."}',
            '{"planned_task_description": {"function_name": "foo", "params": [], "return_type": "int", "core_behavior": "return 1"}, "planner_notes": "Do it simply.", "clarification_questions": []}'
        ]
        prep = node.prep({
            "current_request_for_planner": "Test req",
            "architectural_principles_context": "Principles",
            "planning_guidelines_context": "Guidelines",
            "llm_models_config": {"architect_llm": "mock", "planner_llm": "mock"}
        })
        result = node.exec(prep)
        self.assertIn("planned_output", result)
        self.assertFalse(result["needs_clarification"])

    @patch('nodes.call_llm')
    def test_exec_needs_clarification(self, mock_call_llm):
        from nodes import ArchitectPlannerNode
        node = ArchitectPlannerNode()
        # First call returns architect, second returns planner with clarification needed, third returns clarification questions
        mock_call_llm.side_effect = [
            '{"chosen_language": "python", "framework_hint": "standard_library", "high_level_notes": "Simple."}',
            '{"clarification_questions": ["What should the function do?"]}',
            '{"clarification_questions": ["What should the function do?"]}'
        ]
        prep = node.prep({
            "current_request_for_planner": "Test req",
            "architectural_principles_context": "Principles",
            "planning_guidelines_context": "Guidelines",
            "llm_models_config": {"architect_llm": "mock", "planner_llm": "mock"}
        })
        result = node.exec(prep)
        self.assertTrue(result["needs_clarification"])
        self.assertIn("clarification_questions", result["planned_output"])

class TestTestCaseDesignerNode(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_exec_success(self, mock_call_llm):
        from nodes import TestCaseDesignerNode
        node = TestCaseDesignerNode()
        mock_call_llm.return_value = '{"test_cases": [{"inputs": [1,2], "expected_output": 3, "description": "Add."}]}'
        prep = node.prep({
            "planned_task_description": {"function_name": "add"},
            "planner_notes": "",
            "llm_models_config": {"developer_llm": "mock"}
        })
        result = node.exec(prep)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["expected_output"], 3)

class TestQANode(unittest.TestCase):
    @patch('nodes.code_tester_tool')
    def test_exec_success(self, mock_code_tester_tool):
        from nodes import QANode
        node = QANode()
        mock_code_tester_tool.return_value = [{"status": "success", "message": "OK", "test_case": {"description": "desc"}, "actual_output": 1}]
        prep = node.prep({
            "generated_code": "def foo(): return 1",
            "generated_test_cases": [{"inputs": [1], "expected_output": 1, "description": "desc", "function_name": "foo"}],
            "current_test_case_index": 0
        })
        result = node.exec(prep)
        self.assertEqual(result["status"], "success")

class TestValidationNode(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_exec_success(self, mock_call_llm):
        from nodes import ValidationNode
        node = ValidationNode()
        mock_call_llm.return_value = '{"validation_passed": true, "issues_found": []}'
        prep = node.prep({
            "generated_code": "def foo(): pass",
            "task_description": "desc",
            "planner_notes": "notes",
            "validation_rules_context": "rules",
            "llm_models_config": {"validation_llm": "mock"}
        })
        result = node.exec(prep)
        self.assertTrue(result["validation_passed"])

class TestCritiqueNode(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_exec_success(self, mock_call_llm):
        from nodes import CritiqueNode
        node = CritiqueNode()
        mock_call_llm.return_value = '{"critique_feedback": "Looks good."}'
        prep = node.prep({
            "task_description": "desc",
            "planner_notes": "notes",
            "generated_code": "def foo(): pass",
            "test_failure_message": "fail",
            "validation_issues": [],
            "user_rejection_reason": "none",
            "debugging_tips_context": "tips",
            "llm_models_config": {"critique_llm": "mock"}
        })
        result = node.exec(prep)
        self.assertIn("Looks good.", result)

class TestPackageNode(unittest.TestCase):
    def test_exec_success(self):
        from nodes import PackageNode
        node = PackageNode()
        prep = node.prep({
            "generated_code": "def foo(): pass",
            "planned_task_description": {"function_name": "foo"}
        })
        result = node.exec(prep)
        self.assertIn("code_file_content", result)
        self.assertIn("readme_content", result)
        self.assertIn("function_name", result)

    def test_exec_missing_code(self):
        from nodes import PackageNode
        node = PackageNode()
        prep = node.prep({
            "planned_task_description": {"function_name": "foo"}
        })
        result = node.exec(prep)
        self.assertIn("error", result)
        self.assertIn("generated_code missing", result["error"])

    def test_exec_missing_function_name(self):
        from nodes import PackageNode
        node = PackageNode()
        prep = node.prep({
            "generated_code": "def foo(): pass",
            "planned_task_description": {}
        })
        result = node.exec(prep)
        self.assertIn("error", result)
        self.assertIn("function_name missing", result["error"])
