# flow.py
import logging
from pocketflow import Flow
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode,
    SecurityComplianceNode # Import the new node
)

logger = logging.getLogger(__name__)

# Flow 1: Requirement Elicitation and Planning
initial_request_node = InitialRequestNode()
architect_planner_node = ArchitectPlannerNode()
initial_request_node >> architect_planner_node
elicitation_flow = Flow(start=initial_request_node)
logger.info("Elicitation Flow (InitialRequest >> ArchitectPlanner) created.")

# Flow 2: Test Case Design
test_case_designer_node = TestCaseDesignerNode()
test_design_flow = Flow(start=test_case_designer_node)
logger.info("Test Design Flow (TestCaseDesignerNode) created.")

# Flow 3: Code Generation / Refinement
developer_node = DeveloperNode() 
code_generation_flow = Flow(start=developer_node)
logger.info("Code Generation/Refinement Flow (DeveloperNode) created.")

# Flow 4: QA, Validation, and Security Compliance
qa_node = QANode()
validation_node = ValidationNode()
security_compliance_node = SecurityComplianceNode() # Instantiate the new node

qa_node - "run_next_test" >> qa_node
qa_node - "testing_error_or_done" >> validation_node 
validation_node - "validation_done" >> security_compliance_node # After validation, do security check
validation_node - "error_encountered" >> security_compliance_node # Even if validation has an error, try security check

# SecurityComplianceNode.post() returns "security_check_done" or "error_encountered"
# The UI (app.py) will then check all statuses (tests, validation, security) 
# from shared_state before proceeding to HUMAN_REVIEW or CRITIQUE_CODE.
qa_validation_security_flow = Flow(start=qa_node) # Renamed flow for clarity
logger.info("QA, Validation & Security Flow created.")


# Flow 5: Critique Generation
critique_node = CritiqueNode()
critique_generation_flow = Flow(start=critique_node)
logger.info("Critique Generation Flow (CritiqueNode) created.")


# Flow 6: Packaging
package_node = PackageNode()
packaging_flow = Flow(start=package_node)
logger.info("Packaging Flow (PackageNode) created.")
