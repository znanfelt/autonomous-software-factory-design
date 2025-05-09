import logging
from .prompts import architect_prompt_template, planner_prompt_template, dev_code_gen_prompt_template, validation_prompt_template, critique_prompt_template, test_case_designer_prompt_template, qa_agent_prompt
from .state import GraphState
from .rag import architect_rag_query_engine_global, planner_rag_query_engine_global, developer_rag_query_engine_global, validation_rag_query_engine_global, critique_rag_query_engine_global
from .tools import code_tester_tool, extract_python_code
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain.agents import AgentExecutor, create_openai_tools_agent
from typing import Any, List, Dict, Literal
import os

# All agent node functions

def architect_agent_node(state: GraphState) -> GraphState:
    logger = logging.getLogger(__name__)
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
    def get_llm_instance(model_name_key: str, state: GraphState, default_model="gpt-3.5-turbo-0125", temperature=0.2, mock_response="") -> ChatOpenAI:
        model_name = state["llm_models_config"].get(model_name_key, default_model)
        logger.debug(f"Initializing LLM for '{model_name_key}' with model '{model_name}'.")
        try: return ChatOpenAI(model=model_name, temperature=temperature)
        except Exception as e:
            logger.error(f"LLM init error for {model_name_key} ({model_name}): {e}. Using mock.", exc_info=True)
            class MockLLM:
                def invoke(self, *args, **kwargs):
                    logger.warning(f"MockLLM invoked for {model_name_key}"); return mock_response
            return MockLLM() # type: ignore
    llm_architect = get_llm_instance("architect_llm", state, temperature=0.2, mock_response='{"chosen_language": "python", "framework_hint": "standard_library", "high_level_notes": "Focus on a clear, single Python function for this MVP."}')
    architect_chain_instance = architect_prompt_template | llm_architect | StrOutputParser()
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
            "planner_iteration_count": 0, "generated_code": None, "current_test_status": None, "critique": None,
            "validation_status": None, "packaged_artifacts_info": None, "handoff_summary": None,
            "feedback_history": [], "refinement_count": 0
        }
    else:
        error_msg = f"Architect Error: Invalid output format or missing key fields from LLM. Output: {arch_decision_json}"
        logger.error(error_msg)
        return {**state, "architectural_decision": None, "current_error": error_msg}

def planner_agent_node(state):
    logger = logging.getLogger(__name__)
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
        try:
            response = planner_rag_query_engine_global.query(f"Planning guidelines for a '{arch_decision.get('chosen_language')}' task using '{arch_decision.get('framework_hint')}'.")
            planning_context = str(response)
        except Exception as e:
            logger.warning(f"RAG error (planner): {e}"); planning_context = f"RAG error (planner): {e}"
    def get_llm_instance(model_name_key: str, state, default_model="gpt-3.5-turbo-0125", temperature=0.3, mock_response=""):
        from langchain_openai import ChatOpenAI
        model_name = state["llm_models_config"].get(model_name_key, default_model)
        logger.debug(f"Initializing LLM for '{model_name_key}' with model '{model_name}'.")
        try: return ChatOpenAI(model=model_name, temperature=temperature)
        except Exception as e:
            logger.error(f"LLM init error for {model_name_key} ({model_name}): {e}. Using mock.", exc_info=True)
            class MockLLM:
                def invoke(self, *args, **kwargs):
                    logger.warning(f"MockLLM invoked for {model_name_key}"); return mock_response
            return MockLLM() # type: ignore
    llm_planner = get_llm_instance("planner_llm", state, temperature=0.3, mock_response='{"clarification_questions": [], "planned_task_description": "Mock plan for greet function", "planner_notes": "Mock notes: Ensure docstring for greet function."}')
    planner_chain_instance = planner_prompt_template | llm_planner | StrOutputParser()
    planned_output_json = planner_chain_instance.invoke({
        "user_request_to_process": current_request_to_process,
        "planning_guidelines_context": planning_context,
        "chosen_language": arch_decision.get("chosen_language", "python"),
        "framework_hint": arch_decision.get("framework_hint", "standard_library"),
        "architect_notes": arch_decision.get("high_level_notes", "None")
    })
    logger.debug(f"Planner LLM Raw Output (parsed): {planned_output_json}")
    new_planner_iteration_count = state["planner_iteration_count"] + 1
    questions_for_user = []
    planned_task_desc = None
    planner_notes_str = None
    current_error_for_state = None
    if isinstance(planned_output_json, dict) and not planned_output_json.get("error"):
        questions_for_user = planned_output_json.get("clarification_questions", [])
        if not isinstance(questions_for_user, list):
            questions_for_user = []
        if not questions_for_user:
            planned_task_desc = planned_output_json.get("planned_task_description")
            planner_notes_str = planned_output_json.get("planner_notes")
            if not planned_task_desc:
                current_error_for_state = "Planner Error: No plan provided and no clarification questions asked by LLM."
        else:
            logger.info(f"Planner generated clarification questions: {questions_for_user}")
    else:
        current_error_for_state = f"Planner Error: Invalid output format from LLM or parsing error. Output: {planned_output_json}"
    logger.info(f"Exiting Planner Node. Questions asked: {bool(questions_for_user)}. Plan generated: {bool(planned_task_desc)}")
    return {
        **state, "planned_task_description": planned_task_desc,
        "task_description": planned_task_desc if planned_task_desc else state.get("task_description",""),
        "planner_notes": planner_notes_str,
        "clarification_questions_for_user": questions_for_user if questions_for_user else None,
        "clarified_user_input": None, "planner_iteration_count": new_planner_iteration_count, "current_error": current_error_for_state,
        "critique": None, "validation_status": None, "validation_issues": [], "packaged_artifacts_info": None, "handoff_summary": None,
        "generated_code": None, "current_test_status": None, "current_test_message": None,
        "feedback_history": [] if new_planner_iteration_count == 1 else state.get("feedback_history",[]),
        "refinement_count": 0 if new_planner_iteration_count == 1 else state.get("refinement_count",0)
    }

def developer_agent_node(state):
    logger = logging.getLogger(__name__)
    logger.info("Entering Developer Node")
    dev_task_description = state["task_description"]
    dev_notes = state["planner_notes"]
    latest_critique = state.get("critique", "No specific critique. Focus on initial implementation or previous test/validation feedback if any.")
    full_feedback_history_list = state.get("feedback_history", [])
    refinement_count = state["refinement_count"]
    if not dev_task_description or "Error:" in dev_task_description:
        logger.error(f"Developer received invalid task from planner: {dev_task_description}")
        return {**state, "generated_code": None, "current_test_status": "tool_error", "current_error": dev_task_description, "refinement_count": refinement_count + 1}
    logger.debug(f"Developer task: {str(dev_task_description)[:100]}..., Critique: {str(latest_critique)[:100]}...")
    coding_standards_context = "No coding standards RAG context available."
    if developer_rag_query_engine_global:
        try:
            response = developer_rag_query_engine_global.query(f"Coding standards for: {dev_task_description}")
            coding_standards_context = str(response)
        except Exception as e:
            logger.warning(f"RAG error (developer): {e}"); coding_standards_context = f"RAG error (developer): {e}"
    def get_llm_instance(model_name_key: str, state, mock_response=""):
        from langchain_openai import ChatOpenAI
        model_name = state["llm_models_config"].get(model_name_key, "gpt-3.5-turbo")
        try: return ChatOpenAI(model=model_name, temperature=0.2)
        except Exception as e:
            logger.error(f"LLM init error for {model_name_key} ({model_name}): {e}. Using mock.", exc_info=True)
            class MockLLM:
                def invoke(self, *args, **kwargs):
                    logger.warning(f"MockLLM invoked for {model_name_key}"); return mock_response
            return MockLLM() # type: ignore
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
        updated_feedback_history = list(state.get("feedback_history", []))
        updated_feedback_history.append(f"DevAttempt {current_attempt_count}: Failed to generate parsable code. LLM raw output snippet: '{llm_response[:100]}...'")
        return {**state, "generated_code": None, "current_test_status": "tool_error", "current_test_message": error_message,
                "current_error": error_message, "refinement_count": current_attempt_count, "feedback_history": updated_feedback_history}
    logger.info(f"Developer generated code (Attempt {current_attempt_count}). Exiting Developer Node.")
    return {**state, "generated_code": generated_code_str, "refinement_count": current_attempt_count, "current_error": None,
            "critique": None, "validation_status": None, "validation_issues": [], "packaged_artifacts_info": None, "handoff_summary": None}

def qa_agent_node(state):
    logger = logging.getLogger(__name__)
    logger.info("Entering QA Node (Explicit Tool Protocol Logging)")
    generated_code = state["generated_code"]
    task_desc_for_qa = state["task_description"]
    test_case = state["generated_test_cases"][state["current_test_case_index"]]
    if not generated_code:
        logger.error("QA: No code provided by developer.")
        return {**state, "current_test_status": "tool_error", "current_test_message": "No code from dev for QA."}
    logger.debug(f"QA Agent evaluating code for function '{test_case['function_name']}' (Dev Attempt {state['refinement_count']})")
    test_status_from_agent = "tool_error"
    test_message_from_agent = "QA agent did not successfully complete testing or parse results."
    try:
        agent_input = {
            "task_description_for_qa": task_desc_for_qa, "function_name": test_case['function_name'],
            "test_inputs": test_case['inputs'], "expected_output": test_case['expected_output'],
            "generated_code": generated_code, "chat_history": state.get("qa_agent_messages", [])
        }
        def get_llm_instance(model_name_key: str, state, temperature=0.1):
            from langchain_openai import ChatOpenAI
            model_name = state["llm_models_config"].get(model_name_key, "gpt-4o")
            return ChatOpenAI(model=model_name, temperature=temperature)
        llm_qa = get_llm_instance("qa_llm", state, temperature=0.1)
        qa_tools = [code_tester_tool]
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
        else:
            logger.error("QA Agent response missing 'intermediate_steps' and 'output'. Cannot determine test result.")
            if isinstance(qa_response.get("output"), str) and "죄송합니다. 에이전트가 오류를 반환했습니다." in qa_response.get("output"):
                test_message_from_agent = "QA Agent encountered an internal parsing or execution error."
    except Exception as e:
        logger.error(f"QA agent execution error: {e}", exc_info=True)
        test_status_from_agent = "tool_error"; test_message_from_agent = f"QA agent encountered an error: {e}"
    logger.info(f"QA Final Test Status: {test_status_from_agent}, Message: {test_message_from_agent}. Exiting QA Node.")
    return {**state, "current_test_status": test_status_from_agent, "current_test_message": test_message_from_agent,
            "current_error": None, "qa_agent_messages": [], "validation_status": None, "validation_issues": [],
            "packaged_artifacts_info": None, "handoff_summary": None }

def validation_agent_node(state):
    logger = logging.getLogger(__name__)
    logger.info("Entering Validation Node")
    code_to_validate = state["generated_code"]
    task_desc = state["task_description"]
    planner_notes_str = state["planner_notes"]
    if not code_to_validate:
        logger.error("Validation: No code provided.")
        return {**state, "validation_status": "error", "validation_issues": ["No code provided for validation."], "current_error": "Validation: No code."}
    logger.debug(f"Validation agent reviewing code for task: {task_desc[:100]}...")
    validation_rules_context = "No validation rules RAG context available."
    if validation_rag_query_engine_global:
        try:
            response = validation_rag_query_engine_global.query(f"Validation rules for Python code related to task: {task_desc}")
            validation_rules_context = str(response)
        except Exception as e:
            logger.warning(f"RAG error (validation): {e}"); validation_rules_context = f"RAG error (validation): {e}"
    def get_llm_instance(model_name_key: str, state, temperature=0.1, mock_response='{"validation_passed": true, "issues_found": []}'):
        from langchain_openai import ChatOpenAI
        model_name = state["llm_models_config"].get(model_name_key, "gpt-3.5-turbo")
        try: return ChatOpenAI(model=model_name, temperature=temperature)
        except Exception as e:
            logger.error(f"LLM init error for {model_name_key} ({model_name}): {e}. Using mock.", exc_info=True)
            class MockLLM:
                def invoke(self, *args, **kwargs):
                    logger.warning(f"MockLLM invoked for {model_name_key}"); return mock_response
            return MockLLM() # type: ignore
    llm_validation = get_llm_instance("validation_llm", state, temperature=0.1)
    validation_chain_instance = validation_prompt_template | llm_validation | StrOutputParser()
    validation_output_json = validation_chain_instance.invoke({
        "task_description": task_desc, "planner_notes": planner_notes_str or "None",
        "code_to_validate": code_to_validate, "validation_rules_context": validation_rules_context
    })
    logger.debug(f"Validation LLM Raw Output (parsed): {validation_output_json}")
    issues_found = []
    val_passed = False
    val_status: Literal['pass', 'fail', 'error']
    if isinstance(validation_output_json, dict) and not validation_output_json.get("error"):
        val_passed = validation_output_json.get("validation_passed", False)
        issues_found = validation_output_json.get("issues_found", [])
        if not isinstance(issues_found, list): issues_found = [str(issues_found)] if issues_found else []
        val_status = "pass" if val_passed and not issues_found else "fail"
        if val_passed and issues_found:
            val_status = "fail"
            logger.warning("Validation LLM reported pass=true but also listed issues. Overriding to fail.")
            issues_found.append("Internal Consistency: LLM reported pass but listed issues.")
        elif not val_passed and not issues_found:
            issues_found = ["Validation failed but no specific issues were reported by the validation agent."]
    else:
        issues_found = [f"Validation agent did not return expected JSON format or encountered parsing error. Output: {validation_output_json}"]
        val_status = "error"
    logger.info(f"Validation Status: {val_status}, Issues: {issues_found}. Exiting Validation Node.")
    return {**state, "validation_status": val_status, "validation_issues": issues_found if issues_found else [], "current_error": None}

def test_case_designer_node(state):
    logger = logging.getLogger(__name__)
    logger.info("Entering Test Case Designer Node")
    if not state["planned_task_description"]:
        logger.error("Test Case Designer: No planned task description available.")
        return {**state, "current_error": "Cannot design test cases without a task description.", "generated_test_cases": []}
    task_desc = state["planned_task_description"]
    planner_notes = state.get("planner_notes", "")
    def get_llm_instance(model_name_key: str, state, temperature=0.4, mock_response='{"test_cases": [{"function_name": "mock_func", "inputs": [1], "expected_output": 2, "description": "Mock test"}]}'):
        from langchain_openai import ChatOpenAI
        model_name = state["llm_models_config"].get(model_name_key, "gpt-3.5-turbo")
        try: return ChatOpenAI(model=model_name, temperature=temperature)
        except Exception as e:
            logger.error(f"LLM init error for {model_name_key} ({model_name}): {e}. Using mock.", exc_info=True)
            class MockLLM:
                def invoke(self, *args, **kwargs):
                    logger.warning(f"MockLLM invoked for {model_name_key}"); return mock_response
            return MockLLM() # type: ignore
    llm_test_designer = get_llm_instance("developer_llm", state, temperature=0.4)
    from langchain_core.output_parsers import StrOutputParser
    test_designer_chain = test_case_designer_prompt_template | llm_test_designer | StrOutputParser()
    try:
        response_json = test_designer_chain.invoke({
            "function_description": task_desc,
            "planner_notes": planner_notes
        })
        logger.debug(f"Test Case Designer LLM Raw Output (parsed): {response_json}")
        import json
        if isinstance(response_json, str):
            try:
                response_json = json.loads(response_json)
            except Exception:
                pass
        if isinstance(response_json, dict) and "test_cases" in response_json and isinstance(response_json["test_cases"], list):
            generated_test_cases = []
            valid_cases = True
            for tc_data in response_json["test_cases"]:
                if not (isinstance(tc_data, dict) and
                        "function_name" in tc_data and isinstance(tc_data["function_name"], str) and
                        "inputs" in tc_data and isinstance(tc_data["inputs"], (list, tuple)) and
                        "expected_output" in tc_data and
                        "description" in tc_data and isinstance(tc_data["description"], str)
                        ):
                    logger.warning(f"Invalid test case format from LLM: {tc_data}")
                    valid_cases = False; break
                tc_data["inputs"] = tuple(tc_data["inputs"])
                generated_test_cases.append(tc_data)
            if generated_test_cases and valid_cases:
                logger.info(f"Successfully generated {len(generated_test_cases)} test cases.")
                return {
                    **state,
                    "generated_test_cases": generated_test_cases,
                    "current_test_case_index": 0,
                    "all_tests_passed": False,
                    "test_results_summary": [],
                    "current_error": None
                }
            else:
                error_msg = "Test Case Designer LLM did not return valid test cases or list was empty."
                logger.error(error_msg)
                return {**state, "current_error": error_msg, "generated_test_cases": []}
        else:
            error_msg = f"Test Case Designer LLM output error or malformed JSON: {response_json}"
            logger.error(error_msg)
            return {**state, "current_error": error_msg, "generated_test_cases": []}
    except Exception as e:
        logger.error(f"Test Case Designer node error: {e}", exc_info=True)
        return {**state, "current_error": f"Test Case Designer Exception: {e}", "generated_test_cases": []}