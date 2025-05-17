# nodes.py
import logging
import json
from typing import Any, Dict, List, Optional, Tuple, TypedDict # Ensure TypedDict is imported

from pocketflow import Node # BaseNode is not typically directly used by app developers
from utils.call_llm import call_llm
from utils.tools import extract_project_structure_from_llm, code_tester_tool # Updated extract function
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
            # Remove potential markdown code fences if present
            # Standard JSON ```json ... ```
            match_md_json = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
            # Generic ``` ... ```
            match_md_generic = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            
            json_text_to_parse = None
            if match_md_json:
                json_text_to_parse = match_md_json.group(1).strip()
            elif match_md_generic:
                json_text_to_parse = match_md_generic.group(1).strip()
            else:
                # If no markdown blocks, try to find a JSON object directly.
                # This is a bit more lenient, might grab surrounding text if JSON is not well-formed.
                match_obj = re.search(r"^\s*\{.*\}\s*$", text, re.DOTALL)
                if match_obj:
                    json_text_to_parse = match_obj.group(0).strip()
                else: # Fallback to assuming the whole text might be JSON, if no blocks/objects clearly identified
                    json_text_to_parse = text.strip()
            
            if not json_text_to_parse:
                logger.error(f"JSON Parser: No JSON content identified after stripping markdown for text: {text[:200]}...")
                return {"error": "JSON parsing failed: No JSON content identified", "raw_text": text}

            return json.loads(json_text_to_parse)
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parsing Error in SimpleJsonOutputParser: {e} in text: {json_text_to_parse[:200] if json_text_to_parse else text[:200]}...")
            return {"error": f"JSON parsing failed: {e}", "raw_json_text": json_text_to_parse, "original_text": text}
        except Exception as e:
            logger.error(f"Unexpected error in SimpleJsonOutputParser: {e} for text: {text[:200]}...")
            return {"error": f"Unexpected parsing error: {e}", "raw_text": text}


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

        architect_llm_model = llm_models_config.get("architect_llm", "gpt-4o")
        arch_prompt = ARCHITECT_PROMPT_TEMPLATE.format(
            user_request=current_request,
            architectural_principles_context=arch_principles_ctx
        )
        arch_response_str = call_llm(messages=[{"role": "user", "content": arch_prompt}], model=architect_llm_model, temperature=0.1, expect_json=True)
        arch_decision = SimpleJsonOutputParser().parse(arch_response_str)
        
        if arch_decision.get("error"):
            logger.error(f"Architect LLM error or parsing failed: {arch_decision.get('error')}")
            return {"error": "Architect LLM failed", "details": arch_decision.get("raw_text", arch_response_str)}
        logger.info(f"Architect decision: {arch_decision}")

        planner_llm_model = llm_models_config.get("planner_llm", "gpt-4o")
        
        planner_codegen_prompt = PLANNER_CODEGEN_PROMPT_TEMPLATE.format(
            user_request_to_process=current_request,
            planning_guidelines_context=plan_guidelines_ctx,
            architect_decision_json_str=json.dumps(arch_decision) # Pass full architect decision
        )
        planner_response_str = call_llm(messages=[{"role": "user", "content": planner_codegen_prompt}], model=planner_llm_model, temperature=0.2, expect_json=True)
        planned_output = SimpleJsonOutputParser().parse(planner_response_str)

        if planned_output.get("error"):
            logger.error(f"Planner Codegen LLM error or parsing failed: {planned_output.get('error')}")
            return {"error": "Planner Codegen LLM failed", "details": planned_output.get("raw_text", planner_response_str), "architect_decision": arch_decision}

        # Check if the planner thinks it's clear (empty clarification_questions or key not present)
        if planned_output.get("planned_task_description") and not planned_output.get("clarification_questions"):
            logger.info(f"Planner created task description: {str(planned_output['planned_task_description'])[:100]}...")
            return {"architect_decision": arch_decision, "planned_output": planned_output, "needs_clarification": False}

        logger.info("Planner determined request needs clarification or codegen plan was insufficient. Asking clarification questions.")
        planner_clar_prompt = PLANNER_CLARIFICATION_PROMPT_TEMPLATE.format(
             user_request_to_process=current_request,
             planning_guidelines_context=plan_guidelines_ctx,
             architect_decision_json_str=json.dumps(arch_decision) # Pass full architect decision
        )
        clar_response_str = call_llm(messages=[{"role": "user", "content": planner_clar_prompt}], model=planner_llm_model, temperature=0.3, expect_json=True)
        clar_output = SimpleJsonOutputParser().parse(clar_response_str)
        
        if clar_output.get("error"):
            logger.error(f"Planner Clarification LLM error or parsing failed: {clar_output.get('error')}")
            return {"error": "Planner Clarification LLM failed", "details": clar_output.get("raw_text", clar_response_str), "architect_decision": arch_decision}
            
        logger.info(f"Planner generated clarification questions: {clar_output.get('clarification_questions')}")
        return {"architect_decision": arch_decision, "planned_output": clar_output, "needs_clarification": True}

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        logger.info("ArchitectPlannerNode - Post")
        shared["planner_iteration_count"] = shared.get("planner_iteration_count", 0) + 1

        if exec_res.get("error"):
            shared["current_error_message"] = f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            logger.error(f"ArchitectPlannerNode error: {shared['current_error_message']}")
            return "error_encountered" 

        shared["architectural_decision"] = exec_res.get("architect_decision")
        planned_output = exec_res.get("planned_output", {})
        
        if exec_res.get("needs_clarification") and planned_output.get("clarification_questions"):
            shared["clarification_questions_for_user"] = planned_output["clarification_questions"]
            shared["planned_task_description"] = None 
            shared["planner_notes"] = None
            shared["suggested_project_outline"] = None
            logger.debug("Returning 'clarification_needed'")
            return "clarification_needed"
        elif planned_output.get("planned_task_description"):
            shared["planned_task_description"] = planned_output["planned_task_description"] # This is now a dict
            shared["planner_notes"] = planned_output.get("planner_notes")
            shared["suggested_project_outline"] = planned_output.get("suggested_project_structure")
            # For DeveloperNode input compatibility and logging, we can create a string summary of the plan
            shared["developer_task_description"] = json.dumps(planned_output["planned_task_description"], indent=2) 
            shared["clarification_questions_for_user"] = None 
            logger.debug("Returning 'plan_ready_for_code'")
            return "plan_ready_for_code"
        else:
            error_msg = "Planner failed to produce a plan or clarification questions."
            logger.error(error_msg + f" LLM output: {planned_output}")
            shared["current_error_message"] = error_msg
            return "error_encountered"

class DeveloperNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering DeveloperNode - Prep")
        # planned_task_description is now a dict, so pass it as JSON string to prompt
        planned_task_desc_obj = shared.get("planned_task_description")
        if not isinstance(planned_task_desc_obj, dict):
            logger.error("DeveloperNode: planned_task_description is not a dict or is missing.")
            return {"error": "Planned task description (object) missing."}
        
        return {
            "planned_task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "coding_standards_context": shared.get("coding_standards_context", "N/A"),
            "critique_feedback": shared.get("critique_feedback", "N/A (first attempt or no critique)"),
            "feedback_history": "\n".join([f"- {item}" for item in shared.get("feedback_history", [])]) or "No prior feedback.",
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[Dict[str, Any]]: # Now returns project structure dict or None
        if prep_res.get("error"):
            logger.error(f"DeveloperNode: Error from prep stage: {prep_res['error']}")
            return {"error": f"Prep error: {prep_res['error']}"}

        logger.info(f"DeveloperNode - Executing with task plan: {prep_res['planned_task_description_json_str'][:200]}...")
        llm_model = prep_res["llm_models_config"].get("developer_llm", "gpt-4o")
        
        dev_prompt = DEVELOPER_CODEGEN_PROMPT_TEMPLATE.format(
            planned_task_description_json_str=prep_res["planned_task_description_json_str"],
            planner_notes=prep_res["planner_notes"],
            coding_standards_context=prep_res["coding_standards_context"],
            critique_message=prep_res["critique_feedback"],
            full_feedback_history=prep_res["feedback_history"]
        )
        llm_response_str = call_llm(messages=[{"role": "user", "content": dev_prompt}], model=llm_model, temperature=0.1, expect_json=True) # Expecting JSON for project structure
        
        project_structure = SimpleJsonOutputParser().parse(llm_response_str)

        if project_structure.get("error"):
            logger.error(f"DeveloperNode: LLM error or failed to parse project structure JSON: {project_structure['error']}. Raw: {project_structure.get('raw_text','')[:200]}")
            return {"error": f"Could not parse LLM output for project structure. Details: {project_structure.get('error')}", "raw_llm_response": project_structure.get('raw_text', llm_response_str)}
        
        # Validate basic project structure
        if not isinstance(project_structure, dict) or "files" not in project_structure or not isinstance(project_structure["files"], list):
            logger.error(f"DeveloperNode: Invalid project structure from LLM. Missing 'files' list. Got: {str(project_structure)[:200]}")
            return {"error": "LLM returned invalid project structure format.", "raw_llm_response": llm_response_str}

        return project_structure

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[Dict[str, Any]]):
        logger.info("DeveloperNode - Post")
        shared["refinement_count"] = shared.get("refinement_count", 0) + 1

        if exec_res is None or exec_res.get("error"):
            error_detail = exec_res.get("details", exec_res.get("raw_llm_response", "Unknown error during code generation.")) if isinstance(exec_res, dict) else "Execution returned None"
            shared["current_error_message"] = f"Developer Error: {exec_res.get('error', 'Code generation failed')}. Details: {str(error_detail)[:200]}"
            shared["generated_project_structure"] = None 
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"DevAttempt {shared['refinement_count']}: Failed to generate/parse code. {shared['current_error_message']}")
            logger.error(f"DeveloperNode error: {shared['current_error_message']}")
            return "code_generation_failed"
        
        shared["generated_project_structure"] = exec_res # This is now a dict
        logger.debug(f"Generated project structure (attempt {shared['refinement_count']}): {json.dumps(exec_res, indent=2)}")
        shared["critique_feedback"] = None 
        shared["current_error_message"] = None
        return "code_ready_for_tests"

class TestCaseDesignerNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering TestCaseDesignerNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        if not isinstance(planned_task_desc_obj, dict):
            return {"error": "Planned task description (object) missing for test design."}

        return {
            "function_plan_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", ""),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]: # Returns list of test_case dicts or error dict
        if prep_res.get("error"):
            logger.error(f"TestCaseDesignerNode: Error from prep: {prep_res['error']}")
            return prep_res # Pass error dict through

        logger.info(f"TestCaseDesignerNode - Executing with plan: {prep_res['function_plan_json_str'][:200]}...")
        llm_model = prep_res["llm_models_config"].get("test_designer_llm", "gpt-4o") 

        test_case_prompt = TEST_CASE_DESIGNER_PROMPT_TEMPLATE.format(
            function_plan_json_str=prep_res["function_plan_json_str"],
            planner_notes=prep_res["planner_notes"]
        )
        response_str = call_llm(messages=[{"role": "user", "content": test_case_prompt}], model=llm_model, temperature=0.4, expect_json=True)
        response_json = SimpleJsonOutputParser().parse(response_str)

        if response_json.get("error"):
            logger.error(f"TestCaseDesigner LLM error or parsing failed: {response_json['error']}")
            return {"error": "Test Case Designer LLM failed", "details": response_json.get("raw_text", response_str)}

        test_cases = response_json.get("test_cases")
        if not test_cases or not isinstance(test_cases, list):
            logger.error(f"TestCaseDesignerNode: 'test_cases' key missing or not a list: {response_json}")
            return {"error": "LLM did not return a valid list of test cases"}
        
        valid_test_cases = []
        planned_desc = json.loads(prep_res["function_plan_json_str"]) # Re-parse for function_name fallback
        for tc in test_cases:
            if isinstance(tc, dict) and "inputs" in tc and "expected_output" in tc and "description" in tc:
                if isinstance(tc["inputs"], list): tc["inputs"] = tuple(tc["inputs"]) 
                elif not isinstance(tc["inputs"], tuple): tc["inputs"] = (tc["inputs"],)
                
                # Ensure target_file and target_function are present, using plan as fallback
                tc["target_file"] = tc.get("target_file") or planned_desc.get("target_file") or planned_desc.get("entry_point_file", "main.py")
                tc["target_function"] = tc.get("target_function") or planned_desc.get("component_name") or planned_desc.get("main_function_to_test", "unknown_function")
                valid_test_cases.append(tc)
            else:
                logger.warning(f"Skipping malformed test case from LLM: {tc}")
        
        if not valid_test_cases:
            logger.error("TestCaseDesignerNode: No valid test cases generated by LLM.")
            return {"error": "No valid test cases generated"}
        return valid_test_cases

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[List[Dict[str, Any]]]):
        logger.info("TestCaseDesignerNode - Post")
        if isinstance(exec_res, dict) and exec_res.get("error"): # Check if exec_res itself is an error dict
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


class QANode(Node):
    def prep(self, shared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger.info("Entering QANode - Prep")
        project_structure = shared.get("generated_project_structure")
        test_cases = shared.get("generated_test_cases")
        current_idx = shared.get("current_test_case_index", 0)

        if not project_structure or not project_structure.get("files"):
            logger.error("QANode: No generated project structure to test.")
            return {"error": "No project code to test"}
        if not test_cases or not isinstance(test_cases, list) or current_idx >= len(test_cases):
            logger.info("QANode: No more test cases or tests not generated/valid.")
            return {"error": "No more tests or tests not valid"}
        
        current_test_case = test_cases[current_idx]
        return {
            "project_structure": project_structure,
            "test_case": current_test_case
        }

    def exec(self, prep_res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not prep_res or prep_res.get("error"):
            error_msg = prep_res.get("error") if prep_res else "Prep failed for QANode"
            logger.error(f"QANode - Exec: Skipping due to prep error: {error_msg}")
            return {"status": "error", "message": error_msg, "test_case": prep_res.get("test_case") if prep_res else None, "actual_output": None}

        project_structure = prep_res["project_structure"]
        test_case = prep_res["test_case"]
        
        # Target function and file are now part of each test_case
        target_function = test_case.get("target_function")
        target_file = test_case.get("target_file")
        
        logger.info(f"QANode - Executing test: {test_case.get('description', 'N/A')} for function '{target_function}' in file '{target_file}'")
        # Pass project_structure and a list containing the single test_case
        single_test_results = code_tester_tool(project_structure, [test_case])
        
        if not single_test_results: 
            logger.error("QANode: code_tester_tool returned empty result.")
            return {"status": "error", "message": "Test tool malfunctioned.", "test_case": test_case, "actual_output": None}
            
        return single_test_results[0] 

    def post(self, shared: Dict[str, Any], prep_res: Optional[Dict[str, Any]], exec_res: Optional[Dict[str, Any]]):
        # (Post method logic remains the same as previously provided)
        logger.info("QANode - Post")
        if not exec_res or exec_res.get("status") == "error":
            error_msg = exec_res.get("message", "QA execution failed or was skipped.") if exec_res else "QA prep failed."
            logger.error(f"QANode error: {error_msg}")
            shared["current_test_status"] = "error"
            shared["current_test_message"] = error_msg
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"QA Attempt {shared.get('refinement_count',0)}: Error during test execution - {error_msg}")
            return "testing_error_or_done" 

        test_result = exec_res
        shared.setdefault("test_results_summary", []).append(test_result)
        shared["current_test_status"] = test_result["status"] 
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
                if res.get('test_case') in shared.get("generated_test_cases", []) 
            )
            shared["all_tests_passed"] = all_current_tests_passed_this_round
            logger.info(f"All tests run. Overall pass status for this version: {shared['all_tests_passed']}")
            return "testing_error_or_done" 
        else:
            return "run_next_test"

class ValidationNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering ValidationNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        if not isinstance(planned_task_desc_obj, dict):
            return {"error": "Planned task description (object) missing for validation."}

        return {
            "generated_project_structure": shared.get("generated_project_structure"),
            "task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "validation_rules_context": shared.get("validation_rules_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        if prep_res.get("error"):
            logger.error(f"ValidationNode: Error from prep: {prep_res['error']}")
            return {"validation_passed": False, "issues_found": [prep_res['error']]}
            
        project_structure = prep_res["generated_project_structure"]
        if not project_structure or not project_structure.get("files"):
            logger.error("ValidationNode: No project structure/files to validate.")
            return {"validation_passed": False, "issues_found": ["No project code provided for validation."]}

        logger.info(f"ValidationNode - Executing for task (plan snippet): {prep_res['task_description_json_str'][:100]}...")
        llm_model = prep_res["llm_models_config"].get("validation_llm", "gpt-4o")

        val_prompt = VALIDATION_PROMPT_TEMPLATE.format(
            task_description_json_str=prep_res["task_description_json_str"],
            planner_notes=prep_res["planner_notes"],
            project_structure_json_str=json.dumps(project_structure, indent=2), # Pass project structure as JSON string
            validation_rules_context=prep_res["validation_rules_context"]
        )
        response_str = call_llm(messages=[{"role": "user", "content": val_prompt}], model=llm_model, temperature=0.1, expect_json=True)
        validation_result = SimpleJsonOutputParser().parse(response_str)
        
        if validation_result.get("error"):
            logger.error(f"Validation LLM error or parsing failed: {validation_result['error']}")
            return {"validation_passed": False, "issues_found": [f"Validation LLM failed: {validation_result['error']}"], "details": validation_result.get("raw_text", response_str)}

        return validation_result

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        # (Post method logic remains the same as previously provided)
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
        return "validation_done" # This action is used by app.py to decide flow.


class CritiqueNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering CritiqueNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        if not isinstance(planned_task_desc_obj, dict):
            return {"error": "Planned task description (object) missing for critique."}
        
        project_structure_obj = shared.get("generated_project_structure")
        if not isinstance(project_structure_obj, dict) or not project_structure_obj.get("files"):
            return {"error": "Generated project structure missing or invalid for critique."}

        return {
            "task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "project_structure_json_str": json.dumps(project_structure_obj, indent=2),
            "test_failure_message": shared.get("current_test_message", "N/A (or tests passed/not run)"),
            "validation_issues_list_str": "; ".join(shared.get("validation_issues", [])) if shared.get("validation_issues") else "N/A",
            "user_rejection_reason": shared.get("user_rejection_reason", "N/A"),
            "debugging_tips_context": shared.get("debugging_tips_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> str:
        if prep_res.get("error"):
            logger.error(f"CritiqueNode: Error from prep: {prep_res['error']}")
            return f"Error in critique prep: {prep_res['error']}"

        logger.info(f"CritiqueNode - Executing...")
        llm_model = prep_res["llm_models_config"].get("critique_llm", "gpt-4o-mini")

        critique_prompt = CRITIQUE_PROMPT_TEMPLATE.format(
            task_description_json_str=prep_res["task_description_json_str"],
            planner_notes=prep_res["planner_notes"],
            project_structure_json_str=prep_res["project_structure_json_str"],
            test_failure_message=prep_res["test_failure_message"],
            validation_issues_list_str=prep_res["validation_issues_list_str"],
            user_rejection_reason=prep_res["user_rejection_reason"],
            debugging_tips_context=prep_res["debugging_tips_context"]
        )
        response_str = call_llm(messages=[{"role": "user", "content": critique_prompt}], model=llm_model, temperature=0.25, expect_json=True)
        critique_json = SimpleJsonOutputParser().parse(response_str)

        if critique_json.get("error"):
            logger.error(f"Critique LLM error or parsing failed: {critique_json['error']}")
            return f"Error in critique generation: {critique_json['error']}. Details: {critique_json.get('raw_text', response_str)[:100]}"
            
        feedback = critique_json.get("critique_feedback", "Critique LLM did not provide feedback.")
        return feedback

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: str):
        logger.info("CritiqueNode - Post")
        shared["critique_feedback"] = exec_res
        logger.debug(f"Generated critique: {exec_res}")
        return "refine_code" # Signal to DeveloperNode to refine

class PackageNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering PackageNode - Prep")
        project_structure = shared.get("generated_project_structure")
        planned_desc = shared.get("planned_task_description")

        if not isinstance(project_structure, dict) or not project_structure.get("files"):
             return {"error": "Generated project structure missing or invalid for packaging."}
        if not isinstance(planned_desc, dict):
            return {"error": "Planned task description (object) missing for packaging."}
            
        return {
            "generated_project_structure": project_structure,
            "planned_task_description": planned_desc
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        if prep_res.get("error"):
            logger.error(f"PackageNode: Error from prep: {prep_res['error']}")
            return prep_res # Pass error through

        logger.info("PackageNode - Executing")
        project_structure = prep_res["generated_project_structure"]
        plan = prep_res["planned_task_description"]
        
        main_component_name = plan.get("component_name", "unnamed_component")
        
        # For MVP, "packaging" just means collating the final structure and a summary.
        # In a real app, this might create a ZIP, git commit, etc.
        packaged_info = {
            "project_files": project_structure.get("files", []),
            "entry_point": project_structure.get("entry_point_file", "N/A"),
            "main_component_tested": project_structure.get("main_function_to_test", main_component_name)
        }
        handoff_summary = f"Successfully generated and packaged project for component: '{main_component_name}'."
        
        logger.info(f"Packaging artifacts for project related to: {main_component_name}")
        return {
            "packaged_artifacts_info": packaged_info, # The dict of file contents
            "handoff_summary": handoff_summary,
            "main_component_name": main_component_name
        }

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        logger.info("PackageNode - Post")
        if exec_res.get("error"):
            shared["current_error_message"] = f"Packaging Error: {exec_res['error']}"
            shared["packaged_artifacts_info"] = None
            shared["handoff_summary"] = "Packaging failed."
            logger.error(f"PackageNode error: {shared['current_error_message']}")
            return "error_encountered"

        shared["packaged_artifacts_info"] = exec_res.get("packaged_artifacts_info")
        shared["handoff_summary"] = exec_res.get("handoff_summary")
        logger.debug(f"Packaged artifacts for: {exec_res.get('main_component_name')}")
        return "done"