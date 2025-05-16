import re
import logging
from typing import Any, List, Dict, Tuple

logger = logging.getLogger(__name__)

def extract_python_code(llm_output: str) -> str | None:
    """Extracts Python code from a string, expecting markdown code blocks."""
    if not isinstance(llm_output, str):
        logger.warning(f"extract_python_code received non-string input: {type(llm_output)}")
        return None
        
    # Pattern to find ```python ... ```
    match_python = re.search(r"```python\s*(.*?)\s*```", llm_output, re.DOTALL)
    if match_python:
        return match_python.group(1).strip()
    
    # Fallback pattern for ``` ... ``` if python specifier is missing
    match_generic = re.search(r"```\s*(.*?)\s*```", llm_output, re.DOTALL)
    if match_generic:
        logger.warning("extract_python_code: Found generic code block, assuming Python.")
        return match_generic.group(1).strip()
        
    logger.warning("extract_python_code: No Python code block found.")
    return None

def code_tester_tool(code_string: str, function_name: str, test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tests a Python function string against a list of test cases.
    Each test case is a dict: {"inputs": (arg1,), "expected_output": val, "description": "..."}
    Returns a list of result dicts.
    """
    results = []
    if not code_string:
        logger.error("code_tester_tool: No code string provided.")
        for tc in test_cases:
            results.append({
                "test_case": tc, "status": "error", "message": "No code provided to test.", "actual_output": None
            })
        return results

    try:
        # Create a scope for exec to run in
        scope = {'__builtins__': __builtins__} # Provide access to built-in functions
        exec(code_string, scope, scope) # Execute the code string in the defined scope
    except Exception as e:
        logger.error(f"code_tester_tool: Compilation/Import error in provided code: {e}", exc_info=True)
        for tc in test_cases:
            results.append({
                "test_case": tc, "status": "compilation_error", "message": f"Code compilation/import error: {e}", "actual_output": None
            })
        return results

    if function_name not in scope:
        logger.error(f"code_tester_tool: Function '{function_name}' not found in executed code.")
        for tc in test_cases:
            results.append({
                "test_case": tc, "status": "error", "message": f"Function '{function_name}' not defined in code.", "actual_output": None
            })
        return results

    func_to_test = scope[function_name]

    for test_case in test_cases:
        inputs = test_case.get("inputs", ()) # Default to empty tuple if not provided
        expected_output = test_case.get("expected_output")
        description = test_case.get("description", "Unnamed test")
        
        # Ensure inputs is a tuple
        if not isinstance(inputs, tuple):
            logger.warning(f"Test case '{description}' inputs not a tuple, wrapping: {inputs}")
            inputs = (inputs,)

        try:
            actual_output = func_to_test(*inputs)
            if actual_output == expected_output:
                results.append({"test_case": test_case, "status": "success", "actual_output": actual_output, "message": "Test passed."})
            else:
                results.append({"test_case": test_case, "status": "fail", "actual_output": actual_output, "message": f"Expected {expected_output}, got {actual_output}."})
        except Exception as e:
            logger.error(f"code_tester_tool: Runtime error during test '{description}': {e}", exc_info=True)
            results.append({"test_case": test_case, "status": "runtime_error", "actual_output": None, "message": f"Runtime error: {e}."})
            
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("--- Testing extract_python_code ---")
    test_llm_output_python = "Some text before\n```python\ndef greet(name):\n  return f'Hello, {name}!'\n```\nSome text after"
    extracted = extract_python_code(test_llm_output_python)
    print(f"Extracted: \n{extracted}")
    assert extracted == "def greet(name):\n  return f'Hello, {name}!'"

    test_llm_output_generic = "```\ndef add(x, y):\n  return x + y\n```"
    extracted_generic = extract_python_code(test_llm_output_generic)
    print(f"Extracted (generic): \n{extracted_generic}")
    assert extracted_generic == "def add(x, y):\n  return x + y"

    test_llm_output_no_code = "This is just plain text."
    extracted_none = extract_python_code(test_llm_output_no_code)
    print(f"Extracted (none): {extracted_none}")
    assert extracted_none is None

    print("\n--- Testing code_tester_tool ---")
    good_code = "def add(a, b):\n  return a + b"
    test_cases_add = [
        {"inputs": (2, 3), "expected_output": 5, "description": "Positive numbers"},
        {"inputs": (-1, 1), "expected_output": 0, "description": "Negative and positive"},
        {"inputs": (5, 0), "expected_output": 6, "description": "Intentional fail"} 
    ]
    results_add = code_tester_tool(good_code, "add", test_cases_add)
    print("Test results for 'add' function:")
    for res in results_add: print(res)
    assert results_add[0]["status"] == "success"
    assert results_add[1]["status"] == "success"
    assert results_add[2]["status"] == "fail"

    syntax_error_code = "def multiply(a, b):\n  retun a * b" # Syntax error 'retun'
    test_cases_multiply = [{"inputs": (2,3), "expected_output": 6, "description": "Multiply test"}]
    results_syntax_error = code_tester_tool(syntax_error_code, "multiply", test_cases_multiply)
    print("\nTest results for syntax error code:")
    for res in results_syntax_error: print(res)
    assert results_syntax_error[0]["status"] == "compilation_error"

    runtime_error_code = "def divide(a,b):\n return a/b"
    test_cases_divide = [{"inputs": (1,0), "expected_output": "Error", "description": "Division by zero"}]
    results_runtime_error = code_tester_tool(runtime_error_code, "divide", test_cases_divide)
    print("\nTest results for runtime error code:")
    for res in results_runtime_error: print(res)
    assert results_runtime_error[0]["status"] == "runtime_error"
    
    no_code_results = code_tester_tool("", "non_existent_func", test_cases_add)
    print("\nTest results for no code:")
    for res in no_code_results: print(res)
    assert no_code_results[0]["status"] == "error"
    assert "No code provided" in no_code_results[0]["message"]

    func_not_defined_code = "def some_other_func(): pass"
    results_func_not_defined = code_tester_tool(func_not_defined_code, "my_func", test_cases_add)
    print("\nTest results for function not defined:")
    for res in results_func_not_defined: print(res)
    assert results_func_not_defined[0]["status"] == "error"
    assert "not defined in code" in results_func_not_defined[0]["message"]
