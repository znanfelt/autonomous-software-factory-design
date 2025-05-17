# flow.py
import logging
from pocketflow import Flow
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
)

logger = logging.getLogger(__name__)

# Flow 1: Requirement Elicitation and Planning
# User Input -> Architect/Planner -> (Clarification Loop OR Plan Ready)
initial_request_node = InitialRequestNode()
architect_planner_node = ArchitectPlannerNode()

initial_request_node >> architect_planner_node
# ArchitectPlannerNode returns:
# - "clarification_needed" (UI loops back to ArchitectPlannerNode with more user input)
# - "plan_ready_for_code" (UI proceeds to Test Design)
# - "error_encountered" (UI handles error)
elicitation_flow = Flow(start=initial_request_node)
logger.info("Elicitation Flow (InitialRequest >> ArchitectPlanner) created.")


# Flow 2: Test Case Design (runs after successful planning OR after code refinement for re-design)
# Input: planned_task_description, (optionally: critique_feedback, current_project_structure for re-design)
# Output: generated_test_cases
test_case_designer_node = TestCaseDesignerNode()
# TestCaseDesignerNode returns "tests_ready" or "error_encountered"
test_design_flow = Flow(start=test_case_designer_node)
logger.info("Test Design Flow (TestCaseDesignerNode) created.")


# Flow 3: Code Generation / Refinement (runs for initial code OR for refinements)
# Input: planned_task_description, (optionally: critique_feedback, feedback_history)
# Output: generated_project_structure
developer_node = DeveloperNode() # Single instance is fine, its behavior adapts to inputs
# DeveloperNode returns "code_ready_for_tests" or "code_generation_failed"
code_generation_flow = Flow(start=developer_node)
logger.info("Code Generation/Refinement Flow (DeveloperNode) created.")


# Flow 4: QA and Validation (runs after code generation/refinement)
# Input: generated_project_structure, generated_test_cases
# Output: test_results_summary, all_tests_passed, validation_status, validation_issues
qa_node = QANode()
validation_node = ValidationNode()

qa_node - "run_next_test" >> qa_node  # Loop for multiple tests
qa_node - "testing_error_or_done" >> validation_node # Proceed after all tests or if one test errors/fails
# ValidationNode.post() returns "validation_done" or "error_encountered" by default if no explicit return.
# UI will check shared_state.all_tests_passed and shared_state.validation_status
qa_validation_flow = Flow(start=qa_node)
logger.info("QA & Validation Flow (QANode >> ValidationNode) created.")


# Flow 5: Critique Generation (runs if QA/Validation fails or user rejects)
# Input: planned_task_description, generated_project_structure, test_failure_message, validation_issues, user_rejection_reason
# Output: critique_feedback
critique_node = CritiqueNode()
# CritiqueNode returns "refine_code" (signaling app.py to start refinement) or "error_encountered"
critique_generation_flow = Flow(start=critique_node)
logger.info("Critique Generation Flow (CritiqueNode) created.")


# Flow 5: Critique & Refine (runs after QA/Validation fails or user rejects)
# Input: planned_task_description, generated_project_structure, test_failure_message, validation_issues, user_rejection_reason
# Output: critique_feedback, then refined generated_project_structure
refinement_developer_node = DeveloperNode()
critique_node - "refine_code" >> refinement_developer_node
refinement_flow = Flow(start=critique_node)
logger.info("Refinement Flow (CritiqueNode >> DeveloperNode) created.")


# Flow 6: Packaging (runs after user approves)
# Input: final generated_project_structure, planned_task_description
# Output: packaged_artifacts_info, handoff_summary
package_node = PackageNode()
# PackageNode returns "done" or "error_encountered"
packaging_flow = Flow(start=package_node)
logger.info("Packaging Flow (PackageNode) created.")
