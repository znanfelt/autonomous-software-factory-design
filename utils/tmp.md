You're right, that's a common challenge with LLMs. Even with explicit instructions, they can sometimes default to a simpler interpretation or "forget" parts of a complex prompt, especially if one part of the request (like detailing the `fetch_text` function) becomes the dominant focus.

Here's what's likely happening and how we can adjust the prompts and potentially the flow logic to better guide the LLM towards a multi-file output:

**Analysis of the Output:**

*   **`planned_task_description` focuses on `fetch_text`:** The LLM in the `ArchitectPlannerNode` seems to have focused its detailed plan (`planned_task_description`) on the `fetch_text` function within `scraper_utils.py`. This is good for that specific component.
*   **`suggested_project_outline` mentions both files:** This is positive! The planner did acknowledge the multi-file request here: `[{'file_name': 'scraper_utils.py', 'purpose': "Contains the web scraper utility function 'fetch_text' to extract main text content from a given URL."}, {'file_name': 'app.py', 'purpose': "Main script to use the scraper utility and save content."}]`.
*   **`DeveloperNode` latched onto the detailed component:** The `DeveloperNode` received the `planned_task_description` (which was only about `fetch_text`) and likely the `suggested_project_outline`. However, the `DEVELOPER_CODEGEN_PROMPT_TEMPLATE` might be more heavily weighted by the `planned_task_description`. If the prompt asks it to "implement the function described in `planned_task_description`" and also "consider the project outline", it might prioritize the former.

**Refinement Strategies:**

**1. Modify `DEVELOPER_CODEGEN_PROMPT_TEMPLATE` to Emphasize the Project Structure:**

   The current prompt for the developer might be too focused on the `planned_task_description`. We need to make it explicitly build *all files* mentioned in the `suggested_project_outline` and use the `planned_task_description` as the spec for the *main component* within that structure.

   Here's a revised `DEVELOPER_CODEGEN_PROMPT_TEMPLATE`:

   ```python
   # utils/prompts.py

   # ... (other prompts remain the same) ...

   DEVELOPER_CODEGEN_PROMPT_TEMPLATE = """
   You are an expert Python coding assistant. Your task is to generate all files for a Python project.

   Overall Project Plan & Main Component Specification:
   {planned_task_description_json_str} 

   Suggested Project File Structure & Purposes:
   {suggested_project_outline_json_str}

   Planner Notes: {planner_notes}

   Consult the Coding Standards.
   --- BEGIN CODING STANDARDS ---
   {coding_standards_context}
   --- END CODING STANDARDS ---

   LATEST FEEDBACK TO ADDRESS (if any):
   Critique: {critique_message}
   --- END LATEST FEEDBACK ---

   Full Feedback History (for context, address any unresolved issues from here too):
   {full_feedback_history}

   Based on the **Suggested Project File Structure**, the **Overall Project Plan**, and ALL **feedback**, write or revise the Python code for ALL files in the project.
   The `planned_task_description` details the main component (function or class) which should typically reside in the file specified as `target_file` within that description, or in the `entry_point_file` if specified in the project structure.
   Ensure any necessary imports between your generated files are correct (e.g., if 'app.py' needs to import from 'utils.py').
   Include concise docstrings for all functions/classes.

   Output ONLY a valid JSON object representing the complete project structure. The JSON object must have a key "files" which is a list of file objects. Each file object must have "name" (string, e.g., "main.py") and "content" (string, the Python code for that file).
   If the plan or outline suggests an entry point or a main function to test, include "entry_point_file" and "main_function_to_test" keys at the root of your JSON response.

   Example for a two-file project:
   ```json
   {{
     "files": [
       {{
         "name": "app.py",
         "content": "from scraper_utils import fetch_text\\n\\ndef run_scraper():\\n  urls = [\\'http://example.com\\']\\n  for url in urls:\\n    text = fetch_text(url)\\n    if text:\\n      domain = url.split('//')[-1].split('/')[0].replace('.', '_')\\n      with open(f'{domain}_content.txt', 'w') as f:\\n        f.write(text)\\n      print(f'Saved content from {url}')\\n    else:\\n      print(f'Failed to fetch from {url}')\\n\\nif __name__ == '__main__':\\n  run_scraper()"
       }},
       {{
         "name": "scraper_utils.py",
         "content": "import requests\\nfrom bs4 import BeautifulSoup\\n\\ndef fetch_text(url: str) -> str | None:\\n  \\\"\\\"\\\"Fetches and extracts main text from a URL.\\\"\\\"\\\"\\n  try:\\n    response = requests.get(url, timeout=10)\\n    response.raise_for_status()\\n    soup = BeautifulSoup(response.content, 'html.parser')\\n    # Simple text extraction, can be improved\\n    paragraphs = soup.find_all('p')\\n    return '\\n'.join([p.get_text() for p in paragraphs])\\n  except requests.RequestException as e:\\n    print(f'Error fetching {{url}}: {{e}}')\\n    return None"
       }}
     ],
     "entry_point_file": "app.py",
     "main_function_to_test": "run_scraper" 
   }}
   ```
   Ensure all code is within the "content" field of each file object. Do not use markdown code blocks for the Python code itself within the JSON string values.
   Please ensure your entire response is a single JSON object.
   """
   # ... (other prompts remain the same) ...
   ```

   **Changes Made:**
    *   Added `Suggested Project File Structure: {suggested_project_outline_json_str}` to the input.
    *   Explicitly instructed the LLM to "generate code for ALL files in the project" based on the `suggested_project_outline`.
    *   Clarified that `planned_task_description` details the *main component*.
    *   Emphasized correct imports between generated files.
    *   Updated the multi-file example to be more relevant to the scraper task.

**2. Modify `DeveloperNode.prep` to pass `suggested_project_outline`:**

   The `DeveloperNode` needs to receive this outline.

   ```python
   # nodes.py
   # ... (other imports and SimpleJsonOutputParser remain the same) ...

   class DeveloperNode(Node):
       def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
           logger.info("Entering DeveloperNode - Prep")
           planned_task_desc_obj = shared.get("planned_task_description")
           suggested_project_outline_obj = shared.get("suggested_project_outline") # New

           if not isinstance(planned_task_desc_obj, dict):
               logger.error("DeveloperNode: planned_task_description is not a dict or is missing.")
               return {"error": "Planned task description (object) missing."}
           # suggested_project_outline is optional, might be None or empty list for single-file projects
           if suggested_project_outline_obj and not isinstance(suggested_project_outline_obj, list):
                logger.warning("DeveloperNode: suggested_project_outline is not a list. Will be ignored by prompt.")
                suggested_project_outline_obj = []


           return {
               "planned_task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
               "suggested_project_outline_json_str": json.dumps(suggested_project_outline_obj or [], indent=2), # New, ensure it's a JSON list string
               "planner_notes": shared.get("planner_notes", "N/A"),
               "coding_standards_context": shared.get("coding_standards_context", "N/A"),
               "critique_feedback": shared.get("critique_feedback", "N/A (first attempt or no critique)"),
               "feedback_history": "\n".join([f"- {item}" for item in shared.get("feedback_history", [])]) or "No prior feedback.",
               "llm_models_config": shared.get("llm_models_config", {})
           }
       # ... (exec and post methods remain the same as they already handle project_structure dict) ...
   # ... (other nodes remain the same for now) ...
   ```
   **Changes Made:**
    *   Added `suggested_project_outline_obj` to `prep`.
    *   Passed it as `suggested_project_outline_json_str` (serialized to JSON string) to `exec` for the prompt.

**3. Ensure `ArchitectPlannerNode` correctly populates `suggested_project_outline` in `shared` state:**

   The `ArchitectPlannerNode.post` method already sets `shared["suggested_project_outline"] = planned_output.get("suggested_project_structure")`. This should be correct if the LLM (Planner) returns this key. We should double-check the `PLANNER_CODEGEN_PROMPT_TEMPLATE` ensures this key (`suggested_project_structure`) is output by the LLM.

   Looking at `PLANNER_CODEGEN_PROMPT_TEMPLATE`:
   ```python
   # ... (part of PLANNER_CODEGEN_PROMPT_TEMPLATE)
   Output ONLY a valid JSON object with the following keys:
   - "planned_task_description": A detailed description of the *main component* ...
   - "suggested_project_structure": (Optional) A list of dicts describing files ...
   - "entry_point_file": (Optional, if multi-file) ...
   - "main_function_to_test": (Optional) ...
   - "planner_notes": ...
   - "clarification_questions": An empty list `[]` ...
   ```
   This looks correct. The planner *can* output `suggested_project_structure`. The issue might be that it didn't for Prompt 1, or the DeveloperNode didn't use it.

**Why the previous attempt might have failed and how these changes help:**

*   **Prompt Weighting:** LLMs can sometimes focus on the most detailed part of a prompt. If `planned_task_description` was very specific about `fetch_text`, and `suggested_project_outline` was just a brief list, the `DeveloperNode` might have prioritized implementing the former and overlooked creating the multi-file structure. The revised `DEVELOPER_CODEGEN_PROMPT_TEMPLATE` now explicitly asks it to build *all files* from the `suggested_project_outline_json_str` and uses `planned_task_description_json_str` as the spec for the main component within that structure.
*   **Explicit Instruction for Multi-File:** The new developer prompt is more direct in asking for a multi-file JSON output and providing a relevant example.

**Next Steps After These Prompt/Node Changes:**

1.  **Test with Prompt 1 again.** See if it now generates two files (`scraper_utils.py` and `app.py`).
2.  **If it still generates one file:**
    *   **Examine Planner Output:** Check the exact `planned_task_description` and `suggested_project_outline` generated by the `ArchitectPlannerNode` for Prompt 1.
        *   Is `suggested_project_outline` being correctly populated by the planner LLM? If not, the `PLANNER_CODEGEN_PROMPT_TEMPLATE` might need to be even more forceful about generating this outline if the architect suggested a multi-file project.
        *   Is `planned_task_description` too heavily focused on just one file, making it seem like the *only* thing to build? If so, the planner might need to make `planned_task_description` describe the *overall project goal* and then use `suggested_project_structure` to detail individual files and their main components. This is a more significant shift in how the planner works.
    *   **Simplify Developer Task:** As a debugging step, if the planner *is* correctly outputting a multi-file structure, try giving a very simple, hardcoded multi-file plan directly to the `DeveloperNode` (bypassing the planner) to see if it can generate the multi-file JSON structure. This isolates if the issue is with the planner's output or the developer's ability to follow the multi-file instruction.
    *   **Temperature:** For code generation tasks requiring strict adherence to structure, lower temperatures (e.g., 0.0-0.2) for the `DeveloperNode`'s LLM call are generally better.
    *   **Consider a "ProjectBuilderNode":** If the developer consistently struggles with the multi-file JSON, you could break it down further:
        *   `PlannerNode` outputs a list of files and high-level purpose for each.
        *   A `FileCoderNode (BatchNode)` iterates through this list. For each file, it calls an LLM to generate *just that file's content*.
        *   An `AggregatorNode` then assembles these into the project structure. This adds complexity but gives the LLM smaller, more focused coding tasks.

Let's try with the updated `utils/prompts.py` and `nodes.py` first.

Here's the full `utils/prompts.py` again with the change highlighted:

```python
# utils/prompts.py

# --- ARCHITECT PROMPT ---
ARCHITECT_PROMPT_TEMPLATE = """
You are a Senior Software Architect. Your task is to make high-level technical decisions for a user's software request.
Consider the Architectural Principles provided below.

--- BEGIN ARCHITECTURAL PRINCIPLES ---
{architectural_principles_context}
--- END ARCHITECTURAL PRINCIPLES ---

User Request: "{user_request}"

Based on this, output ONLY a valid JSON object with the following keys:
- "chosen_language": Always "python" for this MVP.
- "framework_hint": Always "standard_library" for this MVP.
- "complexity_assessment": A brief assessment (e.g., "simple_function", "small_multi_file_project").
- "high_level_notes": Brief notes (1-2 sentences) for the planner. If the request implies multiple interacting components or a small utility with helper functions, suggest a multi-file structure might be appropriate (e.g., 'main.py' and 'utils.py').
Please ensure your entire response is a single JSON object.
"""

# --- PLANNER PROMPTS ---
PLANNER_CLARIFICATION_PROMPT_TEMPLATE = """
You are an expert Requirements Analyst and Planner.
Architect Decision: {architect_decision_json_str}

Current User Request (potentially refined): "{user_request_to_process}"

Consult the Planning Guidelines.
--- BEGIN PLANNING GUIDELINES ---
{planning_guidelines_context}
--- END PLANNING GUIDELINES ---

The current request seems ambiguous or incomplete for direct code generation.
Identify up to 3 specific, concise questions to ask the user to clarify the requirements for the primary software component.
If a multi-file project was suggested by the architect, your questions can also touch upon how different parts of the desired functionality could be organized.
Focus on the main component's name, parameters (names, types, order), return type, and core behavior.
Output ONLY a valid JSON object with one key:
- "clarification_questions": A list of strings, where each string is a question for the user.
  Example: {{"clarification_questions": ["What should the main function be named?", "What are its input parameters and their types?", "If a helper utility is needed, what should it do?"]}}
Please ensure your entire response is a single JSON object.
"""

PLANNER_CODEGEN_PROMPT_TEMPLATE = """
You are an expert Requirements Analyst and Planner.
Architect Decision: {architect_decision_json_str}

Current User Request (refined and deemed clear): "{user_request_to_process}"

Consult the Planning Guidelines.
--- BEGIN PLANNING GUIDELINES ---
{planning_guidelines_context}
--- END PLANNING GUIDELINES ---

Define a specific plan for the software component based on the request and architect's input.
Output ONLY a valid JSON object with the following keys:
- "planned_task_description": A detailed description of the *main component* to be built (primary function or class):
    - "component_type": "function" or "class".
    - "component_name": Suggested name (e.g., "calculate_sum", "DataProcessor").
    - "target_file": Suggested file name for this main component (e.g., "main.py", "core_logic.py").
    - "parameters": (For functions or class __init__) List of dicts: [{{"name": "param1", "type": "int"}}, ...]. Empty list if no params.
    - "return_type": (For functions or main methods) e.g., "int", "str", "list[int]", "None".
    - "core_behavior": Detailed description of what this main component should do.
- "suggested_project_structure": (Optional) A list of dicts describing files if a multi-file project is appropriate. Each dict: {{"file_name": "e.g., utils.py", "purpose": "Briefly describe this file's role"}}. If a single file, this can be an empty list or omitted.
- "entry_point_file": (Optional, if multi-file) The name of the file that acts as the main entry point for testing or execution.
- "main_function_to_test": (Optional) The name of the primary function or method within the entry_point_file that should be the focus of initial tests.
- "planner_notes": Any brief, critical notes for the developer (1-2 sentences), e.g., "Ensure helper functions in utils.py are imported correctly in main.py."
- "clarification_questions": An empty list `[]` as the request is now considered clear.
Please ensure your entire response is a single JSON object.
"""

# --- DEVELOPER PROMPT (Updated) ---
DEVELOPER_CODEGEN_PROMPT_TEMPLATE = """
You are an expert Python coding assistant. Your task is to generate all files for a Python project.

Overall Project Plan & Main Component Specification:
{planned_task_description_json_str} 

Suggested Project File Structure & Purposes:
{suggested_project_outline_json_str}

Planner Notes: {planner_notes}

Consult the Coding Standards.
--- BEGIN CODING STANDARDS ---
{coding_standards_context}
--- END CODING STANDARDS ---

LATEST FEEDBACK TO ADDRESS (if any):
Critique: {critique_message}
--- END LATEST FEEDBACK ---

Full Feedback History (for context, address any unresolved issues from here too):
{full_feedback_history}

Based on the **Suggested Project File Structure**, the **Overall Project Plan**, and ALL **feedback**, write or revise the Python code for ALL files in the project.
The `planned_task_description` details the main component (function or class) which should typically reside in the file specified as `target_file` within that description, or in the `entry_point_file` if specified in the project structure.
Ensure any necessary imports between your generated files are correct (e.g., if 'app.py' needs to import from 'utils.py').
Include concise docstrings for all functions/classes.

Output ONLY a valid JSON object representing the complete project structure. The JSON object must have a key "files" which is a list of file objects. Each file object must have "name" (string, e.g., "main.py") and "content" (string, the Python code for that file).
If the plan or outline suggests an entry point or a main function to test, include "entry_point_file" and "main_function_to_test" keys at the root of your JSON response.

Example for a two-file project:
```json
{{
  "files": [
    {{
      "name": "app.py",
      "content": "from scraper_utils import fetch_text\\n\\ndef run_scraper():\\n  urls = [\\'http://example.com\\']\\n  for url in urls:\\n    text = fetch_text(url)\\n    if text:\\n      domain = url.split('//')[-1].split('/')[0].replace('.', '_')\\n      with open(f'{{domain}}_content.txt', 'w') as f:\\n        f.write(text)\\n      print(f'Saved content from {{url}}')\\n    else:\\n      print(f'Failed to fetch from {{url}}')\\n\\nif __name__ == '__main__':\\n  run_scraper()"
    }},
    {{
      "name": "scraper_utils.py",
      "content": "import requests\\nfrom bs4 import BeautifulSoup\\n\\ndef fetch_text(url: str) -> str | None:\\n  \\\"\\\"\\\"Fetches and extracts main text from a URL.\\\"\\\"\\\"\\n  try:\\n    response = requests.get(url, timeout=10)\\n    response.raise_for_status()\\n    soup = BeautifulSoup(response.content, 'html.parser')\\n    # Simple text extraction, can be improved\\n    paragraphs = soup.find_all('p')\\n    return '\\\n'.join([p.get_text() for p in paragraphs])\\n  except requests.RequestException as e:\\n    print(f'Error fetching {{url}}: {{e}}')\\n    return None"
    }}
  ],
  "entry_point_file": "app.py",
  "main_function_to_test": "run_scraper" 
}}
```
Ensure all code is within the "content" field of each file object. Do not use markdown code blocks for the Python code itself within the JSON string values.
Please ensure your entire response is a single JSON object.
"""

# --- TEST CASE DESIGNER PROMPT ---
TEST_CASE_DESIGNER_PROMPT_TEMPLATE = """
You are a Test Case Designer.
Function/Component Plan:
{function_plan_json_str} 
Planner Notes (for context): {planner_notes}

Your task is to create 2 to 3 diverse test cases for the main Python component described in the plan (typically specified by "component_name" and "target_file" in the plan, or by "main_function_to_test" and "entry_point_file").
Each test case should be a JSON object with:
1. "target_file": The name of the Python file containing the function/method to test (e.g., "main.py").
2. "target_function": The name of the function or method to test (e.g., "process_data").
3. "inputs": A JSON tuple of input values for the function (e.g., `[1, 2]` for two args, `["hello"]` for one string arg, `[]` for no args).
4. "expected_output": The expected output when the function is called with these inputs.
5. "description": A brief (1-sentence) explanation of what this test case covers.

Consider typical cases and simple edge cases.
Output ONLY a valid JSON object with a single key "test_cases", which is a list of these test case objects.

Example for a function `def process_data(x: int) -> int:` in `main.py` that uses a helper `add_one` from `utils.py`:
```json
{{
  "test_cases": [
    {{
      "target_file": "main.py",
      "target_function": "process_data",
      "inputs": [5], 
      "expected_output": 6, 
      "description": "Test process_data with a positive integer."
    }},
    {{
      "target_file": "utils.py", 
      "target_function": "add_one", 
      "inputs": [0], 
      "expected_output": 1, 
      "description": "Test helper add_one with zero."
    }}
  ]
}}
```
Please ensure your entire response is a single JSON object.
"""

# --- VALIDATION PROMPT ---
VALIDATION_PROMPT_TEMPLATE = """
You are a Code Validation Agent.
Planned Task Description (for context): {task_description_json_str} 
Planner Notes (for context): {planner_notes}

Project Code to Validate (JSON structure with filenames and content):
```json
{project_structure_json_str}
```

Consult the Validation Rules.
--- BEGIN VALIDATION RULES ---
{validation_rules_context}
--- END VALIDATION RULES ---

Analyze the entire project structure and code against these rules.
Consider if the file structure makes sense for the plan, if imports between generated files are plausible, and if individual files adhere to standards.
Output ONLY a valid JSON object with two keys:
* "validation_passed": boolean (true if no issues, false if any issues are found).
* "issues_found": A list of strings, where each string describes a specific validation issue found (mention filename if applicable). Empty list if validation_passed is true.
Please ensure your entire response is a single JSON object.
"""

# --- CRITIQUE PROMPT ---
CRITIQUE_PROMPT_TEMPLATE = """
You are a Code Critique Agent.
Planned Task Description (for context): {task_description_json_str}
Planner Notes (for context): {planner_notes}

Project Code in Question (JSON structure with filenames and content):
```json
{project_structure_json_str}
```

Reason(s) for Critique:
Test Failure Message(s) (if any): {test_failure_message}
Validation Issues (if any): {validation_issues_list_str}
User Rejection Reason (if any): {user_rejection_reason}

Consult Debugging Tips if relevant.
--- BEGIN DEBUGGING TIPS ---
{debugging_tips_context}
--- END DEBUGGING TIPS ---

Based on ALL provided reasons, provide concise, constructive feedback for a developer (1-3 sentences per major issue).
Focus on the root cause and suggest specific areas for improvement across the project or in specific files. Do not rewrite the code yourself.
Output ONLY a valid JSON object with a single key "critique_feedback", which is a string containing your feedback.
Example: {{"critique_feedback": "In main.py, the function 'process_data' fails for empty lists. Add a check. In utils.py, 'helper_func' has an off-by-one error in the loop."}}
Please ensure your entire response is a single JSON object.
"""
```

And here is the updated `nodes.py` with the change to `DeveloperNode.prep`:

```python
# nodes.py
import logging
import json 
from typing import Any, Dict, List, Optional, Tuple, TypedDict
import re 

from pocketflow import Node
from utils.call_llm import call_llm
from utils.tools import extract_project_structure_from_llm, code_tester_tool # Updated
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
            match_md_json = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
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
                logger.error(f"JSON Parser: No JSON content identified for text: {text[:200]}...")
                return {"error": "JSON parsing failed: No JSON content identified", "raw_text": text}

            return json.loads(json_text_to_parse)
        except json.JSONDecodeError as e:
            raw_text_snippet = json_text_to_parse[:200] if json_text_to_parse else text[:200]
            logger.error(f"JSON Parsing Error: {e} in text snippet: {raw_text_snippet}...")
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
            architect_decision_json_str=json.dumps(arch_decision)
        )
        planner_response_str = call_llm(messages=[{"role": "user", "content": planner_codegen_prompt}], model=planner_llm_model, temperature=0.2, expect_json=True)
        planned_output = SimpleJsonOutputParser().parse(planner_response_str)

        if planned_output.get("error"):
            logger.error(f"Planner Codegen LLM error or parsing failed: {planned_output.get('error')}")
            return {"error": "Planner Codegen LLM failed", "details": planned_output.get("raw_text", planner_response_str), "architect_decision": arch_decision}

        if planned_output.get("planned_task_description") and not planned_output.get("clarification_questions"):
            logger.info(f"Planner created task description: {str(planned_output['planned_task_description'])[:100]}...")
            return {"architect_decision": arch_decision, "planned_output": planned_output, "needs_clarification": False}

        logger.info("Planner determined request needs clarification or codegen plan was insufficient. Asking clarification questions.")
        planner_clar_prompt = PLANNER_CLARIFICATION_PROMPT_TEMPLATE.format(
             user_request_to_process=current_request,
             planning_guidelines_context=plan_guidelines_ctx,
             architect_decision_json_str=json.dumps(arch_decision)
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
            shared["planned_task_description"] = planned_output["planned_task_description"]
            shared["planner_notes"] = planned_output.get("planner_notes")
            shared["suggested_project_outline"] = planned_output.get("suggested_project_structure")
            shared["developer_task_description"] = json.dumps(planned_output["planned_task_description"], indent=2) 
            shared["clarification_questions_for_user"] = None 
            logger.debug("Returning 'plan_ready_for_code'")
            return "plan_ready_for_code"
        else:
            error_msg = "Planner failed to produce a plan or clarification questions."
            logger.error(error_msg + f" LLM output: {planned_output}")
            shared["current_error_message"] = error_msg
            return "error_encountered"

class DeveloperNode(Node): # Updated prep
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering DeveloperNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        suggested_project_outline_obj = shared.get("suggested_project_outline") 

        if not isinstance(planned_task_desc_obj, dict):
            logger.error("DeveloperNode: planned_task_description is not a dict or is missing.")
            return {"error": "Planned task description (object) missing."}
        
        # suggested_project_outline is optional, can be None or empty list
        if suggested_project_outline_obj and not isinstance(suggested_project_outline_obj, list):
            logger.warning("DeveloperNode: suggested_project_outline is not a list. Will pass as empty list to prompt.")
            suggested_project_outline_obj = []
        
        return {
            "planned_task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "suggested_project_outline_json_str": json.dumps(suggested_project_outline_obj or [], indent=2),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "coding_standards_context": shared.get("coding_standards_context", "N/A"),
            "critique_feedback": shared.get("critique_feedback", "N/A (first attempt or no critique)"),
            "feedback_history": "\n".join([f"- {item}" for item in shared.get("feedback_history", [])]) or "No prior feedback.",
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if prep_res.get("error"):
            logger.error(f"DeveloperNode: Error from prep stage: {prep_res['error']}")
            return {"error": f"Prep error: {prep_res['error']}"}

        logger.info(f"DeveloperNode - Executing with task plan: {prep_res['planned_task_description_json_str'][:200]}...")
        llm_model = prep_res["llm_models_config"].get("developer_llm", "gpt-4o")
        
        dev_prompt = DEVELOPER_CODEGEN_PROMPT_TEMPLATE.format(
            planned_task_description_json_str=prep_res["planned_task_description_json_str"],
            suggested_project_outline_json_str=prep_res["suggested_project_outline_json_str"], # New
            planner_notes=prep_res["planner_notes"],
            coding_standards_context=prep_res["coding_standards_context"],
            critique_message=prep_res["critique_feedback"],
            full_feedback_history=prep_res["feedback_history"]
        )
        llm_response_str = call_llm(messages=[{"role": "user", "content": dev_prompt}], model=llm_model, temperature=0.1, expect_json=True)
        
        project_structure = SimpleJsonOutputParser().parse(llm_response_str)

        if project_structure.get("error"):
            logger.error(f"DeveloperNode: LLM error or failed to parse project structure JSON: {project_structure['error']}. Raw: {project_structure.get('raw_text','')[:200]}")
            return {"error": f"Could not parse LLM output for project structure. Details: {project_structure.get('error')}", "raw_llm_response": project_structure.get('raw_text', llm_response_str)}
        
        if not isinstance(project_structure, dict) or "files" not in project_structure or not isinstance(project_structure["files"], list):
            logger.error(f"DeveloperNode: Invalid project structure from LLM. Missing 'files' list. Got: {str(project_structure)[:200]}")
            return {"error": "LLM returned invalid project structure format.", "raw_llm_response": llm_response_str}

        return project_structure

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[Dict[str, Any]]):
        logger.info("DeveloperNode - Post")
        # refinement_count is now incremented by app.py before calling critique_refine_flow
        # If this node is part of initial_code_gen_flow, refinement_count will be 0 from shared.
        # If part of critique_refine_flow, app.py should have incremented it *before* calling this flow.
        # So, this node should reflect the attempt *number* based on refinement_count.
        current_attempt_number = shared.get("refinement_count", 0) + 1 # 1 for initial, 2 for first refinement, etc.


        if exec_res is None or exec_res.get("error"):
            error_detail = exec_res.get("details", exec_res.get("raw_llm_response", "Unknown error during code generation.")) if isinstance(exec_res, dict) else "Execution returned None"
            shared["current_error_message"] = f"Developer Error (Attempt {current_attempt_number}): {exec_res.get('error', 'Code generation failed')}. Details: {str(error_detail)[:200]}"
            shared["generated_project_structure"] = None 
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"DevAttempt {current_attempt_number}: Failed to generate/parse code. {shared['current_error_message']}")
            logger.error(f"DeveloperNode error: {shared['current_error_message']}")
            return "code_generation_failed"
        
        shared["generated_project_structure"] = exec_res
        logger.debug(f"Generated project structure (Attempt {current_attempt_number}): {json.dumps(exec_res, indent=2)[:300]}...")
        shared["critique_feedback"] = None # Reset critique after new code is generated
        shared["current_error_message"] = None
        return "code_ready_for_tests"

class TestCaseDesignerNode(Node):
    # ... (prep, exec, post remain largely the same as previous version, assuming prompts are updated)
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

    def exec(self, prep_res: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        if prep_res.get("error"): return prep_res 
        logger.info(f"TestCaseDesignerNode - Executing with plan: {prep_res['function_plan_json_str'][:200]}...")
        llm_model = prep_res["llm_models_config"].get("test_designer_llm", "gpt-4o") 
        test_case_prompt = TEST_CASE_DESIGNER_PROMPT_TEMPLATE.format(
            function_plan_json_str=prep_res["function_plan_json_str"],
            planner_notes=prep_res["planner_notes"]
        )
        response_str = call_llm(messages=[{"role": "user", "content": test_case_prompt}], model=llm_model, temperature=0.4, expect_json=True)
        response_json = SimpleJsonOutputParser().parse(response_str)
        if response_json.get("error"): return {"error": "TC LLM failed", "details": response_json.get("raw_text",response_str)}
        test_cases = response_json.get("test_cases")
        if not test_cases or not isinstance(test_cases, list): return {"error": "LLM no valid test_cases list"}
        
        valid_test_cases = []
        planned_desc = json.loads(prep_res["function_plan_json_str"])
        for tc in test_cases:
            if isinstance(tc, dict) and "inputs" in tc and "expected_output" in tc and "description" in tc:
                if isinstance(tc["inputs"], list): tc["inputs"] = tuple(tc["inputs"]) 
                elif not isinstance(tc["inputs"], tuple): tc["inputs"] = (tc["inputs"],)
                tc["target_file"] = tc.get("target_file") or planned_desc.get("target_file") or planned_desc.get("entry_point_file", "main.py")
                tc["target_function"] = tc.get("target_function") or planned_desc.get("component_name") or planned_desc.get("main_function_to_test", "unknown_function")
                valid_test_cases.append(tc)
            else: logger.warning(f"Skipping malformed test case: {tc}")
        if not valid_test_cases: return {"error": "No valid test cases generated"}
        return valid_test_cases

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[List[Dict[str, Any]]]):
        logger.info("TestCaseDesignerNode - Post")
        if isinstance(exec_res, dict) and exec_res.get("error"):
            shared["current_error_message"] = f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            shared["generated_test_cases"] = []
            return "error_encountered"
        shared["generated_test_cases"] = exec_res
        shared["current_test_case_index"] = 0; shared["all_tests_passed"] = False; shared["test_results_summary"] = [] 
        return "tests_ready"

class QANode(Node):
    # ... (prep, exec, post remain largely the same, code_tester_tool handles project_structure)
    def prep(self, shared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger.info("Entering QANode - Prep")
        project_structure = shared.get("generated_project_structure")
        test_cases = shared.get("generated_test_cases")
        current_idx = shared.get("current_test_case_index", 0)

        if not project_structure or not project_structure.get("files"): return {"error": "No project code"}
        if not test_cases or not isinstance(test_cases, list) or current_idx >= len(test_cases): return {"error": "No more/valid tests"}
        
        return {"project_structure": project_structure, "test_case": test_cases[current_idx]}

    def exec(self, prep_res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not prep_res or prep_res.get("error"):
            error_msg = prep_res.get("error") if prep_res else "Prep failed"
            return {"status": "error", "message": error_msg, "test_case": prep_res.get("test_case") if prep_res else None}

        project_structure = prep_res["project_structure"]
        test_case = prep_res["test_case"]
        # target_function and target_file are now expected inside test_case dict
        single_test_results = code_tester_tool(project_structure, [test_case]) # Pass project_structure
        if not single_test_results: return {"status": "error", "message": "Test tool malfunctioned.", "test_case": test_case}
        return single_test_results[0] 

    def post(self, shared: Dict[str, Any], prep_res: Optional[Dict[str, Any]], exec_res: Optional[Dict[str, Any]]):
        logger.info("QANode - Post")
        if not exec_res or exec_res.get("status") == "error": # Covers tool errors, compilation, runtime
            error_msg = exec_res.get("message", "QA exec failed.") if exec_res else "QA prep failed."
            shared["current_test_status"] = exec_res.get("status", "error") if exec_res else "error"
            shared["current_test_message"] = error_msg
            shared.setdefault("test_results_summary", []).append(exec_res or {"status":"error", "message":error_msg, "test_case": prep_res.get("test_case") if prep_res else {}})
            shared["all_tests_passed"] = False # Mark as failed
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"QA Error/Fail (DevAttempt {shared.get('refinement_count',0)} on test '{exec_res.get('test_case',{}).get('description','N/A')}'): {error_msg}")
            return "testing_error_or_done" # Proceed to validation/critique even on test error

        shared.setdefault("test_results_summary", []).append(exec_res)
        shared["current_test_status"] = exec_res["status"]
        shared["current_test_message"] = exec_res["message"]
        
        if exec_res["status"] != "success":
            shared["all_tests_passed"] = False
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"Test Failure (DevAttempt {shared.get('refinement_count',0)} on test '{exec_res['test_case'].get('description')}'): {exec_res['message']} (Actual: {exec_res.get('actual_output')})")
            # Don't return yet, run all tests

        shared["current_test_case_index"] = shared.get("current_test_case_index", 0) + 1
        
        if shared["current_test_case_index"] >= len(shared.get("generated_test_cases", [])):
            # All tests have run, now determine overall_tests_passed
            shared["all_tests_passed"] = all(res['status'] == 'success' for res in shared['test_results_summary'])
            logger.info(f"All tests run for version. Overall pass: {shared['all_tests_passed']}")
            return "testing_error_or_done" # Go to validation
        else:
            return "run_next_test" # Loop for next test

class ValidationNode(Node):
    # ... (prep, exec, post need to handle project_structure_json_str)
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering ValidationNode - Prep")
        planned_task_desc_obj = shared.get("planned_task_description")
        project_structure_obj = shared.get("generated_project_structure")

        if not isinstance(planned_task_desc_obj, dict): return {"error": "Plan missing for validation."}
        if not isinstance(project_structure_obj, dict) or not project_structure_obj.get("files"): return {"error": "Project structure missing for validation."}

        return {
            "project_structure_json_str": json.dumps(project_structure_obj, indent=2),
            "task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "validation_rules_context": shared.get("validation_rules_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        if prep_res.get("error"): return {"validation_passed": False, "issues_found": [prep_res['error']]}
        
        logger.info(f"ValidationNode - Executing for plan: {prep_res['task_description_json_str'][:100]}...")
        llm_model = prep_res["llm_models_config"].get("validation_llm", "gpt-4o")
        val_prompt = VALIDATION_PROMPT_TEMPLATE.format(**prep_res) # Pass all prep_res keys
        response_str = call_llm(messages=[{"role": "user", "content": val_prompt}], model=llm_model, temperature=0.1, expect_json=True)
        validation_result = SimpleJsonOutputParser().parse(response_str)
        if validation_result.get("error"):
            return {"validation_passed": False, "issues_found": [f"Validation LLM failed: {validation_result['error']}"], "details": validation_result.get("raw_text", response_str)}
        return validation_result

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        logger.info("ValidationNode - Post")
        # (Post method logic for updating shared state same as before)
        if isinstance(exec_res, dict) and "validation_passed" in exec_res:
            shared["validation_status"] = "pass" if exec_res["validation_passed"] and not exec_res.get("issues_found") else "fail"
            shared["validation_issues"] = exec_res.get("issues_found", [])
            if not isinstance(shared["validation_issues"], list): shared["validation_issues"] = [str(shared["validation_issues"])] if shared["validation_issues"] else []
            if exec_res.get("validation_passed") and shared["validation_issues"]:
                 shared["validation_status"] = "fail"; shared["validation_issues"].append("Internal Consistency: LLM reported pass but listed issues.")
        else: 
            shared["validation_status"] = "error"; shared["validation_issues"] = [str(exec_res.get("details", "Validation agent malformed output."))]
        logger.debug(f"Validation status: {shared['validation_status']}, Issues: {shared['validation_issues']}")
        if shared["validation_status"] != "pass" and shared["validation_issues"]:
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"Validation Issues (DevAttempt {shared.get('refinement_count',0)}): {'; '.join(shared['validation_issues'])}")
        return "validation_done"


class CritiqueNode(Node):
    # ... (prep, exec, post need to handle project_structure_json_str)
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering CritiqueNode - Prep")
        # (Similar to ValidationNode.prep, ensure objects are dicts before json.dumps)
        planned_task_desc_obj = shared.get("planned_task_description")
        project_structure_obj = shared.get("generated_project_structure")
        if not isinstance(planned_task_desc_obj, dict): return {"error": "Plan missing for critique."}
        if not isinstance(project_structure_obj, dict) or not project_structure_obj.get("files"): return {"error": "Project structure missing for critique."}

        return {
            "task_description_json_str": json.dumps(planned_task_desc_obj, indent=2),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "project_structure_json_str": json.dumps(project_structure_obj, indent=2),
            "test_failure_message": shared.get("current_test_message", "N/A"), # current_test_message is set by QANode post
            "validation_issues_list_str": "; ".join(shared.get("validation_issues", [])) if shared.get("validation_issues") else "N/A",
            "user_rejection_reason": shared.get("user_rejection_reason", "N/A"),
            "debugging_tips_context": shared.get("debugging_tips_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> str:
        if prep_res.get("error"): return f"Error in critique prep: {prep_res['error']}"
        logger.info(f"CritiqueNode - Executing...")
        llm_model = prep_res["llm_models_config"].get("critique_llm", "gpt-4o-mini")
        critique_prompt = CRITIQUE_PROMPT_TEMPLATE.format(**prep_res)
        response_str = call_llm(messages=[{"role": "user", "content": critique_prompt}], model=llm_model, temperature=0.25, expect_json=True)
        critique_json = SimpleJsonOutputParser().parse(response_str)
        if critique_json.get("error"): return f"Critique LLM error: {critique_json['error']}. Details: {critique_json.get('raw_text', response_str)[:100]}"
        return critique_json.get("critique_feedback", "Critique LLM no feedback.")

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: str):
        logger.info("CritiqueNode - Post")
        shared["critique_feedback"] = exec_res
        logger.debug(f"Generated critique: {exec_res}")
        return "refine_code" 

class PackageNode(Node):
    # ... (prep, exec, post need to handle generated_project_structure)
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering PackageNode - Prep")
        project_structure = shared.get("generated_project_structure")
        planned_desc = shared.get("planned_task_description")
        if not isinstance(project_structure, dict) or not project_structure.get("files"): return {"error": "Project structure missing for packaging."}
        if not isinstance(planned_desc, dict): return {"error": "Plan missing for packaging."}
        return {"generated_project_structure": project_structure, "planned_task_description": planned_desc}

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        if prep_res.get("error"): return prep_res
        logger.info("PackageNode - Executing")
        project_structure = prep_res["generated_project_structure"]
        plan = prep_res["planned_task_description"]
        main_component_name = plan.get("component_name", "unnamed_component")
        
        packaged_info = {
            "project_files": project_structure.get("files", []),
            "entry_point": project_structure.get("entry_point_file", "N/A"),
            "main_component_details": plan # Include the full plan for the main component
        }
        handoff_summary = f"Packaged project for component: '{main_component_name}'."
        return {"packaged_artifacts_info": packaged_info, "handoff_summary": handoff_summary, "main_component_name": main_component_name}

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        logger.info("PackageNode - Post")
        if exec_res.get("error"):
            shared["current_error_message"] = f"Packaging Error: {exec_res['error']}"; shared["packaged_artifacts_info"] = None; shared["handoff_summary"] = "Packaging failed."
            return "error_encountered"
        shared["packaged_artifacts_info"] = exec_res.get("packaged_artifacts_info")
        shared["handoff_summary"] = exec_res.get("handoff_summary")
        return "done"
```

**Summary of Changes in `nodes.py`:**

1.  **`SimpleJsonOutputParser` Update:** Made it slightly more robust in finding JSON blocks, trying ````json ... ````, then ```` ... ````, then attempting to parse the whole string if it looks like a JSON object.
2.  **`ArchitectPlannerNode`:**
    *   `exec`: Now expects `architect_decision` (from the architect LLM call) and `planned_output` (from the planner LLM call for codegen or clarification) to be JSON strings that are parsed into dicts. Passes `architect_decision_json_str` to planner prompts.
    *   `post`: Updates `shared` state with the structured `planned_task_description` (dict) and `suggested_project_outline` (list of dicts). `developer_task_description` is created as a JSON string dump of `planned_task_description` for the DeveloperNode.
3.  **`DeveloperNode`:**
    *   `prep`: Now takes `planned_task_description_json_str` and `suggested_project_outline_json_str` to format into the `DEVELOPER_CODEGEN_PROMPT_TEMPLATE`.
    *   `exec`: Expects the LLM (via `call_llm`) to return a JSON string representing the project structure. It uses `SimpleJsonOutputParser().parse()` and then validates the basic structure (e.g., presence of a "files" list).
    *   `post`: `shared["generated_project_structure"]` now stores the dictionary parsed from the LLM's JSON output. Error handling for parsing or invalid structure.
4.  **`TestCaseDesignerNode`:**
    *   `prep`: `planned_task_description` is a dict. `function_plan_json_str` is created from it for the prompt.
    *   `exec`: Expects LLM to return JSON string for `test_cases`. Parses it. Now also ensures `target_file` and `target_function` are present in each test case, falling back to values from `planned_task_description` if the LLM omits them.
5.  **`QANode`:**
    *   `prep`: Takes `generated_project_structure` (dict).
    *   `exec`: Calls `code_tester_tool` with the `project_structure` dict.
    *   `post`: Handles test results. Appends detailed failure info to `feedback_history` for the `CritiqueNode`.
6.  **`ValidationNode`:**
    *   `prep`: Takes `generated_project_structure` (dict) and `planned_task_description` (dict), stringifies them to JSON for the prompt.
    *   `exec`: Expects LLM to return JSON for validation results.
    *   `post`: Appends validation issues to `feedback_history` if validation fails.
7.  **`CritiqueNode`:**
    *   `prep`: Similar to `ValidationNode`, takes project structure and plan as dicts and stringifies them for the prompt. `validation_issues` are joined into `validation_issues_list_str`.
    *   `exec`: Expects LLM to return JSON for critique.
8.  **`PackageNode`:**
    *   `prep`: Takes `generated_project_structure` (dict) and `planned_task_description` (dict).
    *   `exec`: Now "packages" the project structure dictionary.

The overall theme is that data like plans and code (which can now be multi-file) are primarily handled as Python dictionaries within the `shared` state and node logic, but are serialized to JSON strings when being formatted into LLM prompts or when the LLM is expected to return them in a structured way. The `SimpleJsonOutputParser` and `extract_project_structure_from_llm` (which might be redundant now if DeveloperNode always gets JSON) are key for this. The `call_llm` function was also updated to expect JSON for most calls.

The system is now much more aligned with handling multi-file project generation.
The final piece is `app.py` and then `Dockerfile`/`docker-compose.yml`. Let's proceed.