import logging
from pocketflow import Flow
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
)

logger = logging.getLogger(__name__)

def create_sdlc_flow() -> Flow:
    logger.info("Creating SDLC Flow definition...")
    # Instantiate nodes
    initial_request_node = InitialRequestNode()
    architect_planner_node = ArchitectPlannerNode()
    developer_node = DeveloperNode()
    test_case_designer_node = TestCaseDesignerNode()
    qa_node = QANode()
    validation_node = ValidationNode()
    critique_node = CritiqueNode()
    package_node = PackageNode()
    # Placeholder for a human interaction node (not a PocketFlow node, managed by UI)
    # human_clarification_node = "HUMAN_CLARIFICATION_STAGE_MARKER" 

    # Define the main flow sequence and branches
    initial_request_node >> architect_planner_node

    architect_planner_node - "clarification_needed" >> None # UI will handle this, then re-trigger architect_planner_node
    architect_planner_node - "plan_ready_for_code" >> test_case_designer_node
    architect_planner_node - "error_encountered" >> None # End flow on critical planner error

    test_case_designer_node >> developer_node # Default transition if tests are designed
    test_case_designer_node - "error_encountered" >> None # End flow if test design fails critically

    developer_node - "code_ready_for_tests" >> qa_node
    developer_node - "code_generation_failed" >> critique_node # If dev can't even produce code

    # QA loop for multiple test cases
    qa_node - "run_next_test" >> qa_node # Loop to run all test cases
    qa_node - "testing_error_or_done" >> validation_node # After all tests or if one fails/errors
    
    validation_node - "validation_done" >> critique_node # Always critique after validation unless approved by human
    validation_node - "error_encountered" >> critique_node # If validation itself errors, critique might help

    critique_node - "refine_code" >> developer_node # Loop back to developer for refinement

    # Final packaging after potential human approval (handled by UI state change)
    # For PocketFlow, we assume critique_node directly leads to dev.
    # The UI logic will break this loop if max_refinements is hit or user approves.
    # If we had a "final_approval" action from a HITL node:
    # validation_node - "approved_by_human" >> package_node (This path is managed by Streamlit logic)

    # For now, let's assume the flow ends if critique leads to too many refinements (handled by UI)
    # or if an error path leads to None. `PackageNode` would be triggered by UI after human approval.

    # The flow starting point for the initial request processing.
    # Subsequent stages (like triggering PackageNode) will be handled by Streamlit app.py
    # by running different "sub-flows" or re-running parts of a larger conceptual flow.
    
    # For this simulation, we'll make a linear path to packaging if all goes well.
    # In Streamlit, human review would interrupt this.
    # Simplified "happy path" for pure PocketFlow run:
    validation_node - "validation_done_and_passed" >> package_node # Add this hypothetical path
    
    # For a fully contained PocketFlow, you'd need a node representing human review.
    # Since Streamlit handles that, PocketFlow parts are more like sub-routines.
    # Let's define a main elicitation flow for now.
    
    main_elicitation_and_dev_flow = Flow(start=initial_request_node)
    logger.info("SDLC Flow definition created.")
    return main_elicitation_and_dev_flow


# Separate flow for testing and review cycle
def create_test_review_refine_flow() -> Flow:
    logger.info("Creating Test-Review-Refine Flow definition...")
    # Nodes are already instantiated globally for simplicity in this example
    # In a larger app, you might pass them or re-instantiate.
    developer_node = DeveloperNode()
    test_case_designer_node = TestCaseDesignerNode()
    qa_node = QANode()
    validation_node = ValidationNode()
    critique_node = CritiqueNode()

    # This flow assumes plan and initial code OR critique exist
    # It starts from developer (if refining) or test_case_designer (if first code for plan)
    
    # Path for new code: Design Tests -> Develop -> QA -> Validate -> Critique (if needed)
    test_case_designer_node >> developer_node
    developer_node - "code_ready_for_tests" >> qa_node
    developer_node - "code_generation_failed" >> critique_node
    
    qa_node - "run_next_test" >> qa_node
    qa_node - "testing_error_or_done" >> validation_node # If tests pass or one fails/errors
    
    validation_node - "validation_done" >> critique_node # Always go to critique after automated checks. UI handles approval.
    validation_node - "error_encountered" >> critique_node

    critique_node - "refine_code" >> developer_node # Loop back for refinement

    # This flow is typically started at test_case_designer_node or developer_node via Streamlit
    # For testing, can define a start point.
    # This is more a "segment" of the overall process managed by UI.
    # Let's make a runnable flow starting from test_case_designer for this segment:
    test_refine_flow = Flow(start=test_case_designer_node)
    logger.info("Test-Review-Refine Flow definition created.")
    return test_refine_flow


def create_packaging_flow() -> Flow:
    logger.info("Creating Packaging Flow definition...")
    package_node = PackageNode()
    packaging_flow = Flow(start=package_node)
    logger.info("Packaging Flow definition created.")
    return packaging_flow
