import logging
import json 
from typing import Any, Dict, List, Optional, Tuple, TypedDict
import re # Make sure re is imported if SimpleJsonOutputParser uses it (it does)

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

class SimpleJsonOutputParser:
    def parse(self, text: str) -> Any:
        try:
            # Attempt to find JSON within ```json ... ``` or ``` ... ```
            match_md_json = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            match_md_generic = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            
            json_text_to_parse = None
            if match_md_json:
                json_text_to_parse = match_md_json.group(1).strip()
            elif match_md_generic:
                # If generic, try to parse its content, assuming it might be JSON
                json_text_to_parse = match_md_generic.group(1).strip()
            else:
                # If no markdown blocks, try to find a JSON object directly
                match_obj = re.search(r"\{.*\}", text, re.DOTALL)
                if match_obj:
                    json_text_to_parse = match_obj.group(0)
            
            if json_text_to_parse:
                return json.loads(json_text_to_parse)
            else:
                logger.error(f"JSON Parser: No JSON block or object found in text: {text[:200]}...")
                return {"error": "JSON parsing failed: No JSON content found", "raw_text": text}
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parsing Error in SimpleJsonOutputParser: {e} in text: {json_text_to_parse[:200] if json_text_to_parse else text[:200]}...")
            return {"error": f"JSON parsing failed: {e}", "raw_json_text": json_text_to_parse, "original_text": text}
        except Exception as e: # Catch any other parsing related error
            logger.error(f"Unexpected error in SimpleJsonOutputParser: {e} for text: {text[:200]}...")
            return {"error": f"Unexpected parsing error: {e}", "raw_text": text}


class InitialRequestPrepInput(TypedDict):
    user_raw_request: str

class InitialRequestNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Optional[str]:
        logger.info("Entering InitialRequestNode - Prep")
        return shared.get("user_raw_request")

    def exec(self, prep_res: Optional[str]) -> Optional[str]:
        logger.info(f"InitialRequestNode - Executing with: {str(prep_res)[:100]}...")
        if not prep_res:
            logger.error("InitialRequestNode: No user request provided.")
            return None
        return prep_res

    def post(self, shared: Dict[str, Any], prep_res: Optional[str], exec_res: Optional[str]):
        logger.info("InitialRequestNode - Post")
        if exec_res is None:
            shared["current_error_message"] = "Initial request was empty."
            return "error_encountered" 

        shared["initial_user_request"] = exec_res
        shared["current_request_for_planner"] = exec_res 
        logger.debug(f"Initial request stored: {exec_res[:100]}...")
        return "default"


class ArchitectPlannerPrepInput(TypedDict):
    current_request: str
    architectural_principles_context: str
    planning_guidelines_context: str
    llm_models_config: Dict[str, str]

class ArchitectPlannerNode(Node):
    def prep(self, shared: Dict[str, Any]) -> ArchitectPlannerPrepInput:
        logger.info("Entering ArchitectPlannerNode - Prep")
        return {
            "current_request": shared.get("current_request_for_planner", ""),
            "architectural_principles_context": shared.get("architectural_principles_context", "N/A"),
            "planning_guidelines_context": shared.get("planning_guidelines_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: ArchitectPlannerPrepInput) -> Dict[str, Any]:
        logger.info(f"ArchitectPlannerNode - Executing with request: {prep_res['current_request'][:100]}...")
        current_request = prep_res["current_request"]
        arch_principles_ctx = prep_res["architectural_principles_context"]
        plan_guidelines_ctx = prep_res["planning_guidelines_context"]
        llm_models_config = prep_res["llm_models_config"]

        architect_llm_model = llm_models_config.get("architect_llm", "gpt-4o")
        arch_prompt = ARCHITECT_PROMPT_TEMPLATE.format(
            user_request=current_request,
            architectural_principles_context=arch_principles_ctx
        )
        logger.debug(f"Architect Prompt (first 200 chars): {arch_prompt[:200]}...")
        arch_response_str = call_llm(messages=[{"role": "user", "content": arch_prompt}], model=architect_llm_model, temperature=0.1)
        arch_decision = SimpleJsonOutputParser().parse(arch_response_str)
        
        if arch_decision.get("error"):
            logger.error(f"Architect LLM error or parsing failed: {arch_decision['error']}")
            return {"error": "Architect LLM failed", "details": arch_decision.get("raw_text", arch_response_str)}

        logger.info(f"Architect decision: {arch_decision}")

        planner_llm_model = llm_models_config.get("planner_llm", "gpt-4o")
        
        # DEBUGGING: Print template and args before format
        logger.debug(f"DEBUG: PLANNER_CODEGEN_PROMPT_TEMPLATE (first 100 chars):\n{PLANNER_CODEGEN_PROMPT_TEMPLATE[:100]}...")
        format_args_codegen = {
            "user_request_to_process": current_request,
            "planning_guidelines_context": plan_guidelines_ctx,
            "chosen_language": arch_decision.get("chosen_language", "python"),
            "framework_hint": arch_decision.get("framework_hint", "standard_library"),
            "architect_notes": arch_decision.get("high_level_notes", "N/A")
        }
        logger.debug(f"DEBUG: Arguments for PLANNER_CODEGEN_PROMPT_TEMPLATE.format(): {format_args_codegen}")
        
        try:
            planner_codegen_prompt = PLANNER_CODEGEN_PROMPT_TEMPLATE.format(**format_args_codegen)
        except KeyError as e:
            logger.error(f"CRITICAL: KeyError during PLANNER_CODEGEN_PROMPT_TEMPLATE.format(): {e}")
            # Log the exact keys present in the template to see if there's a mismatch
            import re
            template_keys = set(re.findall(r'{([^{}]+)}', PLANNER_CODEGEN_PROMPT_TEMPLATE))
            logger.error(f"Expected keys in template: {template_keys}")
            logger.error(f"Provided keys in args: {set(format_args_codegen.keys())}")
            raise # Re-raise the original error to halt and see this debug info

        logger.debug(f"Planner Codegen Prompt (first 300 chars): {planner_codegen_prompt[:300]}...")
        planner_response_str = call_llm(messages=[{"role": "user", "content": planner_codegen_prompt}], model=planner_llm_model, temperature=0.2)
        planned_output = SimpleJsonOutputParser().parse(planner_response_str)

        if planned_output.get("error"):
            logger.error(f"Planner Codegen LLM error or parsing failed: {planned_output['error']}")
            return {"error": "Planner Codegen LLM failed", "details": planned_output.get("raw_text", planner_response_str), "architect_decision": arch_decision}

        if planned_output.get("planned_task_description") and not planned_output.get("clarification_questions"): # Ensure questions is explicitly empty or not present
            logger.info(f"Planner created task description: {str(planned_output['planned_task_description'])[:100]}...")
            return {"architect_decision": arch_decision, "planned_output": planned_output, "needs_clarification": False}

        logger.info("Planner determined request needs clarification or codegen plan was insufficient. Asking clarification questions.")
        format_args_clarification = {
             "user_request_to_process": current_request,
             "planning_guidelines_context": plan_guidelines_ctx,
             "chosen_language": arch_decision.get("chosen_language", "python"),
             "framework_hint": arch_decision.get("framework_hint", "standard_library"),
             "architect_notes": arch_decision.get("high_level_notes", "N/A")
        }
        planner_clar_prompt = PLANNER_CLARIFICATION_PROMPT_TEMPLATE.format(**format_args_clarification)
        logger.debug(f"Planner Clarification Prompt (first 300 chars): {planner_clar_prompt[:300]}...")
        clar_response_str = call_llm(messages=[{"role": "user", "content": planner_clar_prompt}], model=planner_llm_model, temperature=0.3)
        clar_output = SimpleJsonOutputParser().parse(clar_response_str)
        
        if clar_output.get("error"):
            logger.error(f"Planner Clarification LLM error or parsing failed: {clar_output['error']}")
            return {"error": "Planner Clarification LLM failed", "details": clar_output.get("raw_text", clar_response_str), "architect_decision": arch_decision}
            
        logger.info(f"Planner generated clarification questions: {clar_output.get('clarification_questions')}")
        return {"architect_decision": arch_decision, "planned_output": clar_output, "needs_clarification": True}

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        # (Post method remains the same as previously provided)
        logger.info("ArchitectPlannerNode - Post")
        shared["planner_iteration_count"] = shared.get("planner_iteration_count", 0) + 1

        if exec_res.get("error"):
            shared["current_error_message"] = f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            logger.error(f"ArchitectPlannerNode error: {shared['current_error_message']}")
            return "error_encountered" 

        shared["architectural_decision"] = exec_res["architect_decision"]
        planned_output = exec_res["planned_output"]
        
        if exec_res["needs_clarification"] and planned_output.get("clarification_questions"):
            shared["clarification_questions_for_user"] = planned_output["clarification_questions"]
            shared["planned_task_description"] = None 
            shared["planner_notes"] = None
            logger.debug("Returning 'clarification_needed'")
            return "clarification_needed"
        elif planned_output.get("planned_task_description"):
            shared["planned_task_description"] = planned_output["planned_task_description"]
            shared["planner_notes"] = planned_output.get("planner_notes")
            shared["task_description"] = str(planned_output["planned_task_description"]) 
            shared["clarification_questions_for_user"] = None 
            logger.debug("Returning 'plan_ready_for_code'")
            return "plan_ready_for_code"
        else:
            error_msg = "Planner failed to produce a plan or clarification questions."
            logger.error(error_msg + f" LLM output: {planned_output}")
            shared["current_error_message"] = error_msg
            return "error_encountered"

class DeveloperPrepInput(TypedDict):
    task_description: str
    planner_notes: Optional[str]
    coding_standards_context: str
    critique_feedback: str
    feedback_history: str # This is a joined string
    llm_models_config: Dict[str, str]

class DeveloperNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare input for code generation."""
        developer_task_description = shared.get("developer_task_description")
        if not developer_task_description:
            logger.error("DeveloperNode: Missing developer_task_description in shared state")
            return {"error": "Developer task description missing"}

        return {
            "task_description": developer_task_description,  # Key name matches test expectations
            "planner_notes": shared.get("planner_notes", "N/A"),
            "coding_standards_context": shared.get("coding_standards_context", "N/A"),
            "critique_feedback": shared.get("critique_feedback", "N/A"),
            "feedback_history": shared.get("feedback_history", []),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[str]:
        # First check for prep errors
        if prep_res.get("error"):
            logger.error("DeveloperNode: Error from prep stage: %s", prep_res["error"])
            return f"Error: {prep_res['error']}"

        # Next, try to make the LLM call and check for JSON error response
        if prep_res and prep_res.get("task_description"):  # Changed from developer_task_description
            llm_model = prep_res["llm_models_config"].get("developer_llm", "gpt-4o")
            dev_prompt = DEVELOPER_CODEGEN_PROMPT_TEMPLATE.format(
                developer_task_description=prep_res["task_description"],  # Changed from developer_task_description
                developer_notes=prep_res["planner_notes"],
                coding_standards_context=prep_res["coding_standards_context"],
                critique_message=prep_res["critique_feedback"],
                full_feedback_history=prep_res["feedback_history"]
            )
            llm_response_str = call_llm(
                messages=[{"role": "user", "content": dev_prompt}], 
                model=llm_model, 
                temperature=0.1,
                expect_json=False
            )
            
            # Check if LLM returned a JSON error response
            try:
                potential_error = json.loads(llm_response_str)
                if isinstance(potential_error, dict) and "error" in potential_error:
                    logger.error(f"DeveloperNode: LLM call failed: {potential_error['error']}")
                    return f"Error: LLM call failed.\nDetails: {potential_error['error']}"
            except json.JSONDecodeError:
                # Not JSON, proceed to code extraction
                code = extract_python_code(llm_response_str)
                if not code:
                    logger.error(f"DeveloperNode: Could not extract Python code. LLM response: {llm_response_str[:200]}...")
                    return f"Error: No code block found.\nLLM_Response:\n{llm_response_str}"
                return code

        # If we get here, either prep_res is None or missing required data
        logger.error("DeveloperNode: Missing or invalid task description in prep_res: %s", prep_res)
        return "Error: task description is missing or invalid. Cannot proceed with code generation."

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[str]):
        logger.info("DeveloperNode - Post")
        shared["refinement_count"] = shared.get("refinement_count", 0) + 1

        if exec_res and "Error: No code block found" in exec_res:
            shared["current_error_message"] = exec_res
            shared["generated_code"] = None 
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"DevAttempt {shared['refinement_count']}: Failed to generate code. {exec_res}")
            logger.error(f"DeveloperNode error: {exec_res}")
            return "code_generation_failed"
        
        shared["generated_code"] = exec_res
        logger.debug(f"Generated code (attempt {shared['refinement_count']}):\n{exec_res}")
        shared["critique_feedback"] = None 
        shared["current_error_message"] = None
        return "code_ready_for_tests"

class TestCaseDesignerPrepInput(TypedDict):
    planned_task_description: Dict[str, Any]
    planner_notes: Optional[str]
    llm_models_config: Dict[str, str]

class TestCaseDesignerNode(Node):
    def prep(self, shared: Dict[str, Any]) -> TestCaseDesignerPrepInput:
        logger.info("Entering TestCaseDesignerNode - Prep")
        return {
            "planned_task_description": shared.get("planned_task_description"),
            "planner_notes": shared.get("planner_notes", ""),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: TestCaseDesignerPrepInput) -> Optional[List[Dict[str, Any]]]:
        plan_desc = prep_res["planned_task_description"]
        if not plan_desc or not isinstance(plan_desc, dict):
            logger.error(f"TestCaseDesignerNode: Invalid or missing planned_task_description: {plan_desc}")
            return {"error": "Invalid plan for test case design"}

        function_plan_json_str = json.dumps(plan_desc, indent=2)
        logger.info(f"TestCaseDesignerNode - Executing with plan: {function_plan_json_str[:200]}...")
        
        llm_model = prep_res["llm_models_config"].get("test_designer_llm", "gpt-4o") 

        test_case_prompt = TEST_CASE_DESIGNER_PROMPT_TEMPLATE.format(
            function_plan_json_str=function_plan_json_str,
            planner_notes=prep_res["planner_notes"]
        )
        logger.debug(f"TestCaseDesigner Prompt (first 300 chars): {test_case_prompt[:300]}...")
        response_str = call_llm(messages=[{"role": "user", "content": test_case_prompt}], model=llm_model, temperature=0.4)
        response_json = SimpleJsonOutputParser().parse(response_str)

        if response_json.get("error"):
            logger.error(f"TestCaseDesigner LLM error or parsing failed: {response_json['error']}")
            return {"error": "Test Case Designer LLM failed", "details": response_json.get("raw_text", response_str)}

        test_cases = response_json.get("test_cases")
        if not test_cases or not isinstance(test_cases, list):
            logger.error(f"TestCaseDesignerNode: 'test_cases' key missing or not a list in LLM response: {response_json}")
            return {"error": "LLM did not return a valid list of test cases"}
        
        valid_test_cases = []
        for tc in test_cases:
            if isinstance(tc, dict) and "inputs" in tc and "expected_output" in tc and "description" in tc:
                if isinstance(tc["inputs"], list): 
                    tc["inputs"] = tuple(tc["inputs"]) 
                elif not isinstance(tc["inputs"], tuple): 
                    tc["inputs"] = (tc["inputs"],)
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
        shared["all_tests_passed"] = False 
        shared["test_results_summary"] = [] 
        logger.debug(f"Generated test cases: {exec_res}")
        return "tests_ready"

class QAPrepInput(TypedDict):
    code_string: str
    function_name: str
    test_case: Dict[str, Any]

class QANode(Node):
    def prep(self, shared: Dict[str, Any]) -> Optional[QAPrepInput]:
        logger.info("Entering QANode - Prep")
        code = shared.get("generated_code")
        test_cases = shared.get("generated_test_cases")
        current_idx = shared.get("current_test_case_index", 0)

        if not code:
            logger.error("QANode: No generated code to test.")
            return {"error": "No code to test"}  # type: ignore
        if not test_cases or not isinstance(test_cases, list) or current_idx >= len(test_cases):
            logger.info("QANode: No more test cases to run or test cases not generated/valid.")
            return {"error": "No more tests or tests not found"}  # type: ignore
        
        current_test_case = test_cases[current_idx]
        function_name = current_test_case.get("function_name") or \
                        (shared.get("planned_task_description", {}).get("function_name") if isinstance(shared.get("planned_task_description"), dict) else "unknown_function")

        return {
            "code_string": code,
            "function_name": function_name,
            "test_case": current_test_case
        }

    def exec(self, prep_res: Optional[QAPrepInput]) -> Optional[Dict[str, Any]]:
        if not prep_res or prep_res.get("error"):
            error_msg = prep_res.get("error") if prep_res else "Prep failed for QANode"
            logger.error(f"QANode - Exec: Skipping due to prep error: {error_msg}")
            return {"status": "error", "message": error_msg, "test_case": prep_res.get("test_case") if prep_res else None, "actual_output": None}

        code_string = prep_res["code_string"]
        function_name = prep_res["function_name"]
        test_case = prep_res["test_case"]
        
        logger.info(f"QANode - Executing test: {test_case.get('description', 'N/A')} for function '{function_name}'")
        single_test_results = code_tester_tool(code_string, function_name, [test_case])
        
        if not single_test_results: 
            logger.error("QANode: code_tester_tool returned empty result.")
            return {"status": "error", "message": "Test tool malfunctioned.", "test_case": test_case, "actual_output": None}
            
        return single_test_results[0] 

    def post(self, shared: Dict[str, Any], prep_res: Optional[Dict[str, Any]], exec_res: Optional[Dict[str, Any]]):
        logger.info("QANode - Post")
        if not exec_res or exec_res.get("status") == "error":
            error_msg = exec_res.get("message", "QA execution failed or was skipped.") if exec_res else "QA prep failed."
            logger.error(f"QANode error: {error_msg}")
            shared["current_test_status"] = "error" # Specific status for tool/setup issue
            shared["current_test_message"] = error_msg
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"QA Attempt {shared.get('refinement_count',0)}: Error during test execution - {error_msg}")
            return "testing_error_or_done" 

        test_result = exec_res
        shared.setdefault("test_results_summary", []).append(test_result)
        shared["current_test_status"] = test_result["status"] # This will be 'success', 'fail', 'runtime_error', 'compilation_error'
        shared["current_test_message"] = test_result["message"]
        logger.debug(f"Test result: {test_result['status']} - {test_result['message']}")

        shared["current_test_case_index"] = shared.get("current_test_case_index", 0) + 1
        
        if test_result["status"] != "success":
            shared["all_tests_passed"] = False 
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"Test Failure (DevAttempt {shared.get('refinement_count',0)} on test '{test_result['test_case'].get('description')}'): {test_result['message']} (Actual: {test_result.get('actual_output')})")
            return "testing_error_or_done" 

        if shared["current_test_case_index"] >= len(shared.get("generated_test_cases", [])):
            all_current_tests_passed_this_round = all(
                res['status'] == 'success' for res in shared['test_results_summary']
                if res['test_case'] in shared.get("generated_test_cases", []) 
            )
            shared["all_tests_passed"] = all_current_tests_passed_this_round
            logger.info(f"All tests run. Overall pass status for this version: {shared['all_tests_passed']}")
            return "testing_error_or_done" 
        else:
            return "run_next_test"


class ValidationPrepInput(TypedDict):
    generated_code: str
    task_description: str
    planner_notes: str
    validation_rules_context: str
    llm_models_config: Dict[str, str]

class ValidationNode(Node):
    def prep(self, shared: Dict[str, Any]) -> ValidationPrepInput:
        logger.info("Entering ValidationNode - Prep")
        return {
            "generated_code": shared.get("generated_code"),
            "task_description": shared.get("task_description", "N/A"),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "validation_rules_context": shared.get("validation_rules_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: ValidationPrepInput) -> Dict[str, Any]:
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
        logger.debug(f"Validation Prompt (first 300 chars): {val_prompt[:300]}...")
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
            if not isinstance(shared["validation_issues"], list):
                shared["validation_issues"] = [str(shared["validation_issues"])] if shared["validation_issues"] else []
            if exec_res.get("validation_passed") and shared["validation_issues"]:
                 logger.warning("Validation conflict: LLM said passed but issues were found. Marking as fail.")
                 shared["validation_status"] = "fail"
                 shared["validation_issues"].append("Internal Consistency: LLM reported pass but listed issues.")
        else: 
            shared["validation_status"] = "error"
            shared["validation_issues"] = [str(exec_res.get("details", "Validation agent returned malformed output."))]

        logger.debug(f"Validation status: {shared['validation_status']}, Issues: {shared['validation_issues']}")
        # Add validation issues to feedback history for critique node
        if shared["validation_status"] != "pass" and shared["validation_issues"]:
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"Validation Issues (DevAttempt {shared.get('refinement_count',0)}): {'; '.join(shared['validation_issues'])}")
        return "testing_error_or_done"


class CritiquePrepInput(TypedDict):
    task_description: str
    planner_notes: str
    generated_code: str
    test_failure_message: str
    validation_issues: List[str]
    user_rejection_reason: str
    debugging_tips_context: str
    llm_models_config: Dict[str, str]

class CritiqueNode(Node):
    def prep(self, shared: Dict[str, Any]) -> CritiquePrepInput:
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

    def exec(self, prep_res: CritiquePrepInput) -> str:
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
        logger.debug(f"Critique Prompt (first 300 chars): {critique_prompt[:300]}...")
        response_str = call_llm(messages=[{"role": "user", "content": critique_prompt}], model=llm_model, temperature=0.25)
        critique_json = SimpleJsonOutputParser().parse(response_str)

        if critique_json.get("error"):
            logger.error(f"Critique LLM error or parsing failed: {critique_json['error']}")
            return f"Error in critique generation: {critique_json['error']}. Details: {critique_json.get('raw_text', response_str)[:100]}"
            
        feedback = critique_json.get("critique_feedback", "Critique LLM did not provide feedback.")
        return feedback

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: str):
        logger.info("CritiqueNode - Post")
        shared["critique_feedback"] = exec_res # This will be used by DeveloperNode
        
        # The feedback_history is already updated by QA and Validation nodes before critique.
        # CritiqueNode's output (exec_res) IS the feedback FOR the next dev attempt.
        # The app.py will handle adding this *generated* critique to the DB.
        # The shared["feedback_history"] is more for the DeveloperNode to see the sequence of events.

        logger.debug(f"Generated critique: {exec_res}")
        return "refine_code"


class PackagePrepInput(TypedDict):
    generated_code: str
    planned_task_description: Dict[str, Any]

class PackageNode(Node):
    def prep(self, shared: Dict[str, Any]) -> PackagePrepInput:
        logger.info("Entering PackageNode - Prep")
        return {
            "generated_code": shared.get("generated_code"),
            "planned_task_description": shared.get("planned_task_description", {})
        }

    def exec(self, prep_res: PackagePrepInput) -> Dict[str, Any]:
        logger.info("PackageNode - Executing")
        code = prep_res["generated_code"]
        plan = prep_res["planned_task_description"]

        # Check for missing code
        if not code:
            logger.error("PackageNode: No code provided for packaging")
            return {"error": "generated_code missing"}

        # Check for missing function name
        function_name = plan.get("function_name") if isinstance(plan, dict) else None
        if not function_name:
            logger.error("PackageNode: No function name found in planned_task_description")
            return {"error": "function_name missing"}

        py_file_content = f"# Auto-generated by FlowForge AI (Simple SDLC App)\n# Function: {function_name}\n\n{code}\n"
        readme_content = f"""# Function: {function_name}\n\n## Description from Plan\nThis function was automatically generated based on the following plan:\n```json\n{json.dumps(plan, indent=2)}\n```\n\n## Generated Code\n```python\n{code}\n```\n"""
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
        logger.debug(f"Packaged artifacts for: {exec_res.get('function_name')}")
        return "done"