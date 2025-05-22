"""
Node definitions for the SDLC PocketFlow system.
"""
import logging
import json
import re
from typing import Any, Dict, List, Optional
from pocketflow import Node
from utils.call_llm import call_llm
from utils.tools import extract_project_structure_from_llm, code_tester_tool
from utils.prompts import (
    ARCHITECT_PROMPT_TEMPLATE,
    PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
    PLANNER_CODEGEN_PROMPT_TEMPLATE,
    DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
    TEST_CASE_DESIGNER_PROMPT_TEMPLATE,
    VALIDATION_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT_TEMPLATE,
    SECURITY_COMPLIANCE_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)


class SimpleJsonOutputParser:
    def parse(self, text: str) -> Any:
        try:
            match_md_json = re.search(
                r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE
            )
            match_md_generic = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            json_text_to_parse = None
            if match_md_json:
                json_text_to_parse = match_md_json.group(1).strip()
            elif match_md_generic:
                json_text_to_parse = match_md_generic.group(1).strip()
            else:
                match_obj = re.search(r"^\s*\{.*\}\s*$", text, re.DOTALL)
                if match_obj:
                    json_text_to_parse = match_obj.group(0).strip()
                else:
                    json_text_to_parse = text.strip()
            if not json_text_to_parse:
                return {
                    "error": "JSON parsing failed: No JSON content identified",
                    "raw_text": text,
                }
            return json.loads(json_text_to_parse)
        except json.JSONDecodeError as e:
            raw_snippet = json_text_to_parse[:200] if json_text_to_parse else text[:200]
            return {
                "error": f"JSON parsing failed: {e}",
                "raw_json_text": json_text_to_parse,
                "original_text": text,
                "snippet": raw_snippet,
            }
        except Exception as e:
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

    def post(
        self, shared: Dict[str, Any], prep_res: Optional[str], exec_res: Optional[str]
    ):
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
        logger.info(
            f"ArchitectPlannerNode - Prep. ID: {id(shared)}. planner_iter: {shared.get('planner_iteration_count')}"
        )
        return {
            "current_request": shared.get("current_request_for_planner", ""),
            "architectural_principles_context": shared.get(
                "architectural_principles_context", "N/A"
            ),
            "planning_guidelines_context": shared.get(
                "planning_guidelines_context", "N/A"
            ),
            "llm_models_config": shared.get("llm_models_config", {}),
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(
            f"ArchitectPlannerNode - Exec with request: {prep_res['current_request'][:100]}..."
        )
        current_request = prep_res["current_request"]
        arch_principles_ctx = prep_res["architectural_principles_context"]
        plan_guidelines_ctx = prep_res["planning_guidelines_context"]
        llm_models_config = prep_res["llm_models_config"]
        architect_llm_model = llm_models_config.get("architect_llm", "gpt-4o")
        arch_prompt = ARCHITECT_PROMPT_TEMPLATE.format(
            user_request=current_request,
            architectural_principles_context=arch_principles_ctx,
        )
        arch_response_str = call_llm(
            messages=[{"role": "user", "content": arch_prompt}],
            model=architect_llm_model,
            temperature=0.1,
            expect_json=True,
        )
        arch_decision = SimpleJsonOutputParser().parse(arch_response_str)
        if arch_decision.get("error"):
            logger.error(f"Architect LLM error: {arch_decision.get('error')}")
            return {
                "error": "Architect LLM failed",
                "details": arch_decision.get("raw_text", arch_response_str),
            }
        logger.info(f"Architect decision: {arch_decision}")
        planner_llm_model = llm_models_config.get("planner_llm", "gpt-4o")
        planner_codegen_prompt = PLANNER_CODEGEN_PROMPT_TEMPLATE.format(
            user_request_to_process=current_request,
            planning_guidelines_context=plan_guidelines_ctx,
            architect_decision_json_str=json.dumps(arch_decision),
        )
        planner_response_str = call_llm(
            messages=[{"role": "user", "content": planner_codegen_prompt}],
            model=planner_llm_model,
            temperature=0.2,
            expect_json=True,
        )
        planned_output = SimpleJsonOutputParser().parse(planner_response_str)
        if planned_output.get("error"):
            logger.error(
                f"Planner Codegen LLM error or parsing failed: {planned_output.get('error')}"
            )
            planner_clar_prompt = PLANNER_CLARIFICATION_PROMPT_TEMPLATE.format(
                user_request_to_process=current_request,
                planning_guidelines_context=plan_guidelines_ctx,
                architect_decision_json_str=json.dumps(arch_decision),
            )
            clar_response_str = call_llm(
                messages=[{"role": "user", "content": planner_clar_prompt}],
                model=planner_llm_model,
                temperature=0.3,
                expect_json=True,
            )
            clar_output = SimpleJsonOutputParser().parse(clar_response_str)
            if clar_output.get("error"):
                logger.error(
                    f"Planner Clarification LLM error: {clar_output.get('error')}"
                )
                return {
                    "error": "Planner Clarification LLM failed",
                    "details": clar_output.get("raw_text", clar_response_str),
                    "architect_decision": arch_decision,
                    "needs_clarification": True,
                    "planned_output": {},
                }
            logger.info(
                f"Planner generated clarification questions: {clar_output.get('clarification_questions')}"
            )
            return {
                "architect_decision": arch_decision,
                "planned_output": clar_output,
                "needs_clarification": True,
            }
        if planned_output.get("planned_task_description") and not planned_output.get(
            "clarification_questions"
        ):
            logger.info(
                f"Planner created task desc: {str(planned_output['planned_task_description'])[:100]}..."
            )
            return {
                "architect_decision": arch_decision,
                "planned_output": planned_output,
                "needs_clarification": False,
            }
        logger.info("Planner needs clarification. Asking questions.")
        planner_clar_prompt = PLANNER_CLARIFICATION_PROMPT_TEMPLATE.format(
            user_request_to_process=current_request,
            planning_guidelines_context=plan_guidelines_ctx,
            architect_decision_json_str=json.dumps(arch_decision),
        )
        clar_response_str = call_llm(
            messages=[{"role": "user", "content": planner_clar_prompt}],
            model=planner_llm_model,
            temperature=0.3,
            expect_json=True,
        )
        clar_output = SimpleJsonOutputParser().parse(clar_response_str)
        if clar_output.get("error"):
            logger.error(f"Planner Clarification LLM error: {clar_output.get('error')}")
            return {
                "error": "Planner Clarification LLM failed",
                "details": clar_output.get("raw_text", clar_response_str),
                "architect_decision": arch_decision,
            }
        logger.info(
            f"Planner generated clarification questions: {clar_output.get('clarification_questions')}"
        )
        return {
            "architect_decision": arch_decision,
            "planned_output": clar_output,
            "needs_clarification": True,
        }

    def post(
        self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]
    ):
        logger.info(
            f"ArchitectPlannerNode - Post. ID shared: {id(shared)}. planner_iter entry: {shared.get('planner_iteration_count')}"
        )
        shared["planner_iteration_count"] = (
            shared.get("planner_iteration_count", -1) + 1
        )
        logger.info(
            f"ArchitectPlannerNode: planner_iteration_count in shared is now: {shared['planner_iteration_count']}"
        )
        if exec_res.get("error"):
            shared["current_error_message"] = (
                f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            )
            logger.error(f"APNode error: {shared['current_error_message']}")
            return "error_encountered"
        shared["architectural_decision"] = exec_res.get("architect_decision")
        planned_output = exec_res.get("planned_output", {})
        if exec_res.get("needs_clarification") and planned_output.get(
            "clarification_questions"
        ):
            shared["clarification_questions_for_user"] = planned_output[
                "clarification_questions"
            ]
            shared["planned_task_description"] = None
            shared["planner_notes"] = None
            shared["suggested_project_outline"] = None
            return "clarification_needed"
        elif planned_output.get("planned_task_description"):
            shared["planned_task_description"] = planned_output[
                "planned_task_description"
            ]
            shared["planner_notes"] = planned_output.get("planner_notes")
            shared["suggested_project_outline"] = planned_output.get(
                "suggested_project_structure"
            )
            shared["developer_task_description"] = json.dumps(
                planned_output["planned_task_description"], indent=2
            )
            shared["clarification_questions_for_user"] = None
            return "plan_ready_for_code"
        else:
            shared["current_error_message"] = "Planner no plan/clarification."
            logger.error(
                f"APNode error: {shared['current_error_message']} - Output: {planned_output}"
            )
            return "error_encountered"


class DeveloperNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(
            f"DeveloperNode - Prep. ID shared: {id(shared)}. refinement_count: {shared.get('refinement_count')}"
        )
        planned_task_desc_obj = shared.get("planned_task_description")
        suggested_project_outline_obj = shared.get("suggested_project_outline")
        if not isinstance(planned_task_desc_obj, dict):
            return {"error": "Plan (obj) missing."}
        if suggested_project_outline_obj and not isinstance(
            suggested_project_outline_obj, list
        ):
            suggested_project_outline_obj = []
        return {
            "planned_task_description_json_str": json.dumps(
                planned_task_desc_obj, indent=2
            ),
            "suggested_project_outline_json_str": json.dumps(
                suggested_project_outline_obj or [], indent=2
            ),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "coding_standards_context": shared.get("coding_standards_context", "N/A"),
            "critique_feedback": shared.get("critique_feedback", "N/A"),
            "full_feedback_history": "\n".join(
                [f"- {i}" for i in shared.get("feedback_history", [])]
            )
            or "No prior feedback.",
            "llm_models_config": shared.get("llm_models_config", {}),
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if prep_res.get("error"):
            logger.error(f"DevNode: Prep error: {prep_res['error']}")
            return prep_res
        logger.info(
            f"DevNode - Exec plan: {prep_res['planned_task_description_json_str'][:100]}..."
        )
        llm_model = prep_res["llm_models_config"].get("developer_llm", "gpt-4o")
        dev_prompt = DEVELOPER_CODEGEN_PROMPT_TEMPLATE.format(**prep_res)
        llm_response_str = call_llm(
            messages=[{"role": "user", "content": dev_prompt}],
            model=llm_model,
            temperature=0.1,
            expect_json=True,
        )
        project_structure = SimpleJsonOutputParser().parse(llm_response_str)
        if project_structure.get("error"):
            logger.error(
                f"DevNode: LLM/parse error: {project_structure['error']}. Raw: {project_structure.get('raw_text','')[:100]}"
            )
            return {
                "error": f"LLM project parse error. Details: {project_structure.get('error')}",
                "raw_llm_response": project_structure.get("raw_text", llm_response_str),
            }
        if (
            not isinstance(project_structure, dict)
            or "files" not in project_structure
            or not isinstance(project_structure["files"], list)
        ):
            logger.error(
                f"DevNode: Invalid project struct: {str(project_structure)[:100]}"
            )
            return {
                "error": "LLM invalid project struct.",
                "raw_llm_response": llm_response_str,
            }
        return project_structure

    def post(
        self,
        shared: Dict[str, Any],
        prep_res: Dict[str, Any],
        exec_res: Optional[Dict[str, Any]],
    ):
        logger.info(
            f"DeveloperNode - Post. ID shared: {id(shared)}. Refinement_count entry: {shared.get('refinement_count')}"
        )
        shared["refinement_count"] = shared.get("refinement_count", -1) + 1
        current_attempt_number = shared["refinement_count"]
        logger.info(
            f"DeveloperNode: Post-increment. refinement_count in shared: {shared['refinement_count']}"
        )
        if exec_res is None or exec_res.get("error"):
            error_detail = (
                exec_res.get(
                    "details", exec_res.get("raw_llm_response", "Unknown dev error.")
                )
                if isinstance(exec_res, dict)
                else "Exec returned None"
            )
            shared["current_error_message"] = (
                f"Dev Error (Att.{current_attempt_number}): {exec_res.get('error','Code gen failed')}. Details: {str(error_detail)[:100]}"
            )
            shared["generated_project_structure"] = None
            shared.setdefault("feedback_history", []).append(
                f"DevAtt.{current_attempt_number}: Fail gen/parse. {str(shared['current_error_message'])}"
            )
            return "code_generation_failed"
        shared["generated_project_structure"] = exec_res
        logger.debug(
            f"Generated project (Att.{current_attempt_number}): {json.dumps(exec_res,indent=2)[:200]}..."
        )
        shared["critique_feedback"] = None
        shared["current_error_message"] = None
        return "code_ready_for_tests"


class QANode(Node):
    def prep(self, shared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger.info("Entering QANode - Prep")
        project_structure = shared.get("generated_project_structure")
        test_cases = shared.get("generated_test_cases")
        current_idx = shared.get("current_test_case_index", 0)
        if not project_structure or not project_structure.get("files"):
            return {"error": "No project code"}
        if (
            not test_cases
            or not isinstance(test_cases, list)
            or current_idx >= len(test_cases)
        ):
            return {"error": "No more/valid tests"}
        return {
            "project_structure": project_structure,
            "test_case": test_cases[current_idx],
        }

    def exec(self, prep_res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not prep_res or prep_res.get("error"):
            error_msg = prep_res.get("error") if prep_res else "Prep failed"
            return {
                "status": "error",
                "message": error_msg,
                "test_case": prep_res.get("test_case") if prep_res else None,
            }
        project_structure = prep_res["project_structure"]
        test_case = prep_res["test_case"]
        single_test_results = code_tester_tool(project_structure, [test_case])
        if not single_test_results:
            return {
                "status": "error",
                "message": "Test tool malfunctioned.",
                "test_case": test_case,
            }
        return single_test_results[0]

    def post(
        self,
        shared: Dict[str, Any],
        prep_res: Optional[Dict[str, Any]],
        exec_res: Optional[Dict[str, Any]],
    ):
        logger.info("QANode - Post")
        if not exec_res or exec_res.get("status") == "error":
            error_msg = (
                exec_res.get("message", "QA exec failed.")
                if exec_res
                else "QA prep failed."
            )
            shared["current_test_status"] = (
                exec_res.get("status", "error") if exec_res else "error"
            )
            shared["current_test_message"] = error_msg
            shared.setdefault("test_results_summary", []).append(
                exec_res
                or {
                    "status": "error",
                    "message": error_msg,
                    "test_case": prep_res.get("test_case") if prep_res else {},
                }
            )
            shared["all_tests_passed"] = False
            shared.setdefault("feedback_history", []).append(
                f"QA Error/Fail (DevAtt.{shared.get('refinement_count',0)} test '{exec_res.get('test_case',{}).get('description','N/A')}'): {error_msg}"
            )
            return "testing_error_or_done"
        shared.setdefault("test_results_summary", []).append(exec_res)
        shared["current_test_status"] = exec_res["status"]
        shared["current_test_message"] = exec_res["message"]
        if exec_res["status"] != "success":
            shared["all_tests_passed"] = False
            shared.setdefault("feedback_history", []).append(
                f"Test Fail (DevAtt.{shared.get('refinement_count',0)} test '{exec_res['test_case'].get('description')}'): {exec_res['message']} (Actual: {exec_res.get('actual_output')})"
            )
        shared["current_test_case_index"] = shared.get("current_test_case_index", 0) + 1
        if shared["current_test_case_index"] >= len(
            shared.get("generated_test_cases", [])
        ):
            shared["all_tests_passed"] = all(
                res["status"] == "success" for res in shared["test_results_summary"]
            )
            logger.info(f"All tests run. Overall pass: {shared['all_tests_passed']}")
            return "testing_error_or_done"
        else:
            return "run_next_test"


class ValidationNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering ValidationNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        project_structure_obj = shared.get("generated_project_structure")
        if not isinstance(planned_task_desc_obj, dict):
            return {"error": "Plan missing."}
        if not isinstance(project_structure_obj, dict) or not project_structure_obj.get(
            "files"
        ):
            return {"error": "Project structure missing."}
        return {
            "project_structure_json_str": json.dumps(project_structure_obj, indent=2),
            "task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "validation_rules_context": shared.get("validation_rules_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {}),
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        if prep_res.get("error"):
            return {"validation_passed": False, "issues_found": [prep_res["error"]]}
        logger.info(
            f"ValidationNode - Exec plan: {prep_res['task_description_json_str'][:100]}..."
        )
        llm_model = prep_res["llm_models_config"].get("validation_llm", "gpt-4o")
        val_prompt = VALIDATION_PROMPT_TEMPLATE.format(**prep_res)
        response_str = call_llm(
            messages=[{"role": "user", "content": val_prompt}],
            model=llm_model,
            temperature=0.1,
            expect_json=True,
        )
        validation_result = SimpleJsonOutputParser().parse(response_str)
        if validation_result.get("error"):
            return {
                "validation_passed": False,
                "issues_found": [f"Validation LLM fail: {validation_result['error']}"],
                "details": validation_result.get("raw_text", response_str),
            }
        return validation_result

    def post(
        self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]
    ):
        logger.info("ValidationNode - Post")
        if isinstance(exec_res, dict) and "validation_passed" in exec_res:
            shared["validation_status"] = (
                "pass"
                if exec_res["validation_passed"] and not exec_res.get("issues_found")
                else "fail"
            )
            shared["validation_issues"] = exec_res.get("issues_found", [])
            if not isinstance(shared["validation_issues"], list):
                shared["validation_issues"] = (
                    [str(shared["validation_issues"])]
                    if shared["validation_issues"]
                    else []
                )
            if exec_res.get("validation_passed") and shared["validation_issues"]:
                shared["validation_status"] = "fail"
                shared["validation_issues"].append(
                    "Consistency: LLM pass but listed issues."
                )
        else:
            shared["validation_status"] = "error"
            shared["validation_issues"] = [
                str(exec_res.get("details", "Validation agent malformed."))
            ]
        if shared["validation_status"] != "pass" and shared["validation_issues"]:
            shared.setdefault("feedback_history", []).append(
                f"Validation Issues (DevAtt.{shared.get('refinement_count',0)}): {'; '.join(shared['validation_issues'])}"
            )
        if shared["validation_status"] == "pass":
            return None
        return "validation_done"


class SecurityComplianceNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering SecurityComplianceNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        project_structure_obj = shared.get("generated_project_structure")

        if not isinstance(planned_task_desc_obj, dict):
            return {
                "error": "Planned task description (object) missing for security check."
            }
        if not isinstance(project_structure_obj, dict) or not project_structure_obj.get(
            "files"
        ):
            return {
                "error": "Generated project structure missing or invalid for security check."
            }

        return {
            "task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "project_structure_json_str": json.dumps(project_structure_obj, indent=2),
            "security_compliance_rules_context": shared.get(
                "security_compliance_rules_context", "N/A - No specific rules provided."
            ),
            "llm_models_config": shared.get("llm_models_config", {}),
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        if prep_res.get("error"):
            logger.error(
                f"SecurityComplianceNode: Error from prep: {prep_res['error']}"
            )
            return {
                "security_compliance_passed": False,
                "issues_identified": [prep_res["error"]],
            }

        logger.info(
            f"SecurityComplianceNode - Executing for plan: {prep_res['task_description_json_str'][:100]}..."
        )
        llm_model = prep_res["llm_models_config"].get(
            "validation_llm", "gpt-4o"
        )

        sec_prompt = SECURITY_COMPLIANCE_PROMPT_TEMPLATE.format(**prep_res)

        logger.debug(f"SecurityCompliance Prompt (first 300): {sec_prompt[:300]}...")
        response_str = call_llm(
            messages=[{"role": "user", "content": sec_prompt}],
            model=llm_model,
            temperature=0.1,
            expect_json=True,
        )
        security_result = SimpleJsonOutputParser().parse(response_str)

        if security_result.get("error"):
            logger.error(
                f"SecurityCompliance LLM error or parsing failed: {security_result['error']}"
            )
            return {
                "security_compliance_passed": False,
                "issues_identified": [
                    f"Security LLM failed: {security_result['error']}"
                ],
                "details": security_result.get("raw_text", response_str),
            }

        return security_result

    def post(
        self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]
    ):
        logger.info("SecurityComplianceNode - Post")
        if isinstance(exec_res, dict) and "security_compliance_passed" in exec_res:
            shared["security_compliance_status"] = (
                "pass"
                if exec_res["security_compliance_passed"]
                and not exec_res.get("issues_identified")
                else "fail"
            )
            shared["security_compliance_issues"] = exec_res.get("issues_identified", [])
            if not isinstance(shared["security_compliance_issues"], list):
                shared["security_compliance_issues"] = (
                    [str(shared["security_compliance_issues"])]
                    if shared["security_compliance_issues"]
                    else []
                )
            if (
                exec_res.get("security_compliance_passed")
                and shared["security_compliance_issues"]
            ):
                shared["security_compliance_status"] = "fail"
                shared["security_compliance_issues"].append(
                    "Internal Consistency: LLM reported security pass but listed issues."
                )
        else:
            shared["security_compliance_status"] = "error"
            shared["security_compliance_issues"] = [
                str(
                    exec_res.get("details", "Security agent returned malformed output.")
                )
            ]

        logger.debug(
            f"Security check status: {shared['security_compliance_status']}, Issues: {shared['security_compliance_issues']}"
        )
        if (
            shared["security_compliance_status"] != "pass"
            and shared["security_compliance_issues"]
        ):
            shared.setdefault("feedback_history", []).append(
                f"Security/Compliance Issues (DevAttempt {shared.get('refinement_count',0)}): {'; '.join(shared['security_compliance_issues'])}"
            )
        return "security_check_done"


class CritiqueNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering CritiqueNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        project_structure_obj = shared.get("generated_project_structure")
        if not isinstance(planned_task_desc_obj, dict):
            return {"error": "Plan missing for critique."}
        if not isinstance(project_structure_obj, dict) or not project_structure_obj.get(
            "files"
        ):
            return {"error": "Project structure missing for critique."}
        return {
            "task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "project_structure_json_str": json.dumps(project_structure_obj, indent=2),
            "test_failure_message": shared.get("current_test_message", "N/A"),
            "validation_issues_list_str": (
                "; ".join(shared.get("validation_issues", []))
                if shared.get("validation_issues")
                else "N/A"
            ),
            "user_rejection_reason": shared.get("user_rejection_reason", "N/A"),
            "debugging_tips_context": shared.get("debugging_tips_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {}),
        }

    def exec(self, prep_res: Dict[str, Any]) -> str:
        if prep_res.get("error"):
            return f"Error in critique prep: {prep_res['error']}"
        logger.info(f"CritiqueNode - Executing...")
        llm_model = prep_res["llm_models_config"].get("critique_llm", "gpt-4o-mini")
        critique_prompt = CRITIQUE_PROMPT_TEMPLATE.format(**prep_res)
        response_str = call_llm(
            messages=[{"role": "user", "content": critique_prompt}],
            model=llm_model,
            temperature=0.25,
            expect_json=True,
        )
        critique_json = SimpleJsonOutputParser().parse(response_str)
        if critique_json.get("error"):
            return f"Critique LLM error: {critique_json['error']}. Details: {critique_json.get('raw_text',response_str)[:100]}"
        return critique_json.get("critique_feedback", "Critique LLM no feedback.")

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: str):
        logger.info("CritiqueNode - Post")
        shared["critique_feedback"] = exec_res
        logger.debug(f"Generated critique: {exec_res}")
        return "refine_code"


class PackageNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering PackageNode - Prep")
        project_structure = shared.get("generated_project_structure")
        planned_desc = shared.get("planned_task_description")
        if not isinstance(project_structure, dict) or not project_structure.get(
            "files"
        ):
            return {
                "error": "Generated project structure missing or invalid for packaging."
            }
        if not isinstance(planned_desc, dict):
            return {"error": "Planned task description (object) missing for packaging."}
        return {
            "generated_project_structure": project_structure,
            "planned_task_description": planned_desc,
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        if prep_res.get("error"):
            return prep_res
        logger.info("PackageNode - Executing")
        project_structure = prep_res["generated_project_structure"]
        plan = prep_res["planned_task_description"]
        main_component_name = plan.get("component_name")
        if not main_component_name:
            logger.error("PackageNode: component_name missing.")
            return {
                "error": "component_name missing in planned_task_description for packaging."
            }
        packaged_info = {
            "project_files": project_structure.get("files", []),
            "entry_point": project_structure.get("entry_point_file", "N/A"),
            "main_component_details": plan,
        }
        handoff_summary = (
            f"Successfully packaged project for component: '{main_component_name}'."
        )
        return {
            "packaged_artifacts_info": packaged_info,
            "handoff_summary": handoff_summary,
            "main_component_name": main_component_name,
        }

    def post(
        self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]
    ):
        logger.info("PackageNode - Post")
        if exec_res.get("error"):
            shared["current_error_message"] = f"Packaging Error: {exec_res['error']}"
            shared["packaged_artifacts_info"] = None
            shared["handoff_summary"] = "Packaging failed."
            return "error_encountered"
        shared["packaged_artifacts_info"] = exec_res.get("packaged_artifacts_info")
        shared["handoff_summary"] = exec_res.get("handoff_summary")
        return "done"


class TestCaseDesignerNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering TestCaseDesignerNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        if not isinstance(planned_task_desc_obj, dict):
            return {
                "error": "Planned task description (object) missing for test design."
            }
        current_project_structure = shared.get("generated_project_structure", {})
        critique_feedback = shared.get(
            "critique_feedback",
            "N/A (No specific critique for this test design phase, or initial design)",
        )
        return {
            "function_plan_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", ""),
            "current_project_structure_json_str": json.dumps(
                current_project_structure, indent=2
            ),
            "critique_feedback_for_tests": critique_feedback,
            "llm_models_config": shared.get("llm_models_config", {}),
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        if prep_res.get("error"):
            return prep_res
        logger.info(
            f"TestCaseDesignerNode - Executing with plan: {prep_res['function_plan_json_str'][:100]}..."
        )
        llm_model = prep_res["llm_models_config"].get("test_designer_llm", "gpt-4o")
        test_case_prompt = TEST_CASE_DESIGNER_PROMPT_TEMPLATE.format(**prep_res)
        response_str = call_llm(
            messages=[{"role": "user", "content": test_case_prompt}],
            model=llm_model,
            temperature=0.4,
            expect_json=True,
        )
        response_json = SimpleJsonOutputParser().parse(response_str)
        if response_json.get("error"):
            return {
                "error": "TC LLM failed",
                "details": response_json.get("raw_text", response_str),
            }
        test_cases = response_json.get("test_cases")
        if not test_cases or not isinstance(test_cases, list):
            return {"error": "LLM no valid test_cases list"}
        valid_test_cases = []
        planned_desc = json.loads(prep_res["function_plan_json_str"])
        for tc in test_cases:
            if (
                isinstance(tc, dict)
                and "inputs" in tc
                and "expected_output" in tc
                and "description" in tc
            ):
                if isinstance(tc["inputs"], list):
                    tc["inputs"] = tuple(tc["inputs"])
                elif not isinstance(tc["inputs"], tuple):
                    tc["inputs"] = (tc["inputs"],)
                tc["target_file"] = (
                    tc.get("target_file")
                    or planned_desc.get("target_file")
                    or planned_desc.get("entry_point_file", "main.py")
                )
                tc["target_function"] = (
                    tc.get("target_function")
                    or planned_desc.get("component_name")
                    or planned_desc.get("main_function_to_test", "unknown_function")
                )
                valid_test_cases.append(tc)
            else:
                logger.warning(f"Skipping malformed test case: {tc}")
        if not valid_test_cases:
            return {"error": "No valid test cases generated"}
        return valid_test_cases

    def post(
        self,
        shared: Dict[str, Any],
        prep_res: Dict[str, Any],
        exec_res: Optional[List[Dict[str, Any]]],
    ):
        logger.info("TestCaseDesignerNode - Post")
        if isinstance(exec_res, dict) and exec_res.get("error"):
            shared["current_error_message"] = (
                f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            )
            shared["generated_test_cases"] = []
            return "error_encountered"
        shared["generated_test_cases"] = exec_res
        shared["current_test_case_index"] = 0
        shared["all_tests_passed"] = False
        shared["test_results_summary"] = []
        return "tests_ready"
