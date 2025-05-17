# flow.py
import logging
from pocketflow import Flow
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
)

logger = logging.getLogger(__name__)

# Flow 1: Requirement Elicitation and Planning
initial_request_node = InitialRequestNode()
architect_planner_node = ArchitectPlannerNode()
initial_request_node >> architect_planner_node
# ArchitectPlannerNode returns "clarification_needed" or "plan_ready_for_code" or "error_encountered"
# The UI (app.py) will handle the loop for clarification or error.
elicitation_flow = Flow(start=initial_request_node)
logger.info("Elicitation Flow (InitialRequest >> ArchitectPlanner) created.")

# Flow 2: Test Case Design (runs after successful planning)
test_case_designer_node = TestCaseDesignerNode()
# TestCaseDesignerNode returns "tests_ready" or "error_encountered"
test_design_flow = Flow(start=test_case_designer_node)
logger.info("Test Design Flow (TestCaseDesigner) created.")

# Flow 3: Initial Code Generation (runs after test design)
# This flow assumes 'planned_task_description' and 'planner_notes' are in shared state.
# It uses the DeveloperNode for the first code generation attempt.
initial_developer_node = DeveloperNode() # Separate instance for clarity if needed, or reuse
# DeveloperNode returns "code_ready_for_tests" or "code_generation_failed"
initial_code_gen_flow = Flow(start=initial_developer_node)
logger.info("Initial Code Generation Flow (DeveloperNode) created.")

# Flow 4: QA and Validation (runs after code generation/refinement)
# This flow will execute all tests and then validate.
qa_node = QANode()
validation_node = ValidationNode()
qa_node - "run_next_test" >> qa_node  # Loop for multiple tests
qa_node - "testing_error_or_done" >> validation_node # Proceed after all tests or if one test errors/fails
# ValidationNode returns "validation_done" or "error_encountered"
# The UI will check shared_state.all_tests_passed and shared_state.validation_status
qa_validation_flow = Flow(start=qa_node)
logger.info("QA & Validation Flow (QANode >> ValidationNode) created.")

# Flow 5: Critique and Refinement (runs if QA/Validation fails or user rejects)
critique_node = CritiqueNode()
refining_developer_node = DeveloperNode() # Could be the same DeveloperNode instance if stateless enough
critique_node - "refine_code" >> refining_developer_node
# DeveloperNode (in refine mode) returns "code_ready_for_tests" or "code_generation_failed"
# If "code_ready_for_tests", UI loops back to QA_VALIDATION_FLOW.
# If "code_generation_failed", UI might go to HUMAN_REVIEW or MAX_REFINEMENTS_FAILED.
critique_refine_flow = Flow(start=critique_node)
logger.info("Critique & Refine Flow (CritiqueNode >> DeveloperNode) created.")

# Flow 6: Packaging (runs after user approves)
package_node = PackageNode()
# PackageNode returns "done" or "error_encountered"
packaging_flow = Flow(start=package_node)
logger.info("Packaging Flow (PackageNode) created.")
