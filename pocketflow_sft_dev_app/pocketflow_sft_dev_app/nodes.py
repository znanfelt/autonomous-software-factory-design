# nodes.py
import logging
import json # Ensure json is imported
from typing import Any, Dict, List, Optional, Tuple

from pocketflow import Node
from utils.call_llm import call_llm
from utils.tools import extract_python_code, code_tester_tool
from utils.prompts import (
    ARCHITECT_PROMPT_TEMPLATE, PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
    PLANNER_CODEGEN_PROMPT_TEMPLATE, DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
    TEST_CASE_DESIGNER_PROMPT_TEMPLATE, VALIDATION_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT_TEMPLATE
)

logger = logging.getLogger(__name__)

class SimpleJsonOutputParser: # Basic parser, can be enhanced
    def parse(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parsing Error in SimpleJsonOutputParser: {e} in text: {text[:200]}...")
            # Return a dict with an error key, so downstream can check state.get("llm_output_error")
            return {"error": f"JSON parsing failed: {e}", "raw_text": text}


class InitialRequestNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Optional[str]:
        logger.info("Entering InitialRequestNode - Prep")
        return shared.get("user_raw_request")

    def exec(self, prep_res: Optional[str]) -> Optional[str]:
        logger.info(f"InitialRequestNode - Executing with: {str(prep_res)[:100]}...")
        # For MVP, just pass through. Could add initial validation here.
        if not prep_res:
            logger.error("InitialRequestNode: No user request provided.")
            return None
        return prep_res

    def post(self, shared: Dict[str, Any], prep_res: Optional[str], exec_res: Optional[str]):
        logger.info("InitialRequestNode - Post")
        if exec_res is None:
            shared["current_error_message"] = "Initial request was empty."
            return "error_encountered" # Or a specific error action

        shared["initial_user_request"] = exec_res
        shared["current_request_for_planner"] = exec_res # Start with raw request for planner
        logger.debug(f"Initial request stored: {exec_res[:100]}...")
        return "default"


class ArchitectPlannerNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering ArchitectPlannerNode - Prep")
        return {
            "current_request": shared.get("current_request_for_planner", ""),
            "architectural_principles_context": shared.get("architectural_principles_context", "N/A"),
            "planning_guidelines_context": shared.get("planning_guidelines_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"ArchitectPlannerNode - Executing with request: {prep_res['current_request'][:100]}...")
        current_request = prep_res["current_request"]
        arch_principles_ctx = prep_res["architectural_principles_context"]
        plan_guidelines_ctx = prep_res["planning_guidelines_context"]
        llm_models_config = prep_res["llm_models_config"]

        # 1. Architect part (simplified for MVP)
        architect_llm_model = llm_models_config.get("architect_llm", "gpt-4o")
        arch_prompt = ARCHITECT_PROMPT_TEMPLATE.format(
            user_request=current_request,
            architectural_principles_context=arch_principles_ctx
        )
        logger.debug(f"Architect Prompt: {arch_prompt[:200]}...")
        arch_response_str = call_llm(messages=[{"role": "user", "content": arch_prompt}], model=architect_llm_model, temperature=0.1)
        arch_decision = SimpleJsonOutputParser().parse(arch_response_str)
        
        if arch_decision.get("error"):
            logger.error(f"Architect LLM error or parsing failed: {arch_decision['error']}")
            return {"error": "Architect LLM failed", "details": arch_decision.get("raw_text", arch_response_str)}

        logger.info(f"Architect decision: {arch_decision}")

        # 2. Planner part (Clarification or Codegen plan)
        planner_llm_model = llm_models_config.get("planner_llm", "gpt-4o")
        
        # Try to get a codegen plan first
        planner_codegen_prompt = PLANNER_CODEGEN_PROMPT_TEMPLATE.format(
            user_request_to_process=current_request, # Use the potentially clarified request
            planning_guidelines_context=plan_guidelines_ctx,
            chosen_language=arch_decision.get("chosen_language", "python"),
            framework_hint=arch_decision.get("framework_hint", "standard_library"),
            architect_notes=arch_decision.get("high_level_notes", "N/A")
        )
        logger.debug(f"Planner Codegen Prompt: {planner_codegen_prompt[:300]}...")
        planner_response_str = call_llm(messages=[{"role": "user", "content": planner_codegen_prompt}], model=planner_llm_model, temperature=0.2)
        planned_output = SimpleJsonOutputParser().parse(planner_response_str)

        if planned_output.get("error"):
            logger.error(f"Planner Codegen LLM error or parsing failed: {planned_output['error']}")
            # Fallback or re-attempt clarification if direct planning fails due to parsing
            return {"error": "Planner Codegen LLM failed", "details": planned_output.get("raw_text", planner_response_str), "architect_decision": arch_decision}

        # Check if the planner thinks it's clear (empty clarification_questions)
        if planned_output.get("planned_task_description") and not planned_output.get("clarification_questions"):
            logger.info(f"Planner created task description: {str(planned_output['planned_task_description'])[:100]}...")
            return {"architect_decision": arch_decision, "planned_output": planned_output, "needs_clarification": False}

        # If not clear, or if planned_task_description is missing, try asking for clarification questions
        logger.info("Planner determined request needs clarification or codegen plan was insufficient. Asking clarification questions.")
        planner_clar_prompt = PLANNER_CLARIFICATION_PROMPT_TEMPLATE.format(
             user_request_to_process=current_request,
             planning_guidelines_context=plan_guidelines_ctx,
             chosen_language=arch_decision.get("chosen_language", "python"),
             framework_hint=arch_decision.get("framework_hint", "standard_library"),
             architect_notes=arch_decision.get("high_level_notes", "N/A")
        )
        logger.debug(f"Planner Clarification Prompt: {planner_clar_prompt[:300]}...")
        clar_response_str = call_llm(messages=[{"role": "user", "content": planner_clar_prompt}], model=planner_llm_model, temperature=0.3)
        clar_output = SimpleJsonOutputParser().parse(clar_response_str)
        
        if clar_output.get("error"):
            logger.error(f"Planner Clarification LLM error or parsing failed: {clar_output['error']}")
            return {"error": "Planner Clarification LLM failed", "details": clar_output.get("raw_text", clar_response_str), "architect_decision": arch_decision}
            
        logger.info(f"Planner generated clarification questions: {clar_output.get('clarification_questions')}")
        return {"architect_decision": arch_decision, "planned_output": clar_output, "needs_clarification": True}


    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        logger.info("ArchitectPlannerNode - Post")
        shared["planner_iteration_count"] = shared.get("planner_iteration_count", 0) + 1

        if exec_res.get("error"):
            shared["current_error_message"] = f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            logger.error(f"ArchitectPlannerNode error: {shared['current_error_message']}")
            return "error_encountered" # Or a specific error action

        shared["architectural_decision"] = exec_res["architect_decision"]
        planned_output = exec_res["planned_output"]
        
        if exec_res["needs_clarification"] and planned_output.get("clarification_questions"):
            shared["clarification_questions_for_user"] = planned_output["clarification_questions"]
            shared["planned_task_description"] = None # Clear any previous plan
            shared["planner_notes"] = None
            logger.debug("Returning 'clarification_needed'")
            return "clarification_needed"
        elif planned_output.get("planned_task_description"):
            shared["planned_task_description"] = planned_output["planned_task_description"]
            shared["planner_notes"] = planned_output.get("planner_notes")
            shared["task_description"] = str(planned_output["planned_task_description"]) # Ensure it's a string for dev
            shared["clarification_questions_for_user"] = None # Clear questions
            logger.debug("Returning 'plan_ready_for_code'")
            return "plan_ready_for_code"
        else:
            # Should not happen if LLM adheres to one of the two outputs.
            error_msg = "Planner failed to produce a plan or clarification questions."
            logger.error(error_msg + f" LLM output: {planned_output}")
            shared["current_error_message"] = error_msg
            return "error_encountered"


class DeveloperNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering DeveloperNode - Prep")
        return {
            "task_description": shared.get("task_description", ""),
            "planner_notes": shared.get("planner_notes", ""),
            "coding_standards_context": shared.get("coding_standards_context", "N/A"),
            "critique_feedback": shared.get("critique_feedback", "N/A (first attempt or no critique)"),
            "feedback_history": "\n".join([f"- {item}" for item in shared.get("feedback_history", [])]) or "No prior feedback.",
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[str]:
        logger.info(f"DeveloperNode - Executing with task: {str(prep_res['task_description'])[:100]}...")
        llm_model = prep_res["llm_models_config"].get("developer_llm", "gpt-4o")
        
        dev_prompt = DEVELOPER_CODEGEN_PROMPT_TEMPLATE.format(
            developer_task_description=prep_res["task_description"],
            developer_notes=prep_res["planner_notes"],
            coding_standards_context=prep_res["coding_standards_context"],
            critique_message=prep_res["critique_feedback"],
            full_feedback_history=prep_res["feedback_history"]
        )
        logger.debug(f"Developer Prompt: {dev_prompt[:300]}...")
        llm_response_str = call_llm(messages=[{"role": "user", "content": dev_prompt}], model=llm_model, temperature=0.1)
        # The LLM for code gen might not return JSON, so we don't parse it with SimpleJsonOutputParser here.
        # extract_python_code will handle the markdown.
        
        code = extract_python_code(llm_response_str)
        if not code:
            logger.error(f"DeveloperNode: Could not extract Python code. LLM response: {llm_response_str[:200]}...")
            return f"Error: No code block found.\nLLM_Response:\n{llm_response_str}" # Return error string
        return code

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[str]):
        logger.info("DeveloperNode - Post")
        shared["refinement_count"] = shared.get("refinement_count", 0) + 1

        if exec_res and "Error: No code block found" in exec_res:
            shared["current_error_message"] = exec_res
            shared["generated_code"] = None # Ensure no old code persists
            # Add to feedback history to inform next critique/dev attempt
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"DevAttempt {shared['refinement_count']}: Failed to generate code. {exec_res}")
            logger.error(f"DeveloperNode error: {exec_res}")
            return "code_generation_failed"
        
        shared["generated_code"] = exec_res
        logger.debug(f"Generated code (attempt {shared['refinement_count']}):\n{exec_res}")
        # Reset critique after new code is generated
        shared["critique_feedback"] = None 
        shared["current_error_message"] = None
        return "code_ready_for_tests"

class TestCaseDesignerNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering TestCaseDesignerNode - Prep")
        return {
            "planned_task_description": shared.get("planned_task_description"), # This is the structured JSON plan
            "planner_notes": shared.get("planner_notes", ""),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        plan_desc = prep_res["planned_task_description"]
        if not plan_desc or not isinstance(plan_desc, dict):
            logger.error(f"TestCaseDesignerNode: Invalid or missing planned_task_description: {plan_desc}")
            return {"error": "Invalid plan for test case design"}

        # Serialize the plan_desc dict to a JSON string for the prompt
        function_plan_json_str = json.dumps(plan_desc, indent=2)
        logger.info(f"TestCaseDesignerNode - Executing with plan: {function_plan_json_str[:200]}...")
        
        llm_model = prep_res["llm_models_config"].get("developer_llm", "gpt-4o") # Using dev model for this too

        test_case_prompt = TEST_CASE_DESIGNER_PROMPT_TEMPLATE.format(
            function_plan_json_str=function_plan_json_str,
            planner_notes=prep_res["planner_notes"]
        )
        logger.debug(f"TestCaseDesigner Prompt: {test_case_prompt[:300]}...")
        response_str = call_llm(messages=[{"role": "user", "content": test_case_prompt}], model=llm_model, temperature=0.4)
        response_json = SimpleJsonOutputParser().parse(response_str)

        if response_json.get("error"):
            logger.error(f"TestCaseDesigner LLM error or parsing failed: {response_json['error']}")
            return {"error": "Test Case Designer LLM failed", "details": response_json.get("raw_text", response_str)}

        test_cases = response_json.get("test_cases")
        if not test_cases or not isinstance(test_cases, list):
            logger.error(f"TestCaseDesignerNode: 'test_cases' key missing or not a list in LLM response: {response_json}")
            return {"error": "LLM did not return a valid list of test cases"}
        
        # Basic validation of test case structure
        valid_test_cases = []
        for tc in test_cases:
            if isinstance(tc, dict) and "inputs" in tc and "expected_output" in tc and "description" in tc:
                # Ensure inputs is a tuple
                if isinstance(tc["inputs"], list): 
                    tc["inputs"] = tuple(tc["inputs"]) 
                elif not isinstance(tc["inputs"], tuple): # if it's a single non-list/tuple item, wrap in tuple
                    tc["inputs"] = (tc["inputs"],)

                # Ensure function_name is present, deriving from plan if missing
                if "function_name" not in tc or not tc["function_name"]:
                    tc["function_name"] = plan_desc.get("function_name", "unknown_function")
                valid_test_cases.append(tc)
            else:
                logger.warning(f"Skipping malformed test case from LLM: {tc}")
        
        if not valid_test_cases:
            logger.error("TestCaseDesignerNode: No valid test cases generated by LLM.")
            return {"error": "No valid test cases generated"}
            
        return valid_test_cases

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[List[Dict[str, Any]]]):
        logger.info("TestCaseDesignerNode - Post")
        if isinstance(exec_res, dict) and exec_res.get("error"):
            shared["current_error_message"] = f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            shared["generated_test_cases"] = []
            logger.error(f"TestCaseDesignerNode error: {shared['current_error_message']}")
            return "error_encountered"

        shared["generated_test_cases"] = exec_res
        shared["current_test_case_index"] = 0
        shared["all_tests_passed"] = False # Reset for new set of tests
        shared["test_results_summary"] = [] # Reset summary
        logger.debug(f"Generated test cases: {exec_res}")
        return "tests_ready"


class QANode(Node):
    def prep(self, shared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger.info("Entering QANode - Prep")
        code = shared.get("generated_code")
        test_cases = shared.get("generated_test_cases")
        current_idx = shared.get("current_test_case_index", 0)

        if not code:
            logger.error("QANode: No generated code to test.")
            return {"error": "No code to test"}
        if not test_cases or current_idx >= len(test_cases):
            logger.info("QANode: No more test cases to run or test cases not generated.")
            return {"error": "No more tests or tests not found"}
        
        current_test_case = test_cases[current_idx]
        # Extract function name from the current test case or overall plan
        function_name = current_test_case.get("function_name") or \
                        (shared.get("planned_task_description", {}).get("function_name") if isinstance(shared.get("planned_task_description"), dict) else "unknown_function")

        return {
            "code_string": code,
            "function_name": function_name,
            "test_case": current_test_case
        }

    def exec(self, prep_res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not prep_res or prep_res.get("error"):
            logger.error(f"QANode - Exec: Skipping due to prep error: {prep_res.get('error') if prep_res else 'No prep_res'}")
            return {"status": "error", "message": prep_res.get("error") if prep_res else "Prep failed", "test_case": None, "actual_output": None}

        code_string = prep_res["code_string"]
        function_name = prep_res["function_name"]
        test_case = prep_res["test_case"]
        
        logger.info(f"QANode - Executing test: {test_case.get('description', 'N/A')} for function '{function_name}'")
        # code_tester_tool expects a list of test cases, so wrap current_test_case
        single_test_results = code_tester_tool(code_string, function_name, [test_case])
        
        if not single_test_results: # Should always return a list
            logger.error("QANode: code_tester_tool returned empty result.")
            return {"status": "error", "message": "Test tool malfunctioned.", "test_case": test_case, "actual_output": None}
            
        return single_test_results[0] # Return the result for the single test case

    def post(self, shared: Dict[str, Any], prep_res: Optional[Dict[str, Any]], exec_res: Optional[Dict[str, Any]]):
        logger.info("QANode - Post")
        if not exec_res or exec_res.get("status") == "error":
            error_msg = exec_res.get("message", "QA execution failed or was skipped.") if exec_res else "QA prep failed."
            logger.error(f"QANode error: {error_msg}")
            shared["current_test_status"] = "error"
            shared["current_test_message"] = error_msg
            # Potentially add to feedback history to indicate tool/QA setup error
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"QA Attempt {shared.get('refinement_count',0)}: Error during test execution - {error_msg}")
            return "testing_error_or_done" # Or a specific error action

        test_result = exec_res
        shared.setdefault("test_results_summary", []).append(test_result)
        shared["current_test_status"] = test_result["status"]
        shared["current_test_message"] = test_result["message"]
        logger.debug(f"Test result: {test_result['status']} - {test_result['message']}")

        shared["current_test_case_index"] = shared.get("current_test_case_index", 0) + 1
        
        if test_result["status"] != "success":
            shared["all_tests_passed"] = False # Mark as failed if any test fails
            # Add specific failure to feedback history for critique
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"Test Failure (DevAttempt {shared.get('refinement_count',0)} on test '{test_result['test_case'].get('description')}'): {test_result['message']} (Actual: {test_result.get('actual_output')})")
            return "testing_error_or_done" # Go to critique/validation

        if shared["current_test_case_index"] >= len(shared.get("generated_test_cases", [])):
            # All tests for this version have run
            # Check if all passed *in this specific run of tests for the current code version*
            all_current_tests_passed_this_round = all(
                res['status'] == 'success' for res in shared['test_results_summary']
                if res['test_case'] in shared.get("generated_test_cases", []) # Ensure we only check current set
            )
            shared["all_tests_passed"] = all_current_tests_passed_this_round
            logger.info(f"All tests run. Overall pass status for this version: {shared['all_tests_passed']}")
            return "testing_error_or_done" # Go to validation or critique
        else:
            return "run_next_test"


class ValidationNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering ValidationNode - Prep")
        return {
            "generated_code": shared.get("generated_code"),
            "task_description": shared.get("task_description", "N/A"),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "validation_rules_context": shared.get("validation_rules_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        code = prep_res["generated_code"]
        if not code:
            logger.error("ValidationNode: No code to validate.")
            return {"validation_passed": False, "issues_found": ["No code provided for validation."]}

        logger.info(f"ValidationNode - Executing for task: {prep_res['task_description'][:100]}...")
        llm_model = prep_res["llm_models_config"].get("validation_llm", "gpt-4o")

        val_prompt = VALIDATION_PROMPT_TEMPLATE.format(
            task_description=prep_res["task_description"],
            planner_notes=prep_res["planner_notes"],
            code_to_validate=code,
            validation_rules_context=prep_res["validation_rules_context"]
        )
        logger.debug(f"Validation Prompt: {val_prompt[:300]}...")
        response_str = call_llm(messages=[{"role": "user", "content": val_prompt}], model=llm_model, temperature=0.1)
        validation_result = SimpleJsonOutputParser().parse(response_str)
        
        if validation_result.get("error"):
            logger.error(f"Validation LLM error or parsing failed: {validation_result['error']}")
            return {"validation_passed": False, "issues_found": [f"Validation LLM failed: {validation_result['error']}"], "details": validation_result.get("raw_text", response_str)}

        return validation_result

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        logger.info("ValidationNode - Post")
        if isinstance(exec_res, dict) and "validation_passed" in exec_res:
            shared["validation_status"] = "pass" if exec_res["validation_passed"] and not exec_res.get("issues_found") else "fail"
            shared["validation_issues"] = exec_res.get("issues_found", [])
            if not isinstance(shared["validation_issues"], list): # Ensure it's a list
                shared["validation_issues"] = [str(shared["validation_issues"])] if shared["validation_issues"] else []
            if exec_res.get("validation_passed") and shared["validation_issues"]:
                 logger.warning("Validation conflict: LLM said passed but issues were found. Marking as fail.")
                 shared["validation_status"] = "fail"
                 shared["validation_issues"].append("Internal Consistency: LLM reported pass but listed issues.")

        else: # Error case from exec
            shared["validation_status"] = "error"
            shared["validation_issues"] = [str(exec_res.get("details", "Validation agent returned malformed output."))]

        logger.debug(f"Validation status: {shared['validation_status']}, Issues: {shared['validation_issues']}")
        return "validation_done"


class CritiqueNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering CritiqueNode - Prep")
        return {
            "task_description": shared.get("task_description", "N/A"),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "generated_code": shared.get("generated_code", "# No code available"),
            "test_failure_message": shared.get("current_test_message", "N/A (or tests passed/not run)"),
            "validation_issues": shared.get("validation_issues", []),
            "user_rejection_reason": shared.get("user_rejection_reason", "N/A"),
            "debugging_tips_context": shared.get("debugging_tips_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> str:
        logger.info(f"CritiqueNode - Executing...")
        llm_model = prep_res["llm_models_config"].get("critique_llm", "gpt-4o-mini")

        critique_prompt = CRITIQUE_PROMPT_TEMPLATE.format(
            task_description=prep_res["task_description"],
            planner_notes=prep_res["planner_notes"],
            code_in_question=prep_res["generated_code"],
            test_failure_message=prep_res["test_failure_message"],
            validation_issues_list="; ".join(prep_res["validation_issues"]) if prep_res["validation_issues"] else "N/A",
            user_rejection_reason=prep_res["user_rejection_reason"],
            debugging_tips_context=prep_res["debugging_tips_context"]
        )
        logger.debug(f"Critique Prompt: {critique_prompt[:300]}...")
        response_str = call_llm(messages=[{"role": "user", "content": critique_prompt}], model=llm_model, temperature=0.25)
        critique_json = SimpleJsonOutputParser().parse(response_str)

        if critique_json.get("error"):
            logger.error(f"Critique LLM error or parsing failed: {critique_json['error']}")
            return f"Error in critique generation: {critique_json['error']}. Details: {critique_json.get('raw_text', response_str)[:100]}"
            
        feedback = critique_json.get("critique_feedback", "Critique LLM did not provide feedback.")
        return feedback

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: str):
        logger.info("CritiqueNode - Post")
        shared["critique_feedback"] = exec_res
        
        current_feedback_history = shared.get("feedback_history", [])
        # Add latest test/validation results explicitly BEFORE this critique
        # (DeveloperNode will see this full history)
        # This is now handled in QANode and ValidationNode before routing to CritiqueNode
        
        # Add the new critique
        # current_feedback_history.append(f"Critique (DevAttempt {shared.get('refinement_count',0)}): {exec_res}")
        # No, DeveloperNode adds this critique to history after it receives it.
        # CritiqueNode just generates it.

        logger.debug(f"Generated critique: {exec_res}")
        return "refine_code"


class PackageNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering PackageNode - Prep")
        return {
            "generated_code": shared.get("generated_code", "# No final code"),
            "planned_task_description": shared.get("planned_task_description", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, str]:
        logger.info("PackageNode - Executing")
        code = prep_res["generated_code"]
        plan = prep_res["planned_task_description"]
        
        function_name = plan.get("function_name", "unnamed_function") if isinstance(plan, dict) else "unnamed_function"
        
        # Simple packaging: create a string for a Python file and a basic README
        py_file_content = f"# Auto-generated by FlowForge AI (Simple SDLC App)\n\n{code}\n"
        readme_content = f"""# Function: {function_name}

            ## Description
            This function was automatically generated based on the following plan:
            ```json
            {json.dumps(plan, indent=2)}
            Use code with caution.
            Python
            Code
            {code}
            Use code with caution.
            Python
        """
        logger.info(f"Packaging artifacts for function: {function_name}")
        return {
                "code_file_content": py_file_content,
                "readme_content": readme_content,
                "function_name": function_name
                }

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, str]):
        logger.info("PackageNode - Post")
        shared["packaged_artifacts_info"] = exec_res
        shared["handoff_summary"] = f"Successfully generated and packaged function '{exec_res.get('function_name', 'N/A')}'."
        logger.debug(f"Packaged artifacts: {exec_res.get('function_name')}")
        return "done" # End of flow