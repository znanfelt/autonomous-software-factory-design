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
    - "return_type": (For functions or main methods) e.g., "int", "str", "None".
    - "core_behavior": Detailed description of what this main component should do.
- "suggested_project_structure": (Optional) A list of dicts describing files if a multi-file project is appropriate. Each dict: {{"file_name": "e.g., utils.py", "purpose": "Briefly describe this file's role"}}. If a single file, this can be an empty list or omitted.
- "entry_point_file": (Optional, if multi-file) The name of the file that acts as the main entry point for testing or execution.
- "main_function_to_test": (Optional) The name of the primary function or method within the entry_point_file that should be the focus of initial tests.
- "planner_notes": Any brief, critical notes for the developer (1-2 sentences), e.g., "Ensure helper functions in utils.py are imported correctly in main.py."
- "clarification_questions": An empty list `[]` as the request is now considered clear.
Please ensure your entire response is a single JSON object.
"""

# --- DEVELOPER PROMPT ---
DEVELOPER_CODEGEN_PROMPT_TEMPLATE = """
You are an expert Python coding assistant.
Overall Task Description & Plan:
{planned_task_description_json_str} 
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

Based on the task, plan, notes, and ALL feedback (prioritizing the latest), write or revise the Python project.
Each generated file must include a concise docstring for functions/classes.
Output ONLY a valid JSON object representing the project structure. The JSON object must have a key "files" which is a list of file objects. Each file object must have "name" (string, e.g., "main.py") and "content" (string, the Python code for that file).
If the plan suggests an entry point or a main function to test, include "entry_point_file" and "main_function_to_test" keys at the root of your JSON response.

Example for a two-file project:
```json
{{
  "files": [
    {{
      "name": "main.py",
      "content": "from utils import add_one\\n\\ndef process_data(x):\\n  \\\"\\\"\\\"Processes data by adding one.\\\"\\\"\\\"\\n  return add_one(x)"
    }},
    {{
      "name": "utils.py",
      "content": "def add_one(n):\\n  \\\"\\\"\\\"Helper to add one to a number.\\\"\\\"\\\"\\n  return n + 1"
    }}
  ],
  "entry_point_file": "main.py",
  "main_function_to_test": "process_data"
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