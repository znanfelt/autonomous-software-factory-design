# tests/test_nodes.py
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json # Ensure json is imported for tests that mock JSON string returns

# Adjust path to import from the application directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from nodes import (
    DeveloperNode, InitialRequestNode, ArchitectPlannerNode, 
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode,
    SimpleJsonOutputParser # Import if used for direct testing, though nodes use it internally
)
from utils.prompts import ( # Keep for reference, though not directly used in mocks here
    DEVELOPER_CODEGEN_PROMPT_TEMPLATE 
)
from utils.tools import extract_project_structure_from_llm # If testing its direct usage

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
        
        shared2 = {}
        action2 = self.node.post(shared2, "Test function request.", None)
        self.assertEqual(action2, "error_encountered")
        self.assertIn("current_error_message", shared2)

class TestArchitectPlannerNode(unittest.TestCase):
    def setUp(self):
        self.node = ArchitectPlannerNode()
        self.shared_state_base = {
            "current_request_for_planner": "Create a function to add two numbers.",
            "architectural_principles_context": "Principle: Use Python.",
            "planning_guidelines_context": "Guideline: Be clear.",
            "llm_models_config": {"architect_llm": "mock_arch", "planner_llm": "mock_plan"}
        }

    @patch('nodes.call_llm')
    def test_exec_plan_ready_first_try(self, mock_call_llm):
        mock_call_llm.side_effect = [
            json.dumps({"chosen_language": "python", "framework_hint": "standard_library", "complexity_assessment": "simple_function", "high_level_notes": "Simple adder."}),
            json.dumps({"planned_task_description": {"component_name": "add", "target_file": "main.py", "parameters": [{"name":"a","type":"int"}, {"name":"b","type":"int"}], "return_type": "int", "core_behavior": "returns sum of a and b"}, "planner_notes": "Keep it simple.", "clarification_questions": []})
        ]
        prep_data = self.node.prep(self.shared_state_base.copy())
        result = self.node.exec(prep_data)
        
        self.assertFalse(result.get("error"))
        self.assertFalse(result["needs_clarification"])
        self.assertIn("planned_task_description", result["planned_output"])
        self.assertEqual(result["planned_output"]["planned_task_description"]["component_name"], "add")
        self.assertEqual(mock_call_llm.call_count, 2)

    @patch('nodes.call_llm')
    def test_exec_needs_clarification(self, mock_call_llm):
        mock_call_llm.side_effect = [
            json.dumps({"chosen_language": "python", "framework_hint": "standard_library", "complexity_assessment": "unknown", "high_level_notes": "Vague request."}),
            json.dumps({"error": "Planner could not make a plan directly"}), # Simulate first planner call failing to make a plan
            json.dumps({"clarification_questions": ["What should the function return?", "What are the inputs?"]})
        ]
        prep_data = self.node.prep(self.shared_state_base.copy())
        result = self.node.exec(prep_data)
        
        self.assertFalse(result.get("error"))
        self.assertTrue(result["needs_clarification"])
        self.assertIn("clarification_questions", result["planned_output"])
        self.assertEqual(len(result["planned_output"]["clarification_questions"]), 2)
        self.assertEqual(mock_call_llm.call_count, 3) # Arch + PlannerCodegen(failed/ambiguous) + PlannerClar

    def test_post_plan_ready(self):
        shared = {"planner_iteration_count": 0}
        exec_res = {
            "architect_decision": {"chosen_language": "python"},
            "planned_output": {"planned_task_description": {"component_name": "test_func"}, "planner_notes": "notes", "suggested_project_structure": [{"file_name":"test.py", "purpose":"test"}]},
            "needs_clarification": False
        }
        action = self.node.post(shared, {}, exec_res)
        self.assertEqual(action, "plan_ready_for_code")
        self.assertIsNotNone(shared.get("planned_task_description"))
        self.assertEqual(shared.get("planner_notes"), "notes")
        self.assertEqual(shared.get("suggested_project_outline")[0]["file_name"], "test.py")

    def test_post_clarification_needed(self):
        shared = {"planner_iteration_count": 0}
        exec_res = {
            "architect_decision": {"chosen_language": "python"},
            "planned_output": {"clarification_questions": ["What is x?"]},
            "needs_clarification": True
        }
        action = self.node.post(shared, {}, exec_res)
        self.assertEqual(action, "clarification_needed")
        self.assertEqual(shared.get("clarification_questions_for_user"), ["What is x?"])

class TestDeveloperNode(unittest.TestCase):
    def setUp(self):
        self.node = DeveloperNode()
        self.shared_state_base = {
            "planned_task_description": {
                "component_name": "add_numbers", "target_file": "calculator.py",
                "parameters": [{"name": "a", "type": "int"}, {"name": "b", "type": "int"}],
                "return_type": "int", "core_behavior": "Return the sum of a and b."
            },
            "planner_notes": "Handle integer inputs.",
            "coding_standards_context": "Use snake_case.",
            "critique_feedback": "N/A",
            "feedback_history": [],
            "llm_models_config": {"developer_llm": "mock_dev_model"}
        }

    def test_prep_success(self):
        prep_res = self.node.prep(self.shared_state_base.copy())
        self.assertNotIn("error", prep_res)
        self.assertIn("planned_task_description_json_str", prep_res)
        self.assertIn('"component_name": "add_numbers"', prep_res["planned_task_description_json_str"])

    @patch('nodes.call_llm')
    def test_exec_success_project_structure(self, mock_call_llm):
        expected_project_json_str = json.dumps({
            "files": [{"name": "calculator.py", "content": "def add_numbers(a, b):\n  return a + b"}],
            "entry_point_file": "calculator.py",
            "main_function_to_test": "add_numbers"
        })
        mock_call_llm.return_value = expected_project_json_str
        
        prep_data = self.node.prep(self.shared_state_base.copy())
        exec_result = self.node.exec(prep_data)
        
        self.assertIsNotNone(exec_result)
        self.assertNotIn("error", exec_result)
        self.assertIsInstance(exec_result.get("files"), list)
        self.assertEqual(exec_result["files"][0]["name"], "calculator.py")
        self.assertIn("def add_numbers(a, b):", exec_result["files"][0]["content"])
        mock_call_llm.assert_called_once()

    @patch('nodes.call_llm')
    def test_exec_llm_returns_error_json_for_project(self, mock_call_llm):
        mock_call_llm.return_value = json.dumps({"error": "LLM project gen error"})
        prep_data = self.node.prep(self.shared_state_base.copy())
        exec_result = self.node.exec(prep_data)
        self.assertIn("error", exec_result)
        self.assertIn("Could not parse LLM output for project structure", exec_result["error"])


    def test_post_success_project_structure(self):
        local_shared = self.shared_state_base.copy()
        project_structure = {"files": [{"name": "main.py", "content": "code"}]}
        action = self.node.post(local_shared, {}, project_structure)
        self.assertEqual(local_shared["generated_project_structure"], project_structure)
        self.assertEqual(action, "code_ready_for_tests")

# ... (Similar updates for TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode)
# The key is to mock call_llm to return JSON strings where expected,
# and for nodes that call tools (like QANode), mock the tool.

class TestTestCaseDesignerNode(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_exec_success(self, mock_call_llm):
        node = TestCaseDesignerNode()
        expected_test_cases_json_str = json.dumps({
            "test_cases": [{
                "target_file": "main.py", "target_function": "add",
                "inputs": [1, 2], "expected_output": 3, "description": "Add positive numbers."
            }]
        })
        mock_call_llm.return_value = expected_test_cases_json_str
        
        prep_data = node.prep({
            "planned_task_description": {"component_name": "add", "target_file": "main.py", "parameters":[]},
            "planner_notes": "", "llm_models_config": {}
        })
        result = node.exec(prep_data)
        
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["expected_output"], 3)
        self.assertEqual(result[0]["target_file"], "main.py")

class TestQANode(unittest.TestCase):
    @patch('nodes.code_tester_tool')
    def test_exec_success(self, mock_code_tester_tool):
        node = QANode()
        mock_code_tester_tool.return_value = [{"status": "success", "message": "OK", "test_case": {"description": "desc"}, "actual_output": 1}]
        
        prep_data = node.prep({
            "generated_project_structure": {"files": [{"name":"main.py", "content":"def foo(): return 1"}]},
            "generated_test_cases": [{"target_file":"main.py", "target_function":"foo", "inputs": [], "expected_output": 1, "description": "desc"}],
            "current_test_case_index": 0
        })
        result = node.exec(prep_data)
        self.assertEqual(result["status"], "success")

class TestValidationNode(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_exec_success(self, mock_call_llm):
        node = ValidationNode()
        mock_call_llm.return_value = json.dumps({"validation_passed": True, "issues_found": []})
        prep_data = node.prep({
            "generated_project_structure": {"files":[{"name":"main.py", "content":"valid code"}]},
            "planned_task_description": {"component_name":"test"}, # Needs to be a dict
            "planner_notes": "notes",
            "validation_rules_context": "rules",
            "llm_models_config": {}
        })
        result = node.exec(prep_data)
        self.assertTrue(result["validation_passed"])

class TestCritiqueNode(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_exec_success(self, mock_call_llm):
        node = CritiqueNode()
        mock_call_llm.return_value = json.dumps({"critique_feedback": "Looks good."})
        prep_data = node.prep({
            "planned_task_description": {"component_name":"test"}, # Needs to be dict
            "planner_notes": "notes",
            "generated_project_structure": {"files":[{"name":"main.py", "content":"code"}]},
            "test_failure_message": "fail",
            "validation_issues": [],
            "user_rejection_reason": "none",
            "debugging_tips_context": "tips",
            "llm_models_config": {}
        })
        result = node.exec(prep_data)
        self.assertEqual(result, "Looks good.")

class TestPackageNode(unittest.TestCase):
    def test_exec_success(self):
        node = PackageNode()
        prep_data = node.prep({
            "generated_project_structure": {"files":[{"name":"main.py", "content":"def foo(): pass"}], "entry_point_file": "main.py"},
            "planned_task_description": {"component_name": "foo"}
        })
        result = node.exec(prep_data)
        self.assertIn("code_file_content", result["packaged_artifacts_info"]["project_files"][0]) # Adjust based on new structure
        self.assertIn("readme_content", result["packaged_artifacts_info"]["project_files"][0]) # This needs adjustment based on actual packaging logic
        self.assertEqual(result["main_component_name"], "foo")

    def test_exec_missing_project_structure(self):
        node = PackageNode()
        prep_data = node.prep({
            "planned_task_description": {"component_name": "foo"}
            # "generated_project_structure" is missing
        })
        result = node.exec(prep_data)
        self.assertIn("error", result)
        self.assertIn("Generated project structure missing", result["error"].lower())

    def test_exec_missing_component_name_in_plan(self):
        node = PackageNode()
        prep_data = node.prep({
            "generated_project_structure": {"files":[{"name":"main.py", "content":"def foo(): pass"}]},
            "planned_task_description": {} # Missing component_name
        })
        result = node.exec(prep_data)
        self.assertIn("error", result)
        self.assertIn("component_name missing", result["error"].lower())


if __name__ == '__main__':
    unittest.main()