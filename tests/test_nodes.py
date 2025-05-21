# tests/test_nodes.py
import unittest
from unittest.mock import (
    patch,
    MagicMock,
)  # Ensure MagicMock is imported if used, though not in current snippets
import sys
import os
import json  # Ensure json is imported for tests that mock JSON string returns

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from nodes import (
    DeveloperNode,
    InitialRequestNode,
    ArchitectPlannerNode,
    TestCaseDesignerNode,
    QANode,
    ValidationNode,
    CritiqueNode,
    PackageNode,
    SecurityComplianceNode,
)
from utils.prompts import DEVELOPER_CODEGEN_PROMPT_TEMPLATE

# from utils.tools import extract_project_structure_from_llm # Not directly tested here


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
        action = self.node.post(
            shared, "Test function request.", "Test function request."
        )
        self.assertEqual(action, "default")
        self.assertEqual(shared["initial_user_request"], "Test function request.")
        self.assertEqual(
            shared["current_request_for_planner"], "Test function request."
        )
        shared2 = {}
        action2 = self.node.post(shared2, "Test function request.", None)
        self.assertEqual(action2, "error_encountered")
        self.assertIn("current_error_message", shared2)


class TestArchitectPlannerNode(unittest.TestCase):
    # ... (ArchitectPlannerNode tests remain the same as they were likely passing or had different issues)
    def setUp(self):
        self.node = ArchitectPlannerNode()
        self.shared_state_base = {
            "current_request_for_planner": "Create a function to add two numbers.",
            "architectural_principles_context": "Principle: Use Python.",
            "planning_guidelines_context": "Guideline: Be clear.",
            "llm_models_config": {
                "architect_llm": "mock_arch",
                "planner_llm": "mock_plan",
            },
        }

    @patch("nodes.call_llm")
    def test_exec_plan_ready_first_try(self, mock_call_llm):
        mock_call_llm.side_effect = [
            json.dumps(
                {
                    "chosen_language": "python",
                    "framework_hint": "standard_library",
                    "complexity_assessment": "simple_function",
                    "high_level_notes": "Simple adder.",
                }
            ),
            json.dumps(
                {
                    "planned_task_description": {
                        "component_name": "add",
                        "target_file": "main.py",
                    },
                    "planner_notes": "Be polite.",
                    "clarification_questions": [],
                }
            ),
        ]
        prep_data = self.node.prep(self.shared_state_base.copy())
        result = self.node.exec(prep_data)
        self.assertFalse(result.get("error"))
        self.assertFalse(result["needs_clarification"])
        self.assertIn("planned_task_description", result["planned_output"])

    @patch("nodes.call_llm")
    def test_exec_needs_clarification(self, mock_call_llm):
        mock_call_llm.side_effect = [
            json.dumps(
                {
                    "chosen_language": "python",
                    "framework_hint": "standard_library",
                    "complexity_assessment": "unknown",
                    "high_level_notes": "Vague request.",
                }
            ),
            json.dumps({"error": "Planner could not make a plan directly"}),
            json.dumps({"clarification_questions": ["What should the function do?"]}),
        ]
        prep = self.node.prep(self.shared_state_base.copy())
        result = self.node.exec(prep)
        self.assertTrue(result["needs_clarification"])


class TestDeveloperNode(
    unittest.TestCase
):  # Assuming previous DeveloperNode tests were fine
    def setUp(self):
        self.node = DeveloperNode()
        self.shared_state = {
            "planned_task_description": {
                "component_name": "add",
                "target_file": "main.py",
            },
            "suggested_project_outline": [
                {"file_name": "main.py", "purpose": "main logic"}
            ],
            "planner_notes": "Ensure it handles integers.",
            "coding_standards_context": "Use snake_case.",
            "critique_feedback": "N/A",
            "feedback_history": [],
            "llm_models_config": {"developer_llm": "mock_model"},
        }

    @patch("nodes.call_llm")
    def test_exec_success_code_extraction(self, mock_call_llm):
        mock_call_llm.return_value = json.dumps(
            {"files": [{"name": "main.py", "content": "def add(a,b): return a+b"}]}
        )
        prep_data = self.node.prep(self.shared_state)
        exec_result = self.node.exec(prep_data)
        self.assertIsInstance(exec_result, dict)
        self.assertIn("files", exec_result)


class TestTestCaseDesignerNode(unittest.TestCase):  # Assuming previous tests were fine
    @patch("nodes.call_llm")
    def test_exec_success(self, mock_call_llm):
        node = TestCaseDesignerNode()
        mock_call_llm.return_value = json.dumps(
            {
                "test_cases": [
                    {
                        "target_file": "main.py",
                        "target_function": "add",
                        "inputs": (1, 2),
                        "expected_output": 3,
                        "description": "Add.",
                    }
                ]
            }
        )
        prep = node.prep(
            {
                "planned_task_description": {
                    "component_name": "add",
                    "target_file": "main.py",
                },
                "planner_notes": "",
                "llm_models_config": {},
                "current_project_structure_json_str": "{}",
                "critique_feedback_for_tests": "N/A",
            }
        )
        result = node.exec(prep)
        self.assertIsInstance(result, list)


class TestQANode(unittest.TestCase):  # Assuming previous tests were fine
    @patch("nodes.code_tester_tool")
    def test_exec_success(self, mock_code_tester_tool):
        node = QANode()
        mock_code_tester_tool.return_value = [
            {
                "status": "success",
                "message": "OK",
                "test_case": {"description": "desc"},
                "actual_output": 1,
            }
        ]
        prep = node.prep(
            {
                "generated_project_structure": {
                    "files": [{"name": "main.py", "content": "def foo(): return 1"}]
                },
                "generated_test_cases": [
                    {
                        "target_file": "main.py",
                        "target_function": "foo",
                        "inputs": (),
                        "expected_output": 1,
                        "description": "desc",
                    }
                ],
                "current_test_case_index": 0,
            }
        )
        result = node.exec(prep)
        self.assertEqual(result["status"], "success")


class TestValidationNode(unittest.TestCase):  # Assuming previous tests were fine
    @patch("nodes.call_llm")
    def test_exec_success(self, mock_call_llm):
        node = ValidationNode()
        mock_call_llm.return_value = json.dumps(
            {"validation_passed": True, "issues_found": []}
        )
        prep = node.prep(
            {
                "generated_project_structure": {
                    "files": [{"name": "main.py", "content": "valid code"}]
                },
                "planned_task_description": {"component_name": "test"},
                "planner_notes": "notes",
                "validation_rules_context": "rules",
                "llm_models_config": {},
            }
        )
        result = node.exec(prep)
        self.assertTrue(result["validation_passed"])


class TestCritiqueNode(unittest.TestCase):  # Assuming previous tests were fine
    @patch("nodes.call_llm")
    def test_exec_success(self, mock_call_llm):
        node = CritiqueNode()
        mock_call_llm.return_value = json.dumps({"critique_feedback": "Looks good."})
        prep = node.prep(
            {
                "planned_task_description": {"component_name": "test"},
                "generated_project_structure": {
                    "files": [{"name": "main.py", "content": "code"}]
                },
                "planner_notes": "notes",
                "test_failure_message": "fail",
                "validation_issues": [],
                "user_rejection_reason": "none",
                "debugging_tips_context": "tips",
                "llm_models_config": {},
            }
        )
        result = node.exec(prep)
        self.assertIn("Looks good.", result)


class TestPackageNode(unittest.TestCase):
    def test_exec_success(self):
        node = PackageNode()
        prep_data = node.prep(
            {
                "generated_project_structure": {
                    "files": [{"name": "main.py", "content": "def foo(): pass"}],
                    "entry_point_file": "main.py",
                },
                "planned_task_description": {
                    "component_name": "foo",
                    "target_file": "main.py",
                },
            }
        )
        result = node.exec(prep_data)
        self.assertNotIn("error", result)
        self.assertIn("packaged_artifacts_info", result)
        self.assertIn("project_files", result["packaged_artifacts_info"])
        self.assertEqual(
            result["packaged_artifacts_info"]["project_files"][0]["name"], "main.py"
        )
        self.assertEqual(
            result["packaged_artifacts_info"]["project_files"][0]["content"],
            "def foo(): pass",
        )
        self.assertIn("handoff_summary", result)
        self.assertEqual(result["main_component_name"], "foo")

    def test_exec_missing_project_structure(self):
        node = PackageNode()
        # Simulate prep creating the error dict because shared state was bad
        prep_data_for_exec = node.prep(
            {
                "planned_task_description": {"component_name": "foo"}
                # "generated_project_structure" is missing from shared
            }
        )
        # Now, exec should receive this error dict from prep
        result = node.exec(prep_data_for_exec)
        self.assertIn("error", result)
        # The error message comes from PackageNode.prep if structure is invalid
        self.assertEqual(
            result["error"],
            "Generated project structure missing or invalid for packaging.",
        )

    def test_exec_missing_component_name_in_plan(self):
        node = PackageNode()
        prep_data_for_exec = node.prep(
            {
                "generated_project_structure": {
                    "files": [{"name": "main.py", "content": "def foo(): pass"}]
                },
                "planned_task_description": {},  # Missing component_name
            }
        )
        result = node.exec(
            prep_data_for_exec
        )  # prep_data is valid, exec will find missing component_name
        self.assertIn("error", result)
        # This error is now generated inside exec if component_name is missing
        self.assertEqual(
            result["error"],
            "component_name missing in planned_task_description for packaging.",
        )


if __name__ == "__main__":
    unittest.main()
