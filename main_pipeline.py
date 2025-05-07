import re
import traceback
import os
import json
import time
import shutil
from pathlib import Path
from typing import TypedDict, Optional, List, Any, Tuple, Literal, Dict
import logging

# LangChain Imports
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain.agents import AgentExecutor, create_openai_tools_agent, AgentAction

# LangGraph Imports
from langgraph.graph import StateGraph, END

# LlamaIndex Imports (with graceful fallback)
try:
    from llama_index.core import VectorStoreIndex, Document, Settings
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.llms.openai import OpenAI as LlamaOpenAI # Renamed to avoid conflict
    llama_index_available = True
except ImportError:
    llama_index_available = False
    class Document: def __init__(self, text="", metadata=None): self.text = text; self.metadata = metadata or {}
    class VectorStoreIndex: @staticmethod
    def from_documents(*args, **kwargs): return MockQueryEngineWrapper()
    class MockQueryEngine: def query(self, *args, **kwargs): return MockQueryResponse()
    class MockQueryResponse:
        def __init__(self, response_text="No RAG context (LlamaIndex not installed)."): self.response = response_text
        def __str__(self): return self.response
    class MockQueryEngineWrapper: def as_query_engine(self, *args, **kwargs): return MockQueryEngine()
    Settings = None # Will be checked before use

# --- -1. Logging Configuration ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), 
                    format='%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
logger = logging.getLogger(__name__)


# --- 0. Knowledge Base Content & RAG Setup (Add Data Contract Standards) ---
CODING_STANDARDS_TEXT = """
Python Coding Standards:
1. Type hints for all parameters and return values are mandatory.
2. Function names: snake_case.
3. Docstrings: Brief explanation, args, return (unless trivial).
"""
PLANNING_GUIDELINES_TEXT = """
Project Planning Guidelines:
1. Decompose requests into single, manageable Python functions.
2. Specify inputs, outputs, and their types for each function.
3. Note constraints or edge cases.
"""
DEBUGGING_TIPS_TEXT = """
Python Debugging Tips:
1. TypeErrors: Check data types against hints.
2. SyntaxErrors: Review line for typos, colons, indentation.
3. NameErrors: Ensure variables defined before use.
4. Test Fails: Analyze expected vs. actual output.
"""
VALIDATION_RULES_TEXT = """
Code Validation Rules (Python):
1. Security: Avoid `eval()` with untrusted input; no hardcoded credentials.
2. Compliance: Adhere to coding standards (type hints, docstrings, naming).
3. Quality: Code must be readable; implement core logic requested.
"""
ARCHITECTURAL_PRINCIPLES_TEXT = """
Architectural Principles:
1. Language: Python for single-function MVPs.
2. Frameworks: Prefer standard Python libraries for simple tasks.
3. Simplicity and Testability: Prioritize these.
4. Output: JSON with 'chosen_language', 'framework_hint', 'high_level_notes'.
"""
DATA_CONTRACT_STANDARDS_TEXT = """
Data Contract Standards:
1. Applicability: Define JSON Schemas for functions that process or return structured data (e.g., dicts). Not strictly needed for simple scalar inputs/outputs unless structure is implied.
2. Content: Schemas should define `type` (e.g., object, string, number, array, boolean), `properties` for objects, and `description` for fields.
3. Output: Agent should produce a JSON string representing the schema or state 'not_applicable'.
4. Goal: Ensure data interfaces are clearly defined. For simple functions like adding two numbers, a contract might be 'not_applicable' or a very simple schema for the numbers.
"""

# RAG Engine Globals
rag_engines: Dict[str, Any] = {
    "developer": None, "planner": None, "critique": None, 
    "validation": None, "architect": None, "datacontract": None # New
}
rag_contexts_map = {
    "developer": CODING_STANDARDS_TEXT, "planner": PLANNING_GUIDELINES_TEXT,
    "critique": DEBUGGING_TIPS_TEXT, "validation": VALIDATION_RULES_TEXT,
    "architect": ARCHITECTURAL_PRINCIPLES_TEXT, "datacontract": DATA_CONTRACT_STANDARDS_TEXT # New
}

def initialize_rag_engines():
    if not llama_index_available or not os.getenv("OPENAI_API_KEY"):
        for key in rag_engines.keys():
            rag_engines[key] = MockQueryEngineWrapper().as_query_engine()
        logger.warning("RAG: Disabled (LlamaIndex/API key missing). Using mock query engines.")
        return
    logger.info("RAG: Initializing LlamaIndex query engines...")
    try:
        for key, text_content in rag_contexts_map.items():
            docs = [Document(text=text_content, metadata={"source": f"{key}_rules.txt"})]
            index = VectorStoreIndex.from_documents(docs)
            rag_engines[key] = index.as_query_engine(similarity_top_k=1) # Get top 1 relevant chunk
        logger.info("RAG: All RAG engines initialized successfully.")
    except Exception as e:
        logger.error(f"RAG: Error initializing LlamaIndex: {e}. Using mock engines.", exc_info=True)
        for key in rag_engines.keys():
            rag_engines[key] = MockQueryEngineWrapper().as_query_engine()

def get_rag_context(engine_key: str, query_text: str) -> str:
    default_message = f"No RAG context available for {engine_key}."
    if rag_engines.get(engine_key):
        try:
            response = rag_engines[engine_key].query(query_text)
            return str(response)
        except Exception as e:
            logger.warning(f"RAG query error ({engine_key}): {e}")
            return f"RAG error querying {engine_key}: {e}"
    return default_message


# --- 1. Define the State for the Graph (Add Data Contract fields) ---
class TestCase(TypedDict):
    function_name: str; inputs: Tuple[Any, ...]; expected_output: Any
class GraphState(TypedDict):
    initial_user_request: str; architectural_decision: Optional[Dict[str, Any]]
    clarified_user_input: Optional[str]; clarification_questions_for_user: Optional[List[str]]
    planner_iteration_count: int; max_planner_iterations: int; llm_models_config: Dict[str, str]
    planned_task_description: Optional[str]; planner_notes: Optional[str]; task_description: str
    current_test_case: TestCase; generated_code: Optional[str]
    test_status: Optional[Literal['success', 'compilation_error', 'runtime_error', 'test_fail', 'tool_error']]
    test_message: Optional[str]; critique: Optional[str]
    
    data_contract: Optional[str]                         # New: JSON string of the contract
    data_contract_status: Optional[Literal['defined', 'not_applicable', 'error']] # New
    data_contract_issues: Optional[List[str]]            # New

    validation_status: Optional[Literal['pass', 'fail', 'error']]; validation_issues: Optional[List[str]]
    packaged_artifacts_info: Optional[Dict[str, str]]; handoff_summary: Optional[str]
    feedback_history: List[str]; refinement_count: int; max_refinements: int
    current_error: Optional[str]; qa_agent_messages: List


# --- 2. Define Tools (Unchanged) ---
@tool
def code_tester_tool(code_string: str, function_name: str, test_inputs: tuple, expected_output: any) -> dict:
    # ... (tool code unchanged)
    if not code_string: return {"status": "compilation_error", "message": "No code provided."}
    try:
        scope = {'__builtins__': __builtins__}; exec(code_string, scope, scope)
        if function_name not in scope: return {"status": "compilation_error", "message": f"Function '{function_name}' not defined."}
        actual = scope[function_name](*test_inputs)
        if actual == expected_output: return {"status": "success", "message": "Test passed.", "actual_output": actual}
        return {"status": "test_fail", "message": f"Input: {test_inputs}, Expected: {expected_output}, Got: {actual}", "actual_output": actual}
    except Exception as e: logger.error(f"Code tester tool runtime error: {e}", exc_info=False); return {"status": "runtime_error", "message": str(e)}

# --- 3. Helper function to extract Python code (Unchanged) ---
def extract_python_code(llm_output: str) -> Optional[str]: # ... (unchanged)
    match = re.search(r"```python\n(.*?)\n```", llm_output, re.DOTALL)
    if match: return match.group(1).strip()
    match = re.search(r"```\n(.*?)\n```", llm_output, re.DOTALL)
    if match: return match.group(1).strip()
    return None

# --- 4. Define LLMs & Prompts (Add Data Contract LLM & Prompt) ---
def get_llm_instance(model_name_key: str, state: GraphState, default_model="gpt-3.5-turbo-0125", temperature=0.2, mock_response="") -> ChatOpenAI:
    # ... (unchanged)
    model_name = state["llm_models_config"].get(model_name_key, default_model)
    logger.debug(f"Initializing LLM for '{model_name_key}' with model '{model_name}'.")
    try: return ChatOpenAI(model=model_name, temperature=temperature)
    except Exception as e:
        logger.error(f"LLM init error for {model_name_key} ({model_name}): {e}. Using mock.", exc_info=True)
        class MockLLM: def invoke(self, *args, **kwargs): logger.warning(f"MockLLM invoked for {model_name_key}"); return mock_response
        return MockLLM() # type: ignore

class SimpleJsonOutputParser(StrOutputParser): # ... (unchanged)
    def parse(self, text:str):
        try: match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL); text = match.group(1) if match else text; return json.loads(text)
        except Exception as e: logger.error(f"JSON Parser Error: {e} in text: {text[:200]}..."); return {"error": "JSON parsing failed", "raw_text": text}

# Architect, Planner, Developer, Validation, Critique, QA LLM Prompts (Unchanged)
# ... (all prompts as before)
architect_prompt_template = ChatPromptTemplate.from_messages([("system", "..."), ("human", "...")]) # Placeholder
planner_prompt_template = ChatPromptTemplate.from_messages([("system", "..."), ("human", "...")]) # Placeholder
dev_code_gen_prompt_template = ChatPromptTemplate.from_messages([("system", "..."), ("human", "...")]) # Placeholder
validation_prompt_template = ChatPromptTemplate.from_messages([("system", "..."), ("human", "...")]) # Placeholder
critique_prompt_template = ChatPromptTemplate.from_messages([("system", "..."), ("human", "...")]) # Placeholder
qa_tools = [code_tester_tool]; qa_agent_prompt = ChatPromptTemplate.from_messages([("system", "..."), ("human", "...")]) # Placeholder

# Data Contract Agent LLM & Prompt
datacontract_prompt_template = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Data Contract Definition agent. Your task is to analyze a Python function's signature, docstring, and the overall task description "
     "to define a JSON Schema for its primary inputs and/or outputs, if applicable. Consult Data Contract Standards.\n"
     "--- BEGIN DATA CONTRACT STANDARDS ---\n{datacontract_standards_context}\n--- END DATA CONTRACT STANDARDS ---\n"
     "If a contract is applicable (e.g., function takes/returns dicts, complex objects), generate a JSON string representing the schema. "
     "If not applicable (e.g., simple scalar math, string manipulation with no defined structure), state 'not_applicable'. "
     "If you encounter issues or cannot determine a contract, state 'error' and provide reasons. "
     "Output a JSON object with keys: 'status' (Literal['defined', 'not_applicable', 'error']), "
     "'contract_schema' (JSON string of the schema if status is 'defined', else null), "
     "and 'issues' (list of strings describing problems if status is 'error', else empty list)."),
    ("human",
     "Task Description: {task_description}\n"
     "Planner Notes: {planner_notes}\n"
     "Function Signature (if available from code): (Inspect generated_code for this)\n"
     "Generated Code (for context, especially docstrings and type hints):\n```python\n{generated_code}\n```\n\n"
     "Please define the data contract.")
])


# --- 5. Define Graph Nodes (Add DataContractAgentNode, update Critique) ---
ARTIFACTS_BASE_DIR = Path("output_artifacts_demo")
# Architect, Planner, HumanInteraction, Developer, QA, Validation, Packaging, Handoff nodes are largely the same.
# Only DataContractAgentNode is new, and CritiqueAgentNode is updated to consider its output.
# Ensure all nodes clear/reset fields for subsequent nodes as needed.
def architect_agent_node(state: GraphState) -> GraphState: # ... (as before, ensure it clears DataContract fields)
    # ...
    return {**state, "architectural_decision": ..., "current_error": None, # Reset relevant fields
            "planned_task_description": None, "planner_notes": None, "task_description": "",
            "clarified_user_input": None, "clarification_questions_for_user": None, "planner_iteration_count": 0,
            "generated_code": None, "test_status": None, "critique": None, "validation_status": None,
            "data_contract_status": None, "data_contract": None, "data_contract_issues": [], # Clear new fields
            "packaged_artifacts_info": None, "handoff_summary": None, "feedback_history": [], "refinement_count": 0}
def planner_agent_node(state: GraphState) -> GraphState: # ... (as before, ensure it clears DataContract fields)
    # ...
    return {**state, "planned_task_description": ..., "task_description": ..., "planner_notes": ...,
            "clarification_questions_for_user": ..., "clarified_user_input": None, "planner_iteration_count": ...,
            "current_error": None, "critique": None, "validation_status": None, "data_contract_status": None, # Clear new fields
            "packaged_artifacts_info": None, "handoff_summary": None, "generated_code": None, "test_status": None,
            "feedback_history": [] if state["planner_iteration_count"] == 1 else state.get("feedback_history",[]),
            "refinement_count": 0 if state["planner_iteration_count"] == 1 else state.get("refinement_count",0)}
def developer_agent_node(state: GraphState) -> GraphState: # ... (as before, ensure it clears DataContract fields)
    # ...
    return {**state, "generated_code": ..., "refinement_count": ..., "current_error": None,
            "critique": None, "validation_status": None, "data_contract_status": None, # Clear new fields
            "packaged_artifacts_info": None, "handoff_summary": None}
def qa_agent_node(state: GraphState) -> GraphState: # ... (as before, ensure it clears DataContract fields)
    # ...
    return {**state, "test_status": ..., "test_message": ..., "current_error": None, "qa_agent_messages": [],
            "validation_status": None, "validation_issues": [], "data_contract_status": None, # Clear new fields
            "packaged_artifacts_info": None, "handoff_summary": None}

def data_contract_agent_node(state: GraphState) -> GraphState:
    logger.info("Entering Data Contract Agent Node")
    task_desc = state["task_description"]
    planner_notes_str = state["planner_notes"]
    generated_code_str = state["generated_code"]

    if not generated_code_str:
        logger.error("DataContract: No generated code available.")
        return {**state, "data_contract_status": "error", "data_contract_issues": ["No generated code to define contract from."], "current_error": "DataContract: No code."}

    logger.debug(f"DataContract agent analyzing code for task: {task_desc[:100]}...")
    
    datacontract_standards_context = get_rag_context("datacontract", f"Data contract standards for task: {task_desc}")
    
    llm_datacontract = get_llm_instance("datacontract_llm", state, temperature=0.1, 
                                        mock_response='{"status": "not_applicable", "contract_schema": null, "issues": []}')
    datacontract_chain_instance = datacontract_prompt_template | llm_datacontract | SimpleJsonOutputParser()
    
    contract_output_json = datacontract_chain_instance.invoke({
        "task_description": task_desc,
        "planner_notes": planner_notes_str or "None",
        "generated_code": generated_code_str,
        "datacontract_standards_context": datacontract_standards_context
    })
    logger.debug(f"DataContract LLM Raw Output (parsed): {contract_output_json}")

    status: Literal['defined', 'not_applicable', 'error'] = "error"
    contract_schema: Optional[str] = None
    issues: List[str] = ["Data contract agent output format error or missing status."]

    if isinstance(contract_output_json, dict):
        status_from_llm = contract_output_json.get("status")
        if status_from_llm in ["defined", "not_applicable", "error"]:
            status = status_from_llm
        contract_schema_from_llm = contract_output_json.get("contract_schema")
        if status == "defined" and isinstance(contract_schema_from_llm, str):
            # Validate if it's valid JSON string
            try:
                json.loads(contract_schema_from_llm) # Test parsing
                contract_schema = contract_schema_from_llm
            except json.JSONDecodeError as e:
                logger.warning(f"Generated contract_schema is not valid JSON: {e}")
                status = "error" # Downgrade status if schema is malformed
                issues = [f"Generated contract schema is not valid JSON: {e}"]
        elif status == "defined" and not contract_schema_from_llm:
             status = "error"
             issues = ["Contract status 'defined' but no schema provided."]
        
        issues_from_llm = contract_output_json.get("issues", [])
        if isinstance(issues_from_llm, list) and status != "error": # only use LLM issues if we didn't already set error status
            issues = issues_from_llm
        elif status == "error" and not issues: # If error status but no specific issues from LLM
            issues = ["Data contract definition failed for unspecified reasons."]


    logger.info(f"Data Contract Status: {status}, Schema defined: {bool(contract_schema)}, Issues: {issues}. Exiting Data Contract Node.")
    return {**state, "data_contract_status": status, "data_contract": contract_schema, 
            "data_contract_issues": issues, "current_error": None if status != "error" else (issues[0] if issues else "Unknown data contract error")}

def validation_agent_node(state: GraphState) -> GraphState: # ... (as before)
    # ...
    return {**state, "validation_status": ..., "validation_issues": ..., "current_error": None}
def critique_agent_node(state: GraphState) -> GraphState: # Updated to include data contract issues
    logger.info("Entering Critique Node")
    code_in_question = state["generated_code"]
    task_desc = state["task_description"]
    planner_notes_str = state["planner_notes"]
    test_failure_msg = state.get("test_message", "N/A")
    val_issues = state.get("validation_issues", [])
    dc_status = state.get("data_contract_status")
    dc_issues = state.get("data_contract_issues", [])

    reason_for_critique = ""
    if state.get("test_status") not in ["success", "tool_error", None]:
        reason_for_critique += f"Functional test failed: {test_failure_msg}. "
    if val_issues:
        reason_for_critique += f"Validation issues found: {'; '.join(val_issues)}. "
    if dc_status == "error" or (dc_status == "defined" and dc_issues): # If defined but still has issues, or outright error
        reason_for_critique += f"Data contract issues: {'; '.join(dc_issues)}. "
    
    if not code_in_question: # ... (as before)
        logger.error("Critique: No code."); return {**state, "critique": "Error: No code.", "current_error": "Critique: No code."}
    if not reason_for_critique: # ... (as before)
        logger.warning("Critique: No failure/validation/contract issue."); return {**state, "critique": "No specific issue.", "current_error": "Critique: No failure."}

    logger.debug(f"Critique agent analyzing. Reason: {reason_for_critique.strip()[:150]}...")
    debugging_tips_context = get_rag_context("critique", f"Debugging tips for: {reason_for_critique}")
        
    llm_critique = get_llm_instance("critique_llm", state, temperature=0.25, mock_response="Mock critique: Address data contract issues.")
    # Update critique prompt to include data contract feedback explicitly if needed, or rely on general reason
    # For now, assuming 'reason_for_critique' covers it well enough in the prompt.
    # The prompt already includes: "Validation Issues (if any): {validation_issues_list}"
    # We should add data contract issues to the prompt.
    # Let's assume critique_prompt_template is updated to handle a combined list of issues or separate fields.
    # For this MVP, just ensuring `reason_for_critique` captures it for the LLM is a start.
    # A better prompt would have specific slots for test_failure, validation_issues, data_contract_issues.
    # Let's make a small adjustment to the critique_prompt_template invocation.
    critique_chain_instance = critique_prompt_template | llm_critique | StrOutputParser()
    critique_input = {
        "task_description": task_desc, "planner_notes": planner_notes_str or "None",
        "code_in_question": code_in_question,
        "test_failure_message": test_failure_msg if state.get("test_status") != "success" else "N/A",
        "validation_issues_list": "; ".join(val_issues) if val_issues else "N/A",
        # Add data contract issues to prompt. Prompt needs to be updated to accept this.
        # For now, included in 'reason_for_critique' passed in debugging_tips_context RAG query.
        "debugging_tips_context": debugging_tips_context
    }
    # For a quick fix, let's add data contract issues to validation_issues_list for the prompt
    # THIS IS A SIMPLIFICATION - ideally prompt has its own slot.
    combined_issues_for_prompt = val_issues
    if dc_issues: combined_issues_for_prompt = combined_issues_for_prompt + [f"DataContractIssue: {i}" for i in dc_issues]
    critique_input["validation_issues_list"] = "; ".join(combined_issues_for_prompt) if combined_issues_for_prompt else "N/A"
    
    critique_output = critique_chain_instance.invoke(critique_input)
    logger.info(f"Generated Critique: {critique_output}. Exiting Critique Node.")
    updated_feedback_history = list(state.get("feedback_history", []))
    updated_feedback_history.append(f"Critique on DevAttempt {state['refinement_count']}: {critique_output} (Reason: {reason_for_critique.strip()})")
    return {**state, "critique": critique_output, "current_error": None, "feedback_history": updated_feedback_history}
def artifact_packaging_node(state: GraphState) -> GraphState: # Updated to include data contract
    logger.info("Entering Artifact Packaging Node")
    generated_code = state["generated_code"]
    task_desc = state["task_description"]
    planner_notes = state["planner_notes"]
    function_name = state["current_test_case"]["function_name"]
    data_contract_str = state.get("data_contract")
    data_contract_status = state.get("data_contract_status")

    if not generated_code: # ... (as before)
        logger.error("Packaging: No code."); return {**state, "current_error": "Packaging: No code."}
    try:
        run_timestamp = time.strftime("%Y%m%d-%H%M%S"); package_dir = ARTIFACTS_BASE_DIR / f"run_{run_timestamp}" / function_name
        package_dir.mkdir(parents=True, exist_ok=True)
        code_file_path = package_dir / f"{function_name}.py"; readme_file_path = package_dir / "README.md"
        with open(code_file_path, "w") as f: f.write(generated_code)
        logger.info(f"Saved code to: {code_file_path}")

        readme_content = f"# Artifacts for: {function_name}\n\n## Task:\n{task_desc}\n## Planner Notes:\n{planner_notes or 'None'}\n## Status:\nSuccess\n"
        
        packaged_files = {
            "package_directory": str(package_dir),
            "code_file": str(code_file_path.relative_to(ARTIFACTS_BASE_DIR.parent)),
            "readme_file": str(readme_file_path.relative_to(ARTIFACTS_BASE_DIR.parent))
        }

        if data_contract_str and data_contract_status == "defined":
            contract_file_path = package_dir / f"{function_name}_contract.json"
            with open(contract_file_path, "w") as f:
                # Attempt to pretty-print if it's valid JSON
                try: json.dump(json.loads(data_contract_str), f, indent=2)
                except json.JSONDecodeError: f.write(data_contract_str) # Write as is if not valid JSON (should be caught earlier)
            logger.info(f"Saved data contract to: {contract_file_path}")
            readme_content += f"\n## Data Contract:\nSee `{contract_file_path.name}`\n"
            packaged_files["data_contract_file"] = str(contract_file_path.relative_to(ARTIFACTS_BASE_DIR.parent))
        elif data_contract_status == "not_applicable":
            readme_content += f"\n## Data Contract:\nStatus: Not Applicable\n"
        
        with open(readme_file_path, "w") as f: f.write(readme_content)
        logger.info(f"Saved README to: {readme_file_path}")
        
        logger.info("Artifacts packaged successfully. Exiting Packaging Node.")
        return {**state, "packaged_artifacts_info": packaged_files, "current_error": None}
    except Exception as e: # ... (as before)
        logger.error(f"Artifact packaging error: {e}", exc_info=True); return {**state, "current_error": f"Packaging Error: {e}"}
def handoff_node(state: GraphState) -> GraphState: # Updated to include data contract info
    logger.info("Entering Handoff Node")
    packaged_info = state["packaged_artifacts_info"]
    task_desc = state["task_description"]
    data_contract_status = state.get("data_contract_status")

    if not packaged_info: # ... (as before)
        summary = f"Handoff for '{task_desc[:50]}...': Failed, no artifact info."; logger.error(summary); return {**state, "handoff_summary": summary, "current_error": "Handoff: No artifact info."}
    
    summary = f"Project '{task_desc[:50]}...' completed!\n"
    summary += f"  Artifacts packaged in: {packaged_info.get('package_directory')}\n"
    summary += f"  - Code: {packaged_info.get('code_file')}\n"
    summary += f"  - README: {packaged_info.get('readme_file')}\n"
    if packaged_info.get("data_contract_file"):
        summary += f"  - Data Contract: {packaged_info.get('data_contract_file')}\n"
    elif data_contract_status == "not_applicable":
        summary += f"  - Data Contract: Not Applicable\n"
    summary += "Ready for human review."
    
    logger.info(f"Handoff Summary:\n{summary}\nExiting Handoff Node.")
    print("\n-------------------- HANDOFF SUMMARY --------------------"); print(summary); print("-------------------------------------------------------\n")
    return {**state, "handoff_summary": summary, "current_error": None}

# --- 6. Define Conditional Edge Logic (decide_after_qa and decide_after_datacontract added/updated) ---
def decide_after_architect(state: GraphState) -> Literal["planner_agent_node", "__end__"]: # ... (as before)
    logger.info("Router: Decide After Architect")
    if state.get("current_error") and "Architect Error:" in state.get("current_error", ""): logger.error(f"Critical Architect Error: {state['current_error']}. Ending workflow."); return END
    if state.get("architectural_decision") and state["architectural_decision"].get("chosen_language"): logger.info("Architect provided a decision. Proceeding to Planner."); return "planner_agent_node"
    logger.error("Architect failed to make a decision. Ending workflow."); state["current_error"] = (state.get("current_error") or "") + " Architect failed to make a decision."; return END
def decide_after_planner(state: GraphState) -> Literal["human_interaction_node", "developer_agent_node", "__end__"]: # ... (as before)
    logger.info("Router: Decide After Planner")
    if state.get("current_error") and "Planner Error:" in state.get("current_error", ""): logger.error(f"Critical Planner Error: {state['current_error']}. Ending."); return END
    questions = state.get("clarification_questions_for_user"); planner_iters = state.get("planner_iteration_count", 0); max_planner_iters = state.get("max_planner_iterations", 2)
    if questions and planner_iters < max_planner_iters: logger.info("Planner needs clarification."); return "human_interaction_node"
    if questions and planner_iters >= max_planner_iters: logger.warning(f"Max planner iterations ({max_planner_iters}) reached. Ending."); state["current_error"] = "Max planner iterations reached."; return END
    if state.get("planned_task_description"): logger.info("Planner provided task. Proceeding to Developer."); return "developer_agent_node"
    logger.error("Planner inaction. Ending."); state["current_error"] = "Planner failed to produce plan/questions."; return END

def decide_after_qa(state: GraphState) -> Literal["data_contract_agent_node", "critique_agent_node", "developer_agent_node", "__end__"]: # Updated target
    logger.info("Router: Decide After QA")
    test_status = state["test_status"]; ref_count = state["refinement_count"]; max_ref = state["max_refinements"]
    if state.get("current_error") and "Planner" in state.get("current_error",""): return END
    if test_status == "success":
        logger.info("QA: Success. Proceeding to Data Contract Agent.")
        return "data_contract_agent_node" # New path
    if test_status == "tool_error": # ... (as before)
        if state.get("current_error") and ("Developer agent" in state.get("current_error","") or "No parsable code" in state.get("current_error","")):
            logger.warning(f"QA: Developer tool error ('{state['current_error']}'). Retrying dev if attempts left ({ref_count}/{max_ref})."); 
            return "developer_agent_node" if ref_count < max_ref else END
        logger.warning(f"QA: QA tool error ('{state.get('test_message', 'Unknown')}'). To Critique if attempts left ({ref_count}/{max_ref})."); 
        return "critique_agent_node" if ref_count < max_ref else END
    logger.info(f"QA: Test FAILED ('{state.get('test_message')}'). To Critique if attempts left ({ref_count}/{max_ref})."); 
    return "critique_agent_node" if ref_count < max_ref else END

def decide_after_datacontract(state: GraphState) -> Literal["validation_agent_node", "critique_agent_node", "__end__"]:
    logger.info("Router: Decide After DataContract")
    dc_status = state["data_contract_status"]
    ref_count = state["refinement_count"]; max_ref = state["max_refinements"]

    if dc_status in ["defined", "not_applicable"] and not state.get("data_contract_issues"): # Success or N/A without issues
        logger.info(f"DataContract: Status '{dc_status}'. Proceeding to Validation Agent.")
        return "validation_agent_node"
    elif dc_status == "error" or state.get("data_contract_issues"): # Error or has issues
        logger.warning(f"DataContract: Status '{dc_status}', Issues: {state.get('data_contract_issues')}. To Critique if attempts left ({ref_count}/{max_ref}).")
        return "critique_agent_node" if ref_count < max_ref else END
    else: # Should not happen
        logger.error(f"DataContract: Unknown status '{dc_status}'. Ending.")
        state["current_error"] = "DataContract: Unknown status."
        return END

def decide_after_validation(state: GraphState) -> Literal["artifact_packaging_node", "critique_agent_node", "__end__"]: # ... (as before)
    logger.info("Router: Decide After Validation")
    validation_status = state["validation_status"]; ref_count = state["refinement_count"]; max_ref = state["max_refinements"]
    if validation_status == "pass": logger.info("Validation: Success. To Packaging."); return "artifact_packaging_node"
    if validation_status == "error": logger.error(f"Validation: Agent ERROR. Ending."); return END
    logger.info(f"Validation: FAILED. To Critique if attempts left ({ref_count}/{max_ref})."); return "critique_agent_node" if ref_count < max_ref else END
def decide_after_packaging(state: GraphState) -> Literal["handoff_node", "__end__"]: # ... (as before)
    logger.info("Router: Decide After Packaging")
    if state.get("current_error") and "Artifact Packaging Error" in state.get("current_error", ""): logger.error(f"Packaging: Error. Ending."); return END
    if state.get("packaged_artifacts_info"): logger.info("Packaging: Success. To Handoff."); return "handoff_node"
    logger.error("Packaging: Unknown state after packaging. Ending."); return END

# --- 7. Assemble the Graph (DataContract node added) ---
def build_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("architect_agent_node", architect_agent_node)
    workflow.add_node("planner_agent_node", planner_agent_node)
    workflow.add_node("human_interaction_node", human_interaction_node)
    workflow.add_node("developer_agent_node", developer_agent_node)
    workflow.add_node("qa_agent_node", qa_agent_node)
    workflow.add_node("data_contract_agent_node", data_contract_agent_node) # New
    workflow.add_node("validation_agent_node", validation_agent_node)
    workflow.add_node("critique_agent_node", critique_agent_node)
    workflow.add_node("artifact_packaging_node", artifact_packaging_node)
    workflow.add_node("handoff_node", handoff_node)

    workflow.set_entry_point("architect_agent_node")
    workflow.add_conditional_edges("architect_agent_node", decide_after_architect, {"planner_agent_node": "planner_agent_node", END: END})
    workflow.add_conditional_edges("planner_agent_node", decide_after_planner, {"human_interaction_node": "human_interaction_node", "developer_agent_node": "developer_agent_node", END: END})
    workflow.add_edge("human_interaction_node", "planner_agent_node")
    workflow.add_edge("developer_agent_node", "qa_agent_node")
    # QA -> DataContract (if tests pass) OR QA -> Critique OR QA -> Dev OR QA -> END
    workflow.add_conditional_edges("qa_agent_node", decide_after_qa, {
        "data_contract_agent_node": "data_contract_agent_node", # Updated target
        "critique_agent_node": "critique_agent_node",
        "developer_agent_node": "developer_agent_node", END: END
    })
    # DataContract -> Validation (if ok) OR DataContract -> Critique OR DataContract -> END
    workflow.add_conditional_edges("data_contract_agent_node", decide_after_datacontract, { # New conditional edge
        "validation_agent_node": "validation_agent_node",
        "critique_agent_node": "critique_agent_node", END: END
    })
    workflow.add_conditional_edges("validation_agent_node", decide_after_validation, {"artifact_packaging_node": "artifact_packaging_node", "critique_agent_node": "critique_agent_node", END: END})
    workflow.add_conditional_edges("artifact_packaging_node", decide_after_packaging, {"handoff_node": "handoff_node", END: END})
    workflow.add_edge("critique_agent_node", "developer_agent_node")
    workflow.add_edge("handoff_node", END)
    
    app = workflow.compile()
    return app

# --- 8. Main Execution / Demo Test ---
def run_demo(cleanup_artifacts=True):
    logger.info("🚀 Starting Autonomous Code Generation Demo (with Data Contract Agent & Docker support) 🚀")
    # ... (artifact cleanup and RAG init as before)
    if cleanup_artifacts and ARTIFACTS_BASE_DIR.exists(): shutil.rmtree(ARTIFACTS_BASE_DIR)
    ARTIFACTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    if not rag_engines["developer"]: initialize_rag_engines() # Check one, assume all init
    if not os.getenv("OPENAI_API_KEY"): logger.warning("OPENAI_API_KEY not found. LLM calls may fail or use mocks.")

    max_refinements_env = int(os.getenv("MAX_REFINEMENTS", "3"))
    max_planner_iterations_env = int(os.getenv("MAX_PLANNER_ITERATIONS", "2"))
    default_llm_models = {
        "architect_llm":  os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o-mini"),
        "planner_llm":    os.getenv("PLANNER_LLM_MODEL", "gpt-4o-mini"),
        "developer_llm":  os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo-instruct"), # Cheaper
        "datacontract_llm": os.getenv("DATACONTRACT_LLM_MODEL", "gpt-3.5-turbo"), # New
        "qa_llm":         os.getenv("QA_LLM_MODEL", "gpt-4o-mini"),
        "validation_llm": os.getenv("VALIDATION_LLM_MODEL", "gpt-3.5-turbo"),
        "critique_llm":   os.getenv("CRITIQUE_LLM_MODEL", "gpt-4o-mini")
    } # ... (as before)
    logger.info(f"Using LLM Configuration: {default_llm_models}")
    logger.info(f"Max Developer Refinements: {max_refinements_env}, Max Planner Iterations: {max_planner_iterations_env}")

    initial_user_req = "I need a Python function `process_user_data(user_dict: dict) -> dict`. It should take a dictionary with 'id' (int) and 'name' (str), and return a new dictionary with an added 'status' (str, default 'active'). Ensure docstrings and type hints."
    initial_state: GraphState = {
        "initial_user_request": initial_user_req,
        "architectural_decision": None,
        "clarified_user_input": None, "clarification_questions_for_user": None,
        "planner_iteration_count": 0, "max_planner_iterations": max_planner_iterations_env,
        "llm_models_config": default_llm_models,
        "task_description": "", "planned_task_description": None, "planner_notes": None,
        # Test case now more complex to warrant a data contract
        "current_test_case": {"function_name": "process_user_data", 
                              "inputs": ({"id": 123, "name": "Alice"},), 
                              "expected_output": {"id": 123, "name": "Alice", "status": "active"}},
        "generated_code": None, "test_status": None, "test_message": None, "critique": None,
        "data_contract_status": None, "data_contract": None, "data_contract_issues": [], # New
        "validation_status": None, "validation_issues": [],
        "packaged_artifacts_info": None, "handoff_summary": None,
        "feedback_history": [], "refinement_count": 0, "max_refinements": max_refinements_env,
        "current_error": None, "qa_agent_messages": []
    }
    app = build_graph()
    logger.info("Invoking the graph...")
    final_state = app.invoke(initial_state)
    logger.info("🏁 Demo Finished. Final State (Key Fields): 🏁")
    # ... (log final state as before, including data_contract fields)
    for key, value in final_state.items():
        if key in ["generated_code", "architectural_decision", "planned_task_description", "planner_notes", "critique", "handoff_summary", "clarified_user_input", "packaged_artifacts_info", "validation_issues", "feedback_history", "data_contract", "data_contract_issues"] and value:
             logger.info(f"  {key}: {value}")
        elif key not in ["qa_agent_messages"]: logger.debug(f"  {key}: {value}")

    logger.info("--- End-to-End Demo Test Verification ---")
    # Success now includes data_contract_status being 'defined' or 'not_applicable' without issues
    final_success = (
        final_state.get("test_status") == "success" and
        final_state.get("validation_status") == "pass" and
        final_state.get("data_contract_status") in ["defined", "not_applicable"] and not final_state.get("data_contract_issues") and
        final_state.get("packaged_artifacts_info") is not None
    )
    if final_success: logger.info(f"✅ PASSED: Full pipeline successful. Handoff: {final_state.get('handoff_summary')}")
    # ... (other failure checks)
    else: logger.error(f"❌ FAILED: Pipeline did not complete successfully. Test: {final_state.get('test_status')}, DC: {final_state.get('data_contract_status')}, Validation: {final_state.get('validation_status')}, Error: {final_state.get('current_error')}")
    return final_state

if __name__ == "__main__":
    # Ensure script name matches what Dockerfile will use, e.g., "main_pipeline.py"
    # For local testing, you might call it directly:
    # final_state_output = run_demo(cleanup_artifacts=True)
    # logger.info("--- Programmatic Assertions (Data Contract & Docker Prep Demo) ---")
    # ... (assertions as before, potentially checking data_contract_status)

    # This part is mainly for when running outside Docker to easily test
    if os.getenv("RUN_DEMO_DIRECTLY", "false").lower() == "true":
        final_state_output = run_demo(cleanup_artifacts=True)
        logger.info("--- Programmatic Assertions (Data Contract & Docker Prep Demo) ---")
        final_success = (
            final_state_output.get("test_status") == "success" and
            final_state_output.get("validation_status") == "pass" and
            final_state_output.get("data_contract_status") in ["defined", "not_applicable"] and not final_state_output.get("data_contract_issues") and
            final_state_output.get("packaged_artifacts_info") is not None and
            final_state_output.get("handoff_summary") is not None and
            not final_state_output.get("current_error")
        )
        acceptable_failure = (
            final_state_output.get("refinement_count",0) >= final_state_output.get("max_refinements",3) or
            (final_state_output.get("current_error") and any(err_key in final_state_output.get("current_error","") for err_key in ["Architect Error", "Planner Error", "Max planner iterations"])) or
            (final_state_output.get("data_contract_status") == "error") or
            (final_state_output.get("validation_status") == "error") or
            (final_state_output.get("current_error") and "Artifact Packaging Error" in final_state_output.get("current_error",""))
        )
        assert final_success or acceptable_failure, \
            f"Demo failed unexpectedly. State: { {k:v for k,v in final_state_output.items() if k not in ['feedback_history','qa_agent_messages']} }"
        logger.info("Programmatic assertions passed for direct run.")
    else:
        logger.info("Script loaded. To run the demo directly (outside Docker for testing), set RUN_DEMO_DIRECTLY=true environment variable.")
        # This allows Docker to import the script without running the demo,
        # if CMD in Dockerfile calls a specific function or this script differently.
        # For a simple CMD ["python", "your_script.py"], the __main__ block will run by default.
        # To be safe, the Docker CMD could be `CMD ["python", "-c", "import your_script; your_script.run_demo()"]`
        # Or, ensure RUN_DEMO_DIRECTLY is not set in Docker env.
        # A common pattern is to have the `if __name__ == "__main__":` block *always* run the demo,
        # and Docker just executes the script.
        # For this case, let's assume Docker simply runs `python main_pipeline.py` and thus will execute run_demo().
        # The RUN_DEMO_DIRECTLY is more for scenarios where you might import this file elsewhere.
        # For simplicity, we'll let __main__ run the demo unless we are in a test import scenario.
        # To make it explicit for Docker:
        # if os.getenv("DOCKER_ENV") == "true":
        #    run_demo()
        # else:
        #    # local run, possibly with different config or only if explicitly called
        #    pass
        # For now, the current __main__ behavior is fine if Docker runs the script directly.
        # Let's make the default action to run the demo in __main__
        run_demo(cleanup_artifacts=True)
