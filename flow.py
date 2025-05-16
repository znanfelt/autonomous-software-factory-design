# flow.py
import logging
from pocketflow import Flow
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
)

logger = logging.getLogger(__name__)

def create_elicitation_flow() -> Flow:
    logger.info("Creating Elicitation Flow (InitialRequest >> ArchitectPlanner)...")
    initial_request_node = InitialRequestNode()
    architect_planner_node = ArchitectPlannerNode()
    initial_request_node >> architect_planner_node
    return Flow(start=initial_request_node)

def create_test_design_flow() -> Flow:
    logger.info("Creating Test Design Flow (TestCaseDesigner)...")
    test_case_designer_node = TestCaseDesignerNode()
    return Flow(start=test_case_designer_node)

def create_initial_code_gen_flow() -> Flow:
    # Assumes plan is in shared state.
    logger.info("Creating Initial Code Generation Flow (DeveloperNode)...")
    developer_node = DeveloperNode() # Ensure it uses planned_task_description
    return Flow(start=developer_node)

def create_qa_and_validation_flow() -> Flow:
    # This flow assumes code and test cases are in shared state.
    # It will run all tests, then validate.
    logger.info("Creating QA & Validation Flow (QANode >> ValidationNode)...")
    qa_node = QANode()
    validation_node = ValidationNode()
    
    qa_node - "run_next_test" >> qa_node  # Loop for multiple tests
    qa_node - "testing_error_or_done" >> validation_node # Proceed after all tests or error
    
    # If validation itself errors, it will just end. UI will pick up error from shared state.
    # ValidationNode.post() returns None by default (or specific if needed)
    return Flow(start=qa_node)

def create_critique_and_refine_flow() -> Flow:
    # This flow takes current code, test/validation failures, user feedback
    # generates critique, then new code.
    logger.info("Creating Critique & Refine Flow (CritiqueNode >> DeveloperNode)...")
    critique_node = CritiqueNode()
    developer_node = DeveloperNode() # DeveloperNode should handle critique_feedback
    
    critique_node - "refine_code" >> developer_node
    # DeveloperNode returns "code_ready_for_tests" or "code_generation_failed"
    return Flow(start=critique_node)

def create_packaging_flow() -> Flow:
    logger.info("Creating Packaging Flow (PackageNode)...")
    package_node = PackageNode()
    return Flow(start=package_node)

# Instantiate flows for app.py to use
elicitation_flow = create_elicitation_flow()
test_design_flow = create_test_design_flow()
initial_code_gen_flow = create_initial_code_gen_flow() # For first code attempt
qa_validation_flow = create_qa_and_validation_flow()
critique_refine_flow = create_critique_and_refine_flow() # For refinement cycles
packaging_flow = create_packaging_flow()