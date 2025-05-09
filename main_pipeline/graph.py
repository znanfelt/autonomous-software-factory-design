from .agents import (
    architect_agent_node, planner_agent_node, developer_agent_node, qa_agent_node,
    validation_agent_node, critique_agent_node, test_case_designer_node
)
from .state import GraphState
from langgraph.graph import StateGraph, END
import logging

# Graph assembly, routers, and build_graph

def decide_after_architect(state):
    if state.get("current_error") and "Architect Error" in state.get("current_error", ""):
        return END
    if state.get("architectural_decision") and state["architectural_decision"].get("chosen_language"):
        return "planner_agent_node"
    else:
        return END

def decide_after_planner(state):
    if state.get("current_error") and "Planner Error" in state.get("current_error", ""):
        return END
    questions = state.get("clarification_questions_for_user")
    planner_iters = state.get("planner_iteration_count", 0)
    max_planner_iters = state.get("max_planner_iterations", 2)
    if questions and planner_iters < max_planner_iters:
        return "human_interaction_node"
    elif questions and planner_iters >= max_planner_iters:
        return END
    elif state.get("planned_task_description"):
        return "test_case_designer_node"
    else:
        return END

def decide_after_test_case_designer(state):
    if state.get("current_error") and "Test Case Designer" in state.get("current_error", ""):
        return END
    if state.get("generated_test_cases") and len(state["generated_test_cases"]) > 0:
        return "developer_agent_node"
    else:
        return END

def decide_after_qa(state):
    test_status = state["current_test_status"]
    ref_count = state["refinement_count"]
    max_ref = state["max_refinements"]
    if state.get("current_error") and ("Architect Error" in state.get("current_error","") or "Planner Error" in state.get("current_error","") ):
        return END
    if test_status == "success":
        return "validation_agent_node"
    if test_status == "tool_error":
        if state.get("current_error") and ("Developer agent" in state.get("current_error","") or "No parsable code" in state.get("current_error","") ):
            return "developer_agent_node" if ref_count < max_ref else END
        return "critique_agent_node" if ref_count < max_ref else END
    return "critique_agent_node" if ref_count < max_ref else END

def decide_after_validation(state):
    validation_status = state["validation_status"]
    ref_count = state["refinement_count"]
    max_ref = state["max_refinements"]
    if validation_status == "pass":
        return "artifact_packaging_node"
    elif validation_status == "error":
        return END
    else:
        return "critique_agent_node" if ref_count < max_ref else END

def decide_after_packaging(state):
    if state.get("current_error") and "Packaging Error" in state.get("current_error", ""):
        return END
    elif state.get("packaged_artifacts_info"):
        return "handoff_node"
    else:
        return END

# Define the artifact_packaging_node function
def artifact_packaging_node(state: GraphState) -> GraphState:
    logger = logging.getLogger(__name__)
    logger.info("Entering Artifact Packaging Node")
    # Example logic for packaging artifacts (replace with actual implementation)
    packaged_artifacts_info = {"code_file": "output.py", "documentation": "README.md"}
    logger.info(f"Packaged artifacts: {packaged_artifacts_info}")
    return {**state, "packaged_artifacts_info": packaged_artifacts_info, "current_error": None}

# Define the handoff_node function
def handoff_node(state: GraphState) -> GraphState:
    logger = logging.getLogger(__name__)
    logger.info("Entering Handoff Node")
    # Example logic for handoff (replace with actual implementation)
    handoff_summary = "Artifacts successfully handed off to the next stage."
    logger.info(f"Handoff summary: {handoff_summary}")
    return {**state, "handoff_summary": handoff_summary, "current_error": None}

def build_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("architect_agent_node", architect_agent_node)
    workflow.add_node("planner_agent_node", planner_agent_node)
    workflow.add_node("human_interaction_node", lambda state: state)  # Placeholder for HITL node
    workflow.add_node("test_case_designer_node", test_case_designer_node)
    workflow.add_node("developer_agent_node", developer_agent_node)
    workflow.add_node("qa_agent_node", qa_agent_node)
    workflow.add_node("validation_agent_node", validation_agent_node)
    workflow.add_node("critique_agent_node", critique_agent_node)
    workflow.add_node("artifact_packaging_node", artifact_packaging_node)
    workflow.add_node("handoff_node", handoff_node)
    # Add artifact packaging and handoff nodes as needed
    workflow.set_entry_point("architect_agent_node")
    workflow.add_conditional_edges("architect_agent_node", decide_after_architect, 
                                   {"planner_agent_node": "planner_agent_node", END: END})
    workflow.add_conditional_edges("planner_agent_node", decide_after_planner, 
                                   {"human_interaction_node": "human_interaction_node", "test_case_designer_node": "test_case_designer_node", END: END})
    workflow.add_edge("human_interaction_node", "planner_agent_node")
    workflow.add_conditional_edges("test_case_designer_node", decide_after_test_case_designer,
                                   {"developer_agent_node": "developer_agent_node", END: END})
    workflow.add_edge("developer_agent_node", "qa_agent_node")
    workflow.add_conditional_edges("qa_agent_node", decide_after_qa, 
                                   {"validation_agent_node": "validation_agent_node", "critique_agent_node": "critique_agent_node", 
                                    "developer_agent_node": "developer_agent_node", END: END})
    workflow.add_conditional_edges("validation_agent_node", decide_after_validation, 
                                   {"artifact_packaging_node": "artifact_packaging_node", "critique_agent_node": "critique_agent_node", END: END})
    workflow.add_conditional_edges("artifact_packaging_node", decide_after_packaging, 
                                   {"handoff_node": "handoff_node", END: END})
    workflow.add_edge("critique_agent_node", "developer_agent_node")
    workflow.add_edge("handoff_node", END)
    app = workflow.compile()
    return app