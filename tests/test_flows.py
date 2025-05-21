# tests/test_flows.py
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json # For creating mock JSON strings

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flow import (
    elicitation_flow, 
    test_design_flow, 
    code_generation_flow, 
    qa_validation_security_flow, 
    critique_generation_flow, 
    packaging_flow
)
# Nodes are implicitly tested through the flows, but we mock their LLM calls

class TestElicitationFlow(unittest.TestCase):
    @patch('nodes.call_llm') # Mock at the nodes module level
    def test_elicitation_plan_ready_first_try(self, mock_call_llm):
        # ArchitectPlannerNode makes 2 calls
        mock_call_llm.side_effect = [
            json.dumps({"chosen_language": "python", "framework_hint": "standard_library", "complexity_assessment": "simple_function", "high_level_notes": "Simple function."}),
            json.dumps({"planned_task_description": {"component_name": "greet", "target_file": "main.py"}, "planner_notes": "Be polite.", "clarification_questions": []})
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
        # Architect call, then Planner attempts codegen (finds ambiguous), then Planner requests clarification
        mock_call_llm.side_effect = [
            json.dumps({"chosen_language": "python", "framework_hint": "standard_library", "complexity_assessment": "unknown", "high_level_notes": "Vague request."}),
            json.dumps({"error": "Cannot make plan, ambiguous"}), # Simulate planner failing to make direct plan
            json.dumps({"clarification_questions": ["What should the function do?"]})
        ]
        shared_state = {
            "user_raw_request": "Make a vague function",
            "current_request_for_planner": "Make a vague function",
            "architectural_principles_context": "Keep it simple.",
            "planning_guidelines_context": "Be specific.",
            "planner_iteration_count": 0,
            "llm_models_config": {}
        }
        action = elicitation_flow.run(shared_state)
        self.assertEqual(action, "clarification_needed")
        self.assertIsNotNone(shared_state.get("clarification_questions_for_user"))
        self.assertEqual(mock_call_llm.call_count, 3)

class TestTestDesignFlow(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_test_design_flow_success(self, mock_call_llm):
        mock_call_llm.return_value = json.dumps({
            "test_cases": [{
                "target_file": "main.py", "target_function": "add",
                "inputs": (1, 2), "expected_output": 3, "description": "Add positive numbers."
            }]
        })
        shared_state = {
            "planned_task_description": {"component_name": "add", "target_file": "main.py", "parameters":[]}, # This is now a dict
            "planner_notes": "",
            "llm_models_config": {"test_designer_llm": "mock"}
        }
        action = test_design_flow.run(shared_state)
        self.assertEqual(action, "tests_ready")
        self.assertIsInstance(shared_state.get("generated_test_cases"), list)
        self.assertEqual(shared_state["generated_test_cases"][0]["target_function"], "add")

class TestInitialCodeGenFlow(unittest.TestCase):
    @patch('nodes.call_llm')
    def test_initial_code_gen_flow_success(self, mock_call_llm):
        mock_call_llm.return_value = json.dumps({
            "files": [{"name": "main.py", "content": "def add(a, b):\n  return a + b"}],
            "entry_point_file": "main.py", "main_function_to_test": "add"
        })
        shared_state = {
            "planned_task_description": {"component_name": "add", "target_file":"main.py"}, # Dict
            "developer_task_description": json.dumps({"component_name": "add", "target_file":"main.py"}), # JSON string for prompt
            "planner_notes": "",
            "coding_standards_context": "Use snake_case.",
            "critique_feedback": "N/A",
            "feedback_history": [],
            "llm_models_config": {"developer_llm": "mock"}
        }
        action = code_generation_flow.run(shared_state)
        self.assertEqual(action, "code_ready_for_tests")
        self.assertIn("generated_project_structure", shared_state)
        self.assertEqual(shared_state["generated_project_structure"]["files"][0]["name"], "main.py")

class TestQAValidationFlow(unittest.TestCase):
    @patch('nodes.code_tester_tool')
    @patch('nodes.call_llm') # For ValidationNode
    def test_qa_validation_security_flow_all_pass(self, mock_call_llm_validation, mock_code_tester_tool):
        mock_code_tester_tool.return_value = [{"status": "success", "message": "OK", "test_case": {"description": "desc"}, "actual_output": 1}]
        mock_call_llm_validation.return_value = json.dumps({"validation_passed": True, "issues_found": []})
        
        shared_state = {
            "generated_project_structure": {"files": [{"name":"main.py", "content":"def foo(): return 1"}], "entry_point_file":"main.py"},
            "generated_test_cases": [{"target_file":"main.py", "target_function":"foo", "inputs": (), "expected_output": 1, "description": "desc"}],
            "current_test_case_index": 0,
            "test_results_summary": [],
            "all_tests_passed": False,
            "planned_task_description": {"component_name":"foo", "target_file":"main.py"}, # For ValidationNode
            "planner_notes": "", # For ValidationNode
            "validation_rules_context": "rules", # For ValidationNode
            "llm_models_config": {"validation_llm": "mock"}
        }
        action = qa_validation_security_flow.run(shared_state) # Last node is ValidationNode, post() returns None ("default")
        self.assertIsNone(action) # Default action from ValidationNode's post
        self.assertTrue(shared_state["all_tests_passed"])
        self.assertEqual(shared_state["validation_status"], "pass")

    @patch('nodes.code_tester_tool')
    @patch('nodes.call_llm')
    def test_qa_validation_security_flow_test_fail(self, mock_call_llm_validation, mock_code_tester_tool):
        mock_code_tester_tool.return_value = [{"status": "fail", "message": "Bad output", "test_case": {"description": "desc"}, "actual_output": 0}]
        # Validation might still be called, ensure it can run
        mock_call_llm_validation.return_value = json.dumps({"validation_passed": True, "issues_found": []})

        shared_state = {
            "generated_project_structure": {"files": [{"name":"main.py", "content":"def foo(): return 0"}]},
            "generated_test_cases": [{"target_file":"main.py", "target_function":"foo", "inputs": (), "expected_output": 1, "description": "desc"}],
            "current_test_case_index": 0,
            "test_results_summary": [],
            "all_tests_passed": True, # Start assuming pass
            "planned_task_description": {"component_name":"foo", "target_file":"main.py"},
            "planner_notes": "", "validation_rules_context": "rules", "llm_models_config": {}
        }
        action = qa_validation_security_flow.run(shared_state)
        self.assertIsNone(action)
        self.assertFalse(shared_state["all_tests_passed"])
        # Validation might still pass if the code is valid but logically wrong for the test
        self.assertEqual(shared_state["validation_status"], "pass")


class TestCritiqueRefineFlow(unittest.TestCase):
    @patch('nodes.call_llm') # This will mock call_llm for both CritiqueNode and DeveloperNode
    def test_critique_refine_flow_success(self, mock_call_llm):
        # 1st call (CritiqueNode): LLM generates critique
        # 2nd call (DeveloperNode): LLM generates refined code (as project structure)
        mock_call_llm.side_effect = [
            json.dumps({"critique_feedback": "Needs to handle edge cases."}),
            json.dumps({
                "files": [{"name": "main_v2.py", "content": "def refined_func():\n  # handles edge cases\n  return True"}],
                "entry_point_file": "main_v2.py"
            })
        ]
        shared_state = {
            "planned_task_description": {"component_name": "my_func", "target_file":"main.py"},
            "developer_task_description": json.dumps({"component_name": "my_func", "target_file":"main.py"}), # Stringified plan
            "generated_project_structure": {"files":[{"name":"main.py", "content":"def my_func(): return False"}]},
            "current_test_message": "Test failed for input X.",
            "validation_issues": ["Docstring missing."],
            "user_rejection_reason": "It's not working as expected.",
            "debugging_tips_context": "Check edge cases.",
            "coding_standards_context": "Use docstrings.",
            "feedback_history": ["Previous feedback..."], # For DeveloperNode
            "refinement_count": 0, # Before this flow, will be incremented by DeveloperNode
            "llm_models_config": {}
        }
        from flow import refinement_flow
        action = refinement_flow.run(shared_state)
        # Critique feedback is cleared after DeveloperNode, so only check project structure and action
        self.assertIsNotNone(shared_state.get("generated_project_structure"))
        self.assertEqual(shared_state["generated_project_structure"]["files"][0]["name"], "main_v2.py")
        self.assertEqual(action, "code_ready_for_tests") # From DeveloperNode

class TestPackagingFlow(unittest.TestCase):
    def test_packaging_flow_success(self):
        # PackageNode does not use LLM, so no mock needed here
        shared_state = {
            "generated_project_structure": {"files":[{"name":"final_app.py", "content":"print('done')"}], "entry_point_file":"final_app.py"},
            "planned_task_description": {"component_name": "final_app", "target_file":"final_app.py"}
        }
        action = packaging_flow.run(shared_state)
        self.assertEqual(action, "done")
        self.assertIn("packaged_artifacts_info", shared_state)
        self.assertIn("project_files", shared_state["packaged_artifacts_info"])
        self.assertEqual(shared_state["packaged_artifacts_info"]["project_files"][0]["name"], "final_app.py")

if __name__ == '__main__':
    unittest.main()