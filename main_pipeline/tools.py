import re
import logging
from typing import Any

# Tool definitions and utility functions

def code_tester_tool(code_string: str, function_name: str, test_inputs: tuple, expected_output: Any) -> dict:
    """
    Test a Python function by executing the provided code string, calling the function with test inputs,
    and comparing the result to the expected output. Returns a dict with status and message.
    """
    if not code_string: return {"status": "compilation_error", "message": "No code provided."}
    try:
        scope = {'__builtins__': __builtins__}; exec(code_string, scope, scope)
        if function_name not in scope: return {"status": "compilation_error", "message": f"Function '{function_name}' not defined."}
        actual = scope[function_name](*test_inputs)
        if actual == expected_output: return {"status": "success", "message": "Test passed.", "actual_output": actual}
        return {"status": "test_fail", "message": f"Input: {test_inputs}, Expected: {expected_output}, Got: {actual}", "actual_output": actual}
    except Exception as e: 
        logging.error(f"Code tester tool runtime error: {e}", exc_info=False)
        return {"status": "runtime_error", "message": str(e)}


def extract_python_code(llm_output: str) -> str | None:
    match = re.search(r"```python\n(.*?)\n```", llm_output, re.DOTALL)
    if match: return match.group(1).strip()
    match = re.search(r"```\n(.*?)\n```", llm_output, re.DOTALL)
    if match: return match.group(1).strip()
    return None