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

# --- -1. Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
logger = logging.getLogger(__name__)


# LlamaIndex Imports (with graceful fallback)
try:
    from llama_index.core import VectorStoreIndex, Document, Settings
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.llms.openai import OpenAI as LlamaOpenAI # Renamed to avoid conflict
    llama_index_available = True
    logger.info("LlamaIndex imported successfully.")
except ImportError:
    logger.warning("LlamaIndex or its OpenAI dependencies not found. RAG features will be disabled.")
    logger.info("   To enable RAG, please install: pip install llama-index llama-index-llms-openai llama-index-embeddings-openai")
    llama_index_available = False

    class Document: # Corrected Definition
        def __init__(self, text: str = "", metadata: Optional[Dict[str, Any]] = None):
            self.text = text
            self.metadata = metadata or {}

    class MockQueryResponse: # Corrected Definition
        def __init__(self, response_text: str = "No RAG context available (LlamaIndex not installed or error)."):
            self.response = response_text
        def __str__(self) -> str:
            return self.response

    class MockQueryEngine: # Corrected Definition
        def query(self, *args: Any, **kwargs: Any) -> MockQueryResponse:
            query_str = args[0] if args else ""
            # Basic mock responses based on query content
            if "architectural principles" in query_str.lower():
                 return MockQueryResponse("Mock architectural principle: Use Python for MVP. Prioritize simplicity and testability.")
            elif "planning guidelines" in query_str.lower():
                 return MockQueryResponse("Mock planning guideline: Define function signature clearly including types and return value. Add notes for edge cases.")
            elif "coding standards" in query_str.lower():
                 return MockQueryResponse("Mock coding standard: Use type hints for all parameters and return values. Include a docstring.")
            elif "validation rules" in query_str.lower():
                 return MockQueryResponse("Mock validation rule: Ensure docstrings are present and type hints are used. Avoid `eval`.")
            elif "debugging tips" in query_str.lower():
                 return MockQueryResponse("Mock debugging tip: For type errors, check input data against function signature. For logic errors, trace variable states.")
            return MockQueryResponse(f"Mock RAG response (LlamaIndex not available) for query: {query_str[:50]}...")


    class MockQueryEngineWrapper: # Corrected Definition
        def as_query_engine(self, *args: Any, **kwargs: Any) -> MockQueryEngine:
            return MockQueryEngine()

    class VectorStoreIndex: # Corrected Definition
        @staticmethod
        def from_documents(*args: Any, **kwargs: Any) -> MockQueryEngineWrapper:
            return MockQueryEngineWrapper()

    class SettingsObject: # Mock for Settings if it were used more complexly
        llm = None
        embed_model = None
        node_parser = None
        # Add other attributes if your actual Settings usage needs them mocked
    
    Settings = SettingsObject() # Assign the mock class instance


# --- 0. Knowledge Base Content & RAG Setup ---
CODING_STANDARDS_TEXT = """
Python Coding Standards for this Project:
1. All functions MUST include type hints for all parameters and for the return value.
2. Function names should be in snake_case.
3. Include a brief docstring explaining the function's purpose, args, and return, unless the function is trivial and its name is self-explanatory.
4. For arithmetic operations, ensure inputs are handled as numbers. If specific types like int or float are expected, hint them.
5. Code should be well-formatted and readable.
"""
PLANNING_GUIDELINES_TEXT = """
Project Planning Guidelines:
1. Decompose complex requests into smaller, manageable function definitions.
2. Clearly specify the expected inputs and outputs for each function, including their types.
3. Identify any external libraries or modules that might be needed.
4. Note any specific constraints or edge cases mentioned in the user request.
5. The primary output should be a clear task description for a developer to implement a single Python function.
"""
DEBUGGING_TIPS_TEXT = """
Common Python Debugging Tips:
1. For TypeErrors, double-check that the data types of variables match the function's expectations and type hints.
2. For SyntaxErrors, carefully review the indicated line and surrounding lines for typos, missing colons, or incorrect indentation.
3. For NameErrors, ensure all variables are defined before use and spelled correctly.
4. When a test fails (e.g., expected X, got Y), analyze the discrepancy. Is it an off-by-one error, a logical flaw, or an incorrect formula?
5. Print statements (or a debugger) can help trace variable values at different stages of execution.
"""
VALIDATION_RULES_TEXT = """
General Validation Rules for Python Code:
1. Security:
    - Avoid using `eval()` with untrusted input.
    - Do not hardcode sensitive credentials (API keys, passwords).
    - Check for common injection vulnerabilities if handling external data (not applicable to simple math functions but good general advice).
2. Compliance & Quality:
    - Functions MUST include type hints for all parameters and return values.
    - Functions SHOULD have a docstring explaining purpose, args, and returns, especially if non-trivial.
    - Adhere to naming conventions (e.g., snake_case for functions and variables).
    - Code should be readable and well-formatted.
    - Check if the code seems to implement the core logic requested in the task description.
"""
ARCHITECTURAL_PRINCIPLES_TEXT = """
Architectural Principles for Project "Autonomous Coder MVP":
1. Language Choice: For initial MVPs focusing on single functions or simple scripts, Python is the preferred language due to its ease of use and extensive libraries.
2. Frameworks: Prefer standard Python libraries unless a specific framework (e.g., Flask for a web endpoint, Spark for big data - though out of scope for current MVP) is explicitly justified by the request's complexity and nature.
3. Simplicity: Favor simple, direct solutions. Avoid over-engineering.
4. Testability: Ensure the planned components are designed in a way that facilitates unit testing.
5. Modularity: Functions should be self-contained and perform a single, well-defined task.
6. Output: The architect should produce a JSON object with 'chosen_language', 'framework_hint', and 'high_level_notes'.
"""
developer_rag_query_engine_global, planner_rag_query_engine_global, critique_rag_query_engine_global, validation_rag_query_engine_global, architect_rag_query_engine_global = None, None, None, None, None

def initialize_rag_engines():
    global developer_rag_query_engine_global, planner_rag_query_engine_global, critique_rag_query_engine_global, validation_rag_query_engine_global, architect_rag_query_engine_global
    if not llama_index_available or not os.getenv("OPENAI_API_KEY"):
        engines = [MockQueryEngineWrapper().as_query_engine()] * 5
        developer_rag_query_engine_global, planner_rag_query_engine_global, critique_rag_query_engine_global, validation_rag_query_engine_global, architect_rag_query_engine_global = engines
        logger.warning("RAG: Disabled (LlamaIndex/API key missing). Using mock query engines.")
        return
    logger.info("RAG: Initializing LlamaIndex query engines...")
    try:
        # Optional: Configure global LlamaIndex settings if needed
        # Settings.llm = LlamaOpenAI(model="gpt-3.5-turbo") # For LlamaIndex's internal use
        # Settings.embed_model = OpenAIEmbedding() # Uses default OpenAI embedding model

        dev_docs = [Document(text=CODING_STANDARDS_TEXT, metadata={"source": "coding_standards.txt"})]
        dev_index = VectorStoreIndex.from_documents(dev_docs)
        developer_rag_query_engine_global = dev_index.as_query_engine(similarity_top_k=1)
        
        planner_docs = [Document(text=PLANNING_GUIDELINES_TEXT, metadata={"source": "planning_guidelines.txt"})]
        planner_index = VectorStoreIndex.from_documents(planner_docs)
        planner_rag_query_engine_global = planner_index.as_query_engine(similarity_top_k=1)
        
        critique_docs = [Document(text=DEBUGGING_TIPS_TEXT, metadata={"source": "debugging_tips.txt"})]
        critique_index = VectorStoreIndex.from_documents(critique_docs)
        critique_rag_query_engine_global = critique_index.as_query_engine(similarity_top_k=1)
        
        validation_docs = [Document(text=VALIDATION_RULES_TEXT, metadata={"source": "validation_rules.txt"})]
        validation_index = VectorStoreIndex.from_documents(validation_docs)
        validation_rag_query_engine_global = validation_index.as_query_engine(similarity_top_k=2)
        
        architect_docs = [Document(text=ARCHITECTURAL_PRINCIPLES_TEXT, metadata={"source": "architectural_principles.txt"})]
        architect_index = VectorStoreIndex.from_documents(architect_docs)
        architect_rag_query_engine_global = architect_index.as_query_engine(similarity_top_k=2)
        logger.info("RAG: All RAG engines initialized successfully.")
    except Exception as e:
        logger.error(f"RAG: Error initializing LlamaIndex: {e}. Using mock engines.", exc_info=True)
        engines = [MockQueryEngineWrapper().as_query_engine()] * 5
        developer_rag_query_engine_global, planner_rag_query_engine_global, critique_rag_query_engine_global, validation_rag_query_engine_global, architect_rag_query_engine_global = engines

# --- 1. Define the State for the Graph ---
class TestCase(TypedDict):
    function_name: str; inputs: Tuple[Any, ...]; expected_output: Any
class GraphState(TypedDict):
    initial_user_request: str
    architectural_decision: Optional[Dict[str, Any]]
    clarified_user_input: Optional[str]; clarification_questions_for_user: Optional[List[str]]
    planner_iteration_count: int; max_planner_iterations: int; llm_models_config: Dict[str, str]
    planned_task_description: Optional[str]; planner_notes: Optional[str]; task_description: str
    current_test_case: TestCase; generated_code: Optional[str]
    test_status: Optional[Literal['success', 'compilation_error', 'runtime_error', 'test_fail', 'tool_error']]
    test_message: Optional[str]; critique: Optional[str]
    validation_status: Optional[Literal['pass', 'fail', 'error']]; validation_issues: Optional[List[str]]
    packaged_artifacts_info: Optional[Dict[str, str]]; handoff_summary: Optional[str]
    feedback_history: List[str]; refinement_count: int; max_refinements: int
    current_error: Optional[str]; qa_agent_messages: List


# --- 2. Define Tools ---
@tool
def code_tester_tool(code_string: str, function_name: str, test_inputs: tuple, expected_output: any) -> dict:
    if not code_string: return {"status": "compilation_error", "message": "No code provided."}
    try:
        scope = {'__builtins__': __builtins__}; exec(code_string, scope, scope)
        if function_name not in scope: return {"status": "compilation_error", "message": f"Function '{function_name}' not defined."}
        actual = scope[function_name](*test_inputs)
        if actual == expected_output: return {"status": "success", "message": "Test passed.", "actual_output": actual}
        return {"status": "test_fail", "message": f"Input: {test_inputs}, Expected: {expected_output}, Got: {actual}", "actual_output": actual}
    except Exception as e: logger.error(f"Code tester tool runtime error: {e}", exc_info=False); return {"status": "runtime_error", "message": str(e)}

# --- 3. Helper function to extract Python code ---
def extract_python_code(llm_output: str) -> Optional[str]:
    match = re.search(r"```python\n(.*?)\n```", llm_output, re.DOTALL)
    if match: return match.group(1).strip()
    match = re.search(r"```\n(.*?)\n```", llm_output, re.DOTALL)
    if match: return match.group(1).strip()
    return None

# --- 4. Define LLMs & Prompts ---
def get_llm_instance(model_name_key: str, state: GraphState, default_model="gpt-3.5-turbo-0125", temperature=0.2, mock_response="") -> ChatOpenAI:
    model_name = state["llm_models_config"].get(model_name_key, default_model)
    logger.debug(f"Initializing LLM for '{model_name_key}' with model '{model_name}'.")
    try: return ChatOpenAI(model=model_name, temperature=temperature)
    except Exception as e:
        logger.error(f"LLM init error for {model_name_key} ({model_name}): {e}. Using mock.", exc_info=True)
        class MockLLM:
            def invoke(self, *args: Any, **kwargs: Any) -> str: logger.warning(f"MockLLM invoked for {model_name_key}"); return mock_response
        return MockLLM() # type: ignore

class SimpleJsonOutputParser(StrOutputParser):
    def parse(self, text:str) -> Any:
        # Try to extract JSON from ```json ... ``` markdown block
        match_md = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
        if match_md:
            json_text = match_md.group(1).strip()
        else:
            # If no markdown, assume the whole text is JSON or attempt to find JSON object within text
            match_obj = re.search(r"\{.*\}", text, re.DOTALL)
            if match_obj:
                json_text = match_obj.group(0)
            else: # No clear JSON object found
                logger.error(f"JSON Parser: No JSON block or object found in text: {text[:200]}...")
                return {"error": "JSON parsing failed: No JSON found", "raw_text": text}
        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parser Error: {e} in JSON text: {json_text[:200]}...")
            return {"error": f"JSON parsing failed: {e}", "raw_json_text": json_text, "original_text": text}


# Architect LLM & Chain
architect_prompt_template = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Senior Software Architect. Your role is to analyze a user request and make high-level technical decisions. "
     "Consult the Architectural Principles provided.\n"
     "--- BEGIN ARCHITECTURAL PRINCIPLES ---\n{architectural_principles_context}\n--- END ARCHITECTURAL PRINCIPLES ---\n"
     "Based on the user request and these principles, determine the 'chosen_language' (e.g., 'python'), "
     "'framework_hint' (e.g., 'standard_library', 'flask', 'pyspark'), and provide 'high_level_notes' for the planning agent. "
     "For current MVP scope, assume Python and standard libraries are preferred for simple function requests. "
     "Output ONLY a valid JSON object with these three keys: 'chosen_language', 'framework_hint', 'high_level_notes'. Do not include any other text or markdown."),
    ("human", "User Request: {user_request}")
])

# Planner LLM & Chain
planner_prompt_template = ChatPromptTemplate.from_messages([
    ("system",
     "You are an expert requirements analyst and planner. Your goal is to refine a user request into a clear, actionable task for a developer. "
     "You have received an architectural decision: Language='{chosen_language}', Framework Hint='{framework_hint}', Architect Notes='{architect_notes}'. "
     "Incorporate these into your planning. Consult Planning Guidelines.\n"
     "--- BEGIN PLANNING GUIDELINES ---\n{planning_guidelines_context}\n--- END PLANNING GUIDELINES ---\n"
     "If the user request (considering architect's input) is clear enough to define a single function in the chosen language, output ONLY a valid JSON object with 'planned_task_description', 'planner_notes', and an empty 'clarification_questions' list (e.g., `[]`).\n"
     "If ambiguous, output ONLY a valid JSON object with a list of specific 'clarification_questions' for the user, and set 'planned_task_description' and 'planner_notes' to null or omit them. "
     "The 'planned_task_description' should be very specific about the function name, parameters (with types), return type, and expected behavior."),
    ("human", "User Request to process (already incorporates architect's context implicitly): {user_request_to_process}")
])

# Developer, Validation, Critique, QA LLM Prompts
dev_code_gen_prompt_template = ChatPromptTemplate.from_messages([
    ("system", "You are an expert Python coding assistant. Your task is to write or revise Python function code based on the provided task description and feedback. "
               "ONLY output the Python code block for the function itself, enclosed in ```python ... ```. "
               "Adhere strictly to the coding standards and planner notes.\n"
               "--- BEGIN CODING STANDARDS ---\n{coding_standards_context}\n--- END CODING STANDARDS ---\n"
               "Planner Notes: {developer_notes}\n\n"
               "Focus on addressing the LATEST critique and test failure/validation messages. Previous feedback history is for context only."),
    ("human", "Task: {developer_task_description}\n\n"
              "--- LATEST FEEDBACK TO ADDRESS ---\n"
              "Critique: {critique_message}\n"
              "--- END LATEST FEEDBACK ---\n\n"
              "Full Feedback History (for context, if any errors persist from these, address them too):\n{full_feedback_history}\n\n"
              "Please generate the revised code.")])

validation_prompt_template = ChatPromptTemplate.from_messages([
    ("system", "You are a code validation agent. Your task is to review Python code for security vulnerabilities and compliance with project standards. "
               "Consult the provided Validation Rules.\n"
               "--- BEGIN VALIDATION RULES ---\n{validation_rules_context}\n--- END VALIDATION RULES ---\n"
               "Analyze the code against these rules and the task description. "
               "Output ONLY a valid JSON object with two keys: 'validation_passed' (boolean: true if no issues, false if any issues are found) and 'issues_found' (a list of strings, where each string describes a specific issue found; empty if validation_passed is true)."),
    ("human", "Task Description: {task_description}\nPlanner Notes: {planner_notes}\nCode to Validate:\n```python\n{code_to_validate}\n```\n\nPlease perform validation.")])

critique_prompt_template = ChatPromptTemplate.from_messages([
    ("system", "You are a code critique agent. Analyze failed code OR code with validation issues. Provide constructive feedback for a developer. "
               "Focus on the root cause and suggest specific changes. Consult debugging tips if relevant.\n"
               "--- BEGIN DEBUGGING TIPS ---\n{debugging_tips_context}\n--- END DEBUGGING TIPS ---\n"
               "Provide a concise critique (1-3 sentences). Do not rewrite the code yourself."),
    ("human", "Task Description: {task_description}\nPlanner Notes: {planner_notes}\nCode in Question:\n```python\n{code_in_question}\n```\nTest Failure Message (if any): {test_failure_message}\nValidation Issues (if any): {validation_issues_list}\n\nPlease provide a critique and suggestions for the developer based on any available failure or validation issues.")])

qa_tools = [code_tester_tool]
qa_agent_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a meticulous QA agent. Your primary responsibility is to assess Python code provided by a developer. "
               "You have access to a 'code_tester_tool'. "
               "1. Review the code against the task description and specific test case. "
               "2. Decide if the 'code_tester_tool' is appropriate to use. If so, determine the correct arguments for it. "
               "   The tool requires: 'code_string', 'function_name', 'test_inputs', and 'expected_output'. "
               "3. Execute the tool with these arguments to get a definitive pass/fail result. "
               "4. Report the outcome based on the tool's execution. "
               "Do not attempt to fix the code yourself or simulate the test. Your role is to correctly invoke the testing tool and interpret its results."),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "Task Description (from planner): {task_description_for_qa}\nTest Case: Function '{function_name}' with inputs {test_inputs} should produce {expected_output}.\nDeveloper's Generated Code to Test:\n```python\n{generated_code}\n```\n\nPlease make a decision on testing, use the 'code_tester_tool' appropriately, and report the precise outcome.")])


# --- 5. Define Graph Nodes ---
ARTIFACTS_BASE_DIR = Path("output_artifacts_demo")

def architect_agent_node(state: GraphState) -> GraphState:
    logger.info("Entering Architect Node")
    user_request = state["initial_user_request"]
    
    architectural_principles_context = "No architectural principles RAG context available."
    if architect_rag_query_engine_global:
        try:
            response = architect_rag_query_engine_global.query("General architectural principles for this project type and user request.")
            architectural_principles_context = str(response)
            logger.debug(f"Architect RAG context: {architectural_principles_context[:100]}...")
        except Exception as e:
            logger.warning(f"RAG error (architect): {e}"); architectural_principles_context = f"RAG error (architect): {e}"

    llm_architect = get_llm_instance("architect_llm", state, temperature=0.2, mock_response='{"chosen_language": "python", "framework_hint": "standard_library", "high_level_notes": "Focus on a clear, single Python function for this MVP."}')
    architect_chain_instance = architect_prompt_template | llm_architect | SimpleJsonOutputParser()
    
    arch_decision_json = architect_chain_instance.invoke({
        "user_request": user_request,
        "architectural_principles_context": architectural_principles_context
    })
    logger.debug(f"Architect LLM Raw Output (parsed): {arch_decision_json}")

    if isinstance(arch_decision_json, dict) and "chosen_language" in arch_decision_json and not arch_decision_json.get("error"):
        logger.info(f"Architect Decision: Language='{arch_decision_json.get('chosen_language')}', Framework='{arch_decision_json.get('framework_hint')}', Notes='{arch_decision_json.get('high_level_notes', '')[:50]}...'. Exiting Architect Node.")
        return {
            **state, "architectural_decision": arch_decision_json, "current_error": None,
            "planned_task_description": None, "planner_notes": None, "task_description": "",
            "clarified_user_input": None, "clarification_questions_for_user": None,
            "planner_iteration_count": 0, "generated_code": None, "test_status": None, "critique": None,
            "validation_status": None, "packaged_artifacts_info": None, "handoff_summary": None,
            "feedback_history": [], "refinement_count": 0
        }
    else:
        error_msg = f"Architect Error: Invalid output format or missing key fields from LLM. Output: {arch_decision_json}"
        logger.error(error_msg)
        return {**state, "architectural_decision": None, "current_error": error_msg}

def planner_agent_node(state: GraphState) -> GraphState:
    logger.info(f"Entering Planner Node (Iteration {state['planner_iteration_count'] + 1})")
    arch_decision = state["architectural_decision"]
    if not arch_decision or not isinstance(arch_decision, dict) or "chosen_language" not in arch_decision:
        error_msg = "Planner Error: Missing or invalid architectural decision from Architect."
        logger.error(error_msg)
        return {**state, "current_error": error_msg, "clarification_questions_for_user": None}

    current_request_to_process = state.get("clarified_user_input") or state["initial_user_request"]
    logger.debug(f"Planner processing request: {current_request_to_process[:100]}... with Arch: {arch_decision}")
    
    planning_context = "No planning guidelines RAG context available."
    if planner_rag_query_engine_global:
        try: response = planner_rag_query_engine_global.query(f"Planning guidelines for a '{arch_decision.get('chosen_language')}' task using '{arch_decision.get('framework_hint')}'."); planning_context = str(response)
        except Exception as e: logger.warning(f"RAG error (planner): {e}"); planning_context = f"RAG error (planner): {e}"
    
    llm_planner = get_llm_instance("planner_llm", state, temperature=0.3, mock_response='{"clarification_questions": [], "planned_task_description": "Mock plan for greet function", "planner_notes": "Mock notes: Ensure docstring for greet function."}')
    planner_chain_instance = planner_prompt_template | llm_planner | SimpleJsonOutputParser()
    
    planned_output_json = planner_chain_instance.invoke({
        "user_request_to_process": current_request_to_process,
        "planning_guidelines_context": planning_context,
        "chosen_language": arch_decision.get("chosen_language", "python"),
        "framework_hint": arch_decision.get("framework_hint", "standard_library"),
        "architect_notes": arch_decision.get("high_level_notes", "None")
    })
    logger.debug(f"Planner LLM Raw Output (parsed): {planned_output_json}")
    
    new_planner_iteration_count = state["planner_iteration_count"] + 1; questions_for_user = []; planned_task_desc = None; planner_notes_str = None; current_error_for_state = None
    if isinstance(planned_output_json, dict) and not planned_output_json.get("error"):
        questions_for_user = planned_output_json.get("clarification_questions", [])
        if not isinstance(questions_for_user, list): questions_for_user = [] # Robustness
        
        if not questions_for_user:
            planned_task_desc = planned_output_json.get("planned_task_description")
            planner_notes_str = planned_output_json.get("planner_notes")
            if not planned_task_desc: current_error_for_state = "Planner Error: No plan provided and no clarification questions asked by LLM."
        else: logger.info(f"Planner generated clarification questions: {questions_for_user}")
    else: current_error_for_state = f"Planner Error: Invalid output format from LLM or parsing error. Output: {planned_output_json}"
    
    logger.info(f"Exiting Planner Node. Questions asked: {bool(questions_for_user)}. Plan generated: {bool(planned_task_desc)}")
    return {
        **state, "planned_task_description": planned_task_desc, 
        "task_description": planned_task_desc if planned_task_desc else state.get("task_description",""), # Keep old task_desc if new plan fails
        "planner_notes": planner_notes_str, 
        "clarification_questions_for_user": questions_for_user if questions_for_user else None,
        "clarified_user_input": None, "planner_iteration_count": new_planner_iteration_count, "current_error": current_error_for_state,
        "critique": None, "validation_status": None, "validation_issues": [], "packaged_artifacts_info": None, "handoff_summary": None,
        "generated_code": None, "test_status": None, "test_message": None,
        "feedback_history": [] if new_planner_iteration_count == 1 else state.get("feedback_history",[]),
        "refinement_count": 0 if new_planner_iteration_count == 1 else state.get("refinement_count",0)
    }

def human_interaction_node(state: GraphState) -> GraphState:
    logger.info("Entering Human Interaction Node")
    questions = state["clarification_questions_for_user"]
    if not questions: logger.warning("No clarification questions found. Skipping HITL."); return {**state}
    
    print("\n🤔 The Planner Agent needs clarification. Please answer the following questions:") # Keep print for direct user interaction
    answers = []
    for i, q_text in enumerate(questions):
        while True:
            answer = input(f"  Q{i+1}: {q_text}\n  Your Answer: ").strip()
            if answer: break
            print("   Please provide an answer.")
        answers.append(f"Answer to '{q_text}': {answer}")
    
    clarified_input_str = f"Original Request: '{state['initial_user_request']}'. User Clarifications: {'; '.join(answers)}"
    logger.info(f"Human provided clarifications. New input for Planner: {clarified_input_str[:150]}...")
    return {**state, "clarified_user_input": clarified_input_str, "clarification_questions_for_user": None, "current_error": None}

def developer_agent_node(state: GraphState) -> GraphState:
    logger.info("Entering Developer Node")
    dev_task_description = state["task_description"]; dev_notes = state["planner_notes"]; 
    latest_critique = state.get("critique", "No specific critique. Focus on initial implementation or previous test/validation feedback if any.")
    # Use test_message as part of critique context, not a separate field in dev prompt for simplicity
    full_feedback_history_list = state.get("feedback_history", [])
    refinement_count = state["refinement_count"]

    if not dev_task_description or "Error:" in dev_task_description:
        logger.error(f"Developer received invalid task from planner: {dev_task_description}")
        return {**state, "generated_code": None, "test_status": "tool_error", "current_error": dev_task_description, "refinement_count": refinement_count + 1} # Count failed attempt
    
    logger.debug(f"Developer task: {dev_task_description[:100]}..., Critique: {latest_critique[:100]}...")
    coding_standards_context = "No coding standards RAG context available."
    if developer_rag_query_engine_global:
        try: response = developer_rag_query_engine_global.query(f"Coding standards for: {dev_task_description}"); coding_standards_context = str(response)
        except Exception as e: logger.warning(f"RAG error (developer): {e}"); coding_standards_context = f"RAG error (developer): {e}"
    
    llm_developer = get_llm_instance("developer_llm", state, mock_response="```python\n# Mocked Code by Developer\ndef example():\n  pass\n```")
    developer_chain_instance = dev_code_gen_prompt_template | llm_developer | StrOutputParser()
    
    llm_response = developer_chain_instance.invoke({
        "developer_task_description": dev_task_description, 
        "developer_notes": dev_notes or "None",
        "coding_standards_context": coding_standards_context, 
        "critique_message": latest_critique,
        "full_feedback_history": "\n".join(full_feedback_history_list) if full_feedback_history_list else "This is the first attempt for this version of the plan."
    })
    generated_code_str = extract_python_code(llm_response)
    
    current_attempt_count = refinement_count + 1
    if not generated_code_str:
        error_message = "Developer agent failed to produce a parsable code block."
        logger.error(error_message + f" LLM Raw: {llm_response[:100]}...")
        # Add this specific failure to feedback_history for the critique agent
        updated_feedback_history = list(state.get("feedback_history", []))
        updated_feedback_history.append(f"DevAttempt {current_attempt_count}: Failed to generate parsable code. LLM raw output snippet: '{llm_response[:100]}...'")
        return {**state, "generated_code": None, "test_status": "tool_error", "test_message": error_message,
                "current_error": error_message, "refinement_count": current_attempt_count, "feedback_history": updated_feedback_history}
                
    logger.info(f"Developer generated code (Attempt {current_attempt_count}). Exiting Developer Node.")
    return {**state, "generated_code": generated_code_str, "refinement_count": current_attempt_count, "current_error": None,
            "critique": None, "validation_status": None, "validation_issues": [], "packaged_artifacts_info": None, "handoff_summary": None}

def validation_agent_node(state: GraphState) -> GraphState:
    logger.info("Entering Validation Node")
    code_to_validate = state["generated_code"]; task_desc = state["task_description"]; planner_notes_str = state["planner_notes"]
    if not code_to_validate:
        logger.error("Validation: No code provided.")
        return {**state, "validation_status": "error", "validation_issues": ["No code provided for validation."], "current_error": "Validation: No code."}
    logger.debug(f"Validation agent reviewing code for task: {task_desc[:100]}...")
    validation_rules_context = "No validation rules RAG context available."
    if validation_rag_query_engine_global:
        try: response = validation_rag_query_engine_global.query(f"Validation rules for Python code related to task: {task_desc}"); validation_rules_context = str(response)
        except Exception as e: logger.warning(f"RAG error (validation): {e}"); validation_rules_context = f"RAG error (validation): {e}"
    
    llm_validation = get_llm_instance("validation_llm", state, temperature=0.1, mock_response='{"validation_passed": true, "issues_found": []}')
    validation_chain_instance = validation_prompt_template | llm_validation | SimpleJsonOutputParser()
    validation_output_json = validation_chain_instance.invoke({
        "task_description": task_desc, "planner_notes": planner_notes_str or "None",
        "code_to_validate": code_to_validate, "validation_rules_context": validation_rules_context
    })
    logger.debug(f"Validation LLM Raw Output (parsed): {validation_output_json}")
    
    issues_found = []; val_passed = False; val_status: Literal['pass', 'fail', 'error']
    if isinstance(validation_output_json, dict) and not validation_output_json.get("error"):
        val_passed = validation_output_json.get("validation_passed", False)
        issues_found = validation_output_json.get("issues_found", [])
        if not isinstance(issues_found, list): issues_found = [str(issues_found)] if issues_found else []
        
        val_status = "pass" if val_passed and not issues_found else "fail"
        if val_passed and issues_found: # Contradiction from LLM
            val_status = "fail"
            logger.warning("Validation LLM reported pass=true but also listed issues. Overriding to fail.")
            issues_found.append("Internal Consistency: LLM reported pass but listed issues.")
        elif not val_passed and not issues_found: # LLM said fail but no reasons
             issues_found = ["Validation failed but no specific issues were reported by the validation agent."]
    else: 
        issues_found = [f"Validation agent did not return expected JSON format or encountered parsing error. Output: {validation_output_json}"]
        val_status = "error"
        
    logger.info(f"Validation Status: {val_status}, Issues: {issues_found}. Exiting Validation Node.")
    return {**state, "validation_status": val_status, "validation_issues": issues_found if issues_found else [], "current_error": None}

def critique_agent_node(state: GraphState) -> GraphState:
    logger.info("Entering Critique Node")
    code_in_question = state["generated_code"]; task_desc = state["task_description"]; planner_notes_str = state["planner_notes"]
    test_failure_msg = state.get("test_message", "") # "" instead of N/A for easier concatenation
    val_issues = state.get("validation_issues", [])
    
    reason_for_critique = ""
    if state.get("test_status") not in ["success", "tool_error", None] and test_failure_msg: 
        reason_for_critique += f"Functional test failed: {test_failure_msg}. "
    if val_issues: 
        reason_for_critique += f"Validation issues found: {'; '.join(val_issues)}. "

    if not code_in_question: 
        logger.error("Critique: No code provided to critique."); 
        return {**state, "critique": "Error: No code provided to critique.", "current_error": "Critique: No code."}
    if not reason_for_critique.strip(): 
        # This can happen if a tool_error from dev/QA led here without a specific code issue to critique.
        # Or if validation passed but somehow routed here (graph logic error).
        logger.warning("Critique: No specific test failure or validation issue to critique. Providing general guidance.");
        critique_output = "The previous step resulted in an error or an issue that needs developer attention. Please review the logs and the task requirements carefully to identify the problem and generate corrected code."
    else:
        logger.debug(f"Critique agent analyzing. Reason: {reason_for_critique.strip()[:150]}...")
        debugging_tips_context = "No debugging tips RAG context available."
        if critique_rag_query_engine_global:
            try: response = critique_rag_query_engine_global.query(f"Debugging tips for: {reason_for_critique.strip()}"); debugging_tips_context = str(response)
            except Exception as e: logger.warning(f"RAG error (critique): {e}"); debugging_tips_context = f"RAG error (critique): {e}"
        
        llm_critique = get_llm_instance("critique_llm", state, temperature=0.25, mock_response="Mock critique: Re-check the core logic and ensure all requirements from planner notes are met.")
        critique_chain_instance = critique_prompt_template | llm_critique | StrOutputParser()
        critique_output = critique_chain_instance.invoke({
            "task_description": task_desc, "planner_notes": planner_notes_str or "None", 
            "code_in_question": code_in_question,
            "test_failure_message": test_failure_msg if state.get("test_status") != "success" else "N/A",
            "validation_issues_list": "; ".join(val_issues) if val_issues else "N/A", 
            "debugging_tips_context": debugging_tips_context
        })
        
    logger.info(f"Generated Critique: {critique_output}. Exiting Critique Node.")
    updated_feedback_history = list(state.get("feedback_history", []))
    # Add the current raw test message and validation issues to feedback history before the new critique
    if test_failure_msg: updated_feedback_history.append(f"Raw Test Failure (DevAttempt {state['refinement_count']}): {test_failure_msg}")
    if val_issues: updated_feedback_history.append(f"Raw Validation Issues (DevAttempt {state['refinement_count']}): {'; '.join(val_issues)}")
    updated_feedback_history.append(f"Critique on DevAttempt {state['refinement_count']}: {critique_output}")
    
    return {**state, "critique": critique_output, "current_error": None, "feedback_history": updated_feedback_history}

def qa_agent_node(state: GraphState) -> GraphState:
    logger.info("Entering QA Node (Explicit Tool Protocol Logging)")
    generated_code = state["generated_code"]; task_desc_for_qa = state["task_description"]; test_case = state["current_test_case"]
    if not generated_code: 
        logger.error("QA: No code provided by developer.")
        return {**state, "test_status": "tool_error", "test_message": "No code from dev for QA."} # current_error set by dev_node
    
    logger.debug(f"QA Agent evaluating code for function '{test_case['function_name']}' (Dev Attempt {state['refinement_count']})")
    test_status_from_agent = "tool_error"; test_message_from_agent = "QA agent did not successfully complete testing or parse results."
    try:
        agent_input = {
            "task_description_for_qa": task_desc_for_qa, "function_name": test_case['function_name'],
            "test_inputs": test_case['inputs'], "expected_output": test_case['expected_output'],
            "generated_code": generated_code, "chat_history": state.get("qa_agent_messages", [])
        }
        llm_qa = get_llm_instance("qa_llm", state, temperature=0.1)
        qa_agent_for_node = create_openai_tools_agent(llm_qa, qa_tools, qa_agent_prompt)
        qa_agent_executor_for_node = AgentExecutor(agent=qa_agent_for_node, tools=qa_tools, verbose=False, handle_parsing_errors="Always죄송합니다. 에이전트가 오류를 반환했습니다.", return_intermediate_steps=True)
        
        qa_response = qa_agent_executor_for_node.invoke(agent_input)
        logger.debug(f"QA Agent Raw Response from AgentExecutor: {qa_response}")

        if "intermediate_steps" in qa_response and qa_response["intermediate_steps"]:
            for action, observation in qa_response["intermediate_steps"]:
                tool_name = action.tool if hasattr(action, 'tool') else "UnknownTool"
                tool_input_args = action.tool_input if hasattr(action, 'tool_input') else {}
                logger.info(f"[MCP Shim] Received Request: Tool='{tool_name}', Args={tool_input_args}")
                logger.info(f"[MCP Shim] Executed Tool='{tool_name}', Result={observation}")
                if isinstance(observation, dict) and tool_name == "code_tester_tool":
                    test_status_from_agent = observation.get("status", "tool_error")
                    test_message_from_agent = observation.get("message", "Tool output format error from MCP Shim.")
        elif "output" in qa_response: 
            logger.warning(f"QA Agent did not use a tool as expected. Final output: {qa_response.get('output')}")
            test_message_from_agent = str(qa_response.get("output", test_message_from_agent))
            # test_status_from_agent remains 'tool_error' as tool wasn't used
        else:
            logger.error("QA Agent response missing 'intermediate_steps' and 'output'. Cannot determine test result.")
            # test_message_from_agent might contain parsing error if handle_parsing_errors was a string
            if isinstance(qa_response.get("output"), str) and "죄송합니다. 에이전트가 오류를 반환했습니다." in qa_response.get("output"):
                test_message_from_agent = "QA Agent encountered an internal parsing or execution error."


    except Exception as e: 
        logger.error(f"QA agent execution error: {e}", exc_info=True)
        test_status_from_agent = "tool_error"; test_message_from_agent = f"QA agent encountered an error: {e}"
        
    logger.info(f"QA Final Test Status: {test_status_from_agent}, Message: {test_message_from_agent}. Exiting QA Node.")
    return {**state, "test_status": test_status_from_agent, "test_message": test_message_from_agent, 
            "current_error": None, "qa_agent_messages": [], "validation_status": None, "validation_issues": [],
            "packaged_artifacts_info": None, "handoff_summary": None }

def artifact_packaging_node(state: GraphState) -> GraphState:
    logger.info("Entering Artifact Packaging Node")
    generated_code = state["generated_code"]; task_desc = state["task_description"]; planner_notes = state["planner_notes"]; function_name = state["current_test_case"]["function_name"]
    if not generated_code: logger.error("Packaging: No code."); return {**state, "current_error": "Packaging: No code."}
    try:
        run_timestamp = time.strftime("%Y%m%d-%H%M%S"); package_dir = ARTIFACTS_BASE_DIR / f"run_{run_timestamp}" / function_name
        package_dir.mkdir(parents=True, exist_ok=True)
        code_file_path = package_dir / f"{function_name}.py"; readme_file_path = package_dir / "README.md"
        with open(code_file_path, "w", encoding="utf-8") as f: f.write(generated_code)
        logger.info(f"Saved code to: {code_file_path}")
        readme_content = f"# Artifacts for: {function_name}\n\n## Task Description (from Planner):\n{task_desc}\n\n"
        if planner_notes: readme_content += f"## Planner Notes:\n{planner_notes}\n\n"
        readme_content += "## Status:\nSuccessfully generated, tested, and validated.\n"
        with open(readme_file_path, "w", encoding="utf-8") as f: f.write(readme_content)
        logger.info(f"Saved README to: {readme_file_path}")
        packaged_info = {"package_directory": str(package_dir), 
                         "code_file": str(code_file_path.relative_to(ARTIFACTS_BASE_DIR.parent)), 
                         "readme_file": str(readme_file_path.relative_to(ARTIFACTS_BASE_DIR.parent))}
        logger.info("Artifacts packaged successfully. Exiting Packaging Node.")
        return {**state, "packaged_artifacts_info": packaged_info, "current_error": None}
    except Exception as e: logger.error(f"Artifact packaging error: {e}", exc_info=True); return {**state, "current_error": f"Packaging Error: {e}"}

def handoff_node(state: GraphState) -> GraphState:
    logger.info("Entering Handoff Node")
    packaged_info = state["packaged_artifacts_info"]; task_desc = state["task_description"]
    if not packaged_info: 
        summary = f"Handoff for '{task_desc[:50]}...': Failed, no packaged artifacts information found."
        logger.error(summary); return {**state, "handoff_summary": summary, "current_error": "Handoff: No artifact info."}
    summary = (f"Project '{task_desc[:50]}...' completed successfully!\n"
               f"  Artifacts packaged in directory: {packaged_info.get('package_directory')}\n"
               f"  - Code File: {packaged_info.get('code_file')}\n"
               f"  - README File: {packaged_info.get('readme_file')}\n"
               "Ready for human review and deployment.")
    logger.info(f"Handoff Summary:\n{summary}\nExiting Handoff Node.")
    print("\n-------------------- HANDOFF SUMMARY --------------------")
    print(summary)
    print("-------------------------------------------------------\n")
    return {**state, "handoff_summary": summary, "current_error": None}


# --- 6. Define Conditional Edge Logic ---
def decide_after_architect(state: GraphState) -> Literal["planner_agent_node", "__end__"]:
    logger.info("Router: Decide After Architect")
    if state.get("current_error") and "Architect Error" in state.get("current_error", ""):
        logger.error(f"Critical Architect Error: {state['current_error']}. Ending workflow.")
        return END
    if state.get("architectural_decision") and state["architectural_decision"].get("chosen_language"):
        logger.info("Architect provided a decision. Proceeding to Planner.")
        return "planner_agent_node"
    else: # Should be caught by current_error but as a fallback
        logger.error("Architect failed to make a decision or decision was invalid. Ending workflow.")
        current_err = state.get("current_error","") + " Architect decision invalid/missing."
        # Ensure current_error is updated in state for final reporting if this path is taken
        # This conditional router doesn't modify state, but the node itself should have set current_error.
        # For robustness in demo, if state.current_error is not set but we end here, log it.
        if not state.get("current_error"): logger.error(current_err)
        return END

def decide_after_planner(state: GraphState) -> Literal["human_interaction_node", "developer_agent_node", "__end__"]:
    logger.info("Router: Decide After Planner")
    if state.get("current_error") and "Planner Error" in state.get("current_error", ""): 
        logger.error(f"Critical Planner Error: {state['current_error']}. Ending."); return END
    
    questions = state.get("clarification_questions_for_user")
    planner_iters = state.get("planner_iteration_count", 0)
    max_planner_iters = state.get("max_planner_iterations", 2)

    if questions and planner_iters < max_planner_iters: 
        logger.info("Planner needs clarification from human."); return "human_interaction_node"
    elif questions and planner_iters >= max_planner_iters: 
        logger.warning(f"Max planner iterations ({max_planner_iters}) reached. Planner still has questions. Ending with planner failure.")
        # The planner node itself should set current_error if it fails to plan after max iterations.
        # This router just directs based on questions. If questions are still there, it implies failure.
        return END # Assume planner node has set current_error appropriately
    elif state.get("planned_task_description"): 
        logger.info("Planner provided a task description. Proceeding to Developer.")
        return "developer_agent_node"
    else: 
        logger.error("Planner did not produce a plan or questions, and no specific error state set by planner. Ending due to planner inaction.")
        # This is a fallback for unexpected planner state.
        return END

def decide_after_qa(state: GraphState) -> Literal["validation_agent_node", "critique_agent_node", "developer_agent_node", "__end__"]:
    logger.info("Router: Decide After QA")
    test_status = state["test_status"]; ref_count = state["refinement_count"]; max_ref = state["max_refinements"]
    
    # Upstream errors (Architect, Planner) should ideally end the graph before QA.
    # If current_error is set by an upstream node and not cleared, it implies a critical failure.
    if state.get("current_error") and ("Architect Error" in state.get("current_error","") or "Planner Error" in state.get("current_error","")):
        logger.error(f"Propagated Upstream Error at QA stage: {state['current_error']}. Ending."); return END

    if test_status == "success": 
        logger.info("QA: Functional tests PASSED. Proceeding to Validation Agent."); return "validation_agent_node"
    
    # Handle tool errors from developer or QA itself
    if test_status == "tool_error":
        # If developer itself failed to produce code or had an internal tool error passed as current_error
        # The developer_agent_node is expected to set current_error if it has an internal issue like failing to parse LLM output.
        if state.get("current_error") and ("Developer agent" in state.get("current_error","") or "No parsable code" in state.get("current_error","")):
            logger.warning(f"QA: Developer tool error detected ('{state['current_error']}'). Retrying developer if attempts left ({ref_count}/{max_ref})."); 
            return "developer_agent_node" if ref_count < max_ref else END
        # Otherwise, assume it's a QA agent's tool error or unhandled scenario from QA
        logger.warning(f"QA: QA tool error ('{state.get('test_message', 'Unknown')}'). Proceeding to critique if attempts left ({ref_count}/{max_ref})."); 
        return "critique_agent_node" if ref_count < max_ref else END
            
    # Functional test failed (not a tool error)
    logger.info(f"QA: Functional tests FAILED ('{state.get('test_message')}'). Proceeding to critique if attempts left ({ref_count}/{max_ref})."); 
    return "critique_agent_node" if ref_count < max_ref else END

def decide_after_validation(state: GraphState) -> Literal["artifact_packaging_node", "critique_agent_node", "__end__"]:
    logger.info("Router: Decide After Validation")
    validation_status = state["validation_status"]; ref_count = state["refinement_count"]; max_ref = state["max_refinements"]
    if validation_status == "pass": 
        logger.info("Validation PASSED. Proceeding to Artifact Packaging."); return "artifact_packaging_node"
    elif validation_status == "error": 
        logger.error(f"Validation agent ERROR: {state.get('validation_issues', ['Unknown validation error'])}. Ending."); return END
    else: # Validation failed
        logger.info(f"Validation FAILED. Issues: {state.get('validation_issues')}. Proceeding to critique if attempts left ({ref_count}/{max_ref})."); 
        return "critique_agent_node" if ref_count < max_ref else END

def decide_after_packaging(state: GraphState) -> Literal["handoff_node", "__end__"]:
    logger.info("Router: Decide After Packaging")
    if state.get("current_error") and "Packaging Error" in state.get("current_error", ""):
        logger.error(f"Error during packaging: {state['current_error']}. Ending workflow with failure."); return END
    elif state.get("packaged_artifacts_info"):
        logger.info("Artifacts packaged successfully. Proceeding to Handoff."); return "handoff_node"
    else: 
        logger.error("Unknown state after packaging (no error, no artifacts). Ending."); return END

# --- 7. Assemble the Graph ---
def build_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("architect_agent_node", architect_agent_node)
    workflow.add_node("planner_agent_node", planner_agent_node)
    workflow.add_node("human_interaction_node", human_interaction_node)
    workflow.add_node("developer_agent_node", developer_agent_node)
    workflow.add_node("qa_agent_node", qa_agent_node)
    workflow.add_node("validation_agent_node", validation_agent_node)
    workflow.add_node("critique_agent_node", critique_agent_node)
    workflow.add_node("artifact_packaging_node", artifact_packaging_node)
    workflow.add_node("handoff_node", handoff_node)

    workflow.set_entry_point("architect_agent_node")
    workflow.add_conditional_edges("architect_agent_node", decide_after_architect, 
                                   {"planner_agent_node": "planner_agent_node", END: END})
    workflow.add_conditional_edges("planner_agent_node", decide_after_planner, 
                                   {"human_interaction_node": "human_interaction_node", "developer_agent_node": "developer_agent_node", END: END})
    workflow.add_edge("human_interaction_node", "planner_agent_node")
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

# --- 8. Main Execution / Demo Test ---
def run_demo(cleanup_artifacts=True):
    logger.info("🚀 Starting Autonomous Code Generation Demo (with Architect Agent) 🚀")
    
    if cleanup_artifacts and ARTIFACTS_BASE_DIR.exists():
        logger.info(f"Cleaning up previous artifacts in {ARTIFACTS_BASE_DIR}...")
        shutil.rmtree(ARTIFACTS_BASE_DIR)
    ARTIFACTS_BASE_DIR.mkdir(parents=True, exist_ok=True)

    if architect_rag_query_engine_global is None: initialize_rag_engines() # Ensures all RAGs are attempted
    if not os.getenv("OPENAI_API_KEY"): logger.warning("OPENAI_API_KEY not found in environment. LLM calls may fail or use mocks.")

    max_refinements_env = int(os.getenv("MAX_REFINEMENTS", "3"))
    max_planner_iterations_env = int(os.getenv("MAX_PLANNER_ITERATIONS", "2"))
    default_llm_models = {
        "architect_llm":  os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o-mini"),
        "planner_llm":    os.getenv("PLANNER_LLM_MODEL", "gpt-4o-mini"),
        "developer_llm":  os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo-instruct"), # Cheaper for code gen
        "qa_llm":         os.getenv("QA_LLM_MODEL", "gpt-4o-mini"), # Good for tool use
        "validation_llm": os.getenv("VALIDATION_LLM_MODEL", "gpt-3.5-turbo"), # Simpler checklist
        "critique_llm":   os.getenv("CRITIQUE_LLM_MODEL", "gpt-4o-mini")  # Good reasoning
    }
    logger.info(f"Using LLM Configuration: {default_llm_models}")
    logger.info(f"Max Developer Refinements: {max_refinements_env}, Max Planner Iterations: {max_planner_iterations_env}")

    # initial_user_req = "I need a Python function to add two integers. Make sure it's clearly defined, uses type hints, and has a docstring."
    initial_user_req = "Can you make a python function? It should be for greeting people. Needs good docs." # More ambiguous

    initial_state: GraphState = {
        "initial_user_request": initial_user_req,
        "architectural_decision": None,
        "clarified_user_input": None, "clarification_questions_for_user": None,
        "planner_iteration_count": 0, "max_planner_iterations": max_planner_iterations_env,
        "llm_models_config": default_llm_models,
        "task_description": "", "planned_task_description": None, "planner_notes": None,
        # Test case might need to be adapted by HITL or be more generic if planner has more freedom
        "current_test_case": {"function_name": "greet_user", "inputs": ("Alice",), "expected_output": "Hello, Alice!"},
        "generated_code": None, "test_status": None, "test_message": None, "critique": None,
        "validation_status": None, "validation_issues": [],
        "packaged_artifacts_info": None, "handoff_summary": None,
        "feedback_history": [], "refinement_count": 0, "max_refinements": max_refinements_env,
        "current_error": None, "qa_agent_messages": []
    }
    app = build_graph()
    logger.info("Invoking the graph...")
    final_state = app.invoke(initial_state)
    
    logger.info("🏁 Demo Finished. Final State (Key Fields): 🏁")
    for key, value in final_state.items():
        if key in ["generated_code", "architectural_decision", "planned_task_description", 
                   "planner_notes", "critique", "handoff_summary", "clarified_user_input", 
                   "packaged_artifacts_info", "validation_issues", "feedback_history", "current_error"] and value:
             logger.info(f"  {key}: {value}")
        elif key not in ["qa_agent_messages", "llm_models_config"] and value is not None : # Avoid logging long lists or static configs unless necessary
             logger.debug(f"  {key}: {value}")


    logger.info("--- End-to-End Demo Test Verification ---")
    final_success = (final_state.get("test_status") == "success" and
                     final_state.get("validation_status") == "pass" and
                     final_state.get("packaged_artifacts_info") is not None and
                     final_state.get("handoff_summary") is not None and
                     not final_state.get("current_error")) # Ensure no lingering error at the end
    
    if final_success: 
        logger.info(f"✅ PASSED: Full pipeline successful. Handoff: {final_state.get('handoff_summary')}")
        pkg_info = final_state.get("packaged_artifacts_info")
        if pkg_info and pkg_info.get("code_file") and Path(ARTIFACTS_BASE_DIR.parent / pkg_info["code_file"]).exists(): # Check relative path
            logger.info("✅ VERIFIED: Artifact code file was created.")
        else:
            logger.warning("⚠️ WARNING: Artifact code file not found where expected.")
    elif final_state.get("current_error"):
        logger.error(f"❌ FAILED: Pipeline ended with error: {final_state.get('current_error')}")
    else: # Other failure conditions (e.g., max refinements hit without specific error in current_error)
        logger.error(f"❌ FAILED: Pipeline did not complete successfully. Final Test: {final_state.get('test_status')}, Validation: {final_state.get('validation_status')}")
    return final_state

if __name__ == "__main__":
    final_state_output = run_demo(cleanup_artifacts=True)
    logger.info("--- Programmatic Assertions (Architect Agent Demo) ---")
    final_success = (final_state_output.get("test_status") == "success" and
                     final_state_output.get("validation_status") == "pass" and
                     final_state_output.get("packaged_artifacts_info") is not None and
                     final_state_output.get("handoff_summary") is not None and
                     not final_state_output.get("current_error") 
                    )
    acceptable_failure = (
        final_state_output.get("refinement_count",0) >= final_state_output.get("max_refinements",3) or
        final_state_output.get("planner_iteration_count",0) >= final_state_output.get("max_planner_iterations",2) or # Planner maxed out
        (final_state_output.get("current_error") and ("Architect Error" in final_state_output.get("current_error","") or "Planner Error" in final_state_output.get("current_error",""))) or
        (final_state_output.get("validation_status") == "error") or 
        (final_state_output.get("current_error") and "Artifact Packaging Error" in final_state_output.get("current_error","")) 
    )
    assert final_success or acceptable_failure, \
           f"Demo failed unexpectedly. State: { {k:v for k,v in final_state_output.items() if k not in ['feedback_history','qa_agent_messages','llm_models_config']} }"
    logger.info("Programmatic assertions passed.")
