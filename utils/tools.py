# utils/tools.py
import re
import json
import logging
import os
import tempfile
import shutil
import sys
from typing import Any, List, Dict, Tuple

logger = logging.getLogger(__name__)

def extract_python_code(llm_output: str) -> str | None:
    """Extracts Python code from a string, expecting markdown code blocks for a single file."""
    if not isinstance(llm_output, str):
        logger.warning(f"extract_python_code received non-string input: {type(llm_output)}")
        return None
        
    match_python = re.search(r"```python\s*(.*?)\s*```", llm_output, re.DOTALL)
    if match_python:
        return match_python.group(1).strip()
    
    match_generic = re.search(r"```\s*(.*?)\s*```", llm_output, re.DOTALL)
    if match_generic:
        logger.warning("extract_python_code: Found generic code block, assuming Python for single file extraction.")
        return match_generic.group(1).strip()
        
    logger.warning("extract_python_code: No Python code block found for single file extraction.")
    return None

def extract_project_structure_from_llm(llm_output: str) -> Dict[str, Any] | None:
    """
    Extracts a project structure (multiple files) from LLM output.
    Expects LLM to output a JSON object, possibly within markdown triple backticks.
    The JSON should conform to:
    {
        "files": [
            {"name": "file1.py", "content": "...", "purpose": "..."},
            ...
        ],
        "entry_point_file": "main.py",  // Optional, but useful
        "main_function_to_test": "function_name" // Optional, but useful for testing
    }
    """
    if not isinstance(llm_output, str):
        logger.warning(f"extract_project_structure_from_llm received non-string input: {type(llm_output)}")
        return None

    json_text_to_parse = None
    # Attempt to find JSON within ```json ... ```
    match_md_json = re.search(r"```json\s*(.*?)\s*```", llm_output, re.DOTALL)
    if match_md_json:
        json_text_to_parse = match_md_json.group(1).strip()
    else:
        # Fallback: attempt to find JSON within generic ``` ... ```
        match_md_generic = re.search(r"```\s*(.*?)\s*```", llm_output, re.DOTALL)
        if match_md_generic:
            json_text_to_parse = match_md_generic.group(1).strip()
        else:
            # Fallback: attempt to parse the whole string as JSON if no backticks
            json_text_to_parse = llm_output.strip()

    if not json_text_to_parse:
        logger.error("extract_project_structure_from_llm: No content to parse as JSON.")
        return None

    try:
        project_data = json.loads(json_text_to_parse)
        # Basic validation of expected structure
        if not isinstance(project_data, dict) or "files" not in project_data or not isinstance(project_data["files"], list):
            logger.error(f"extract_project_structure_from_llm: Parsed JSON is not a valid project structure. Missing 'files' list. Parsed: {str(project_data)[:200]}")
            return None
        for file_info in project_data["files"]:
            if not isinstance(file_info, dict) or "name" not in file_info or "content" not in file_info:
                logger.error(f"extract_project_structure_from_llm: Invalid file entry in project structure: {file_info}")
                return None
        return project_data
    except json.JSONDecodeError as e:
        logger.error(f"extract_project_structure_from_llm: JSONDecodeError: {e}. Content: {json_text_to_parse[:500]}...")
        return None
    except Exception as e:
        logger.error(f"extract_project_structure_from_llm: Unexpected error during parsing: {e}. Content: {json_text_to_parse[:500]}...")
        return None


def code_tester_tool(
    project_structure: Dict[str, Any], # {"files": [{"name": "file.py", "content": "..."}], "entry_point_file": "main.py"}
    test_cases: List[Dict[str, Any]]   # Each test case: {"inputs": (args,), "expected_output": val, "description": "...", "target_function": "func_name", "target_file": "file.py" (optional)}
) -> List[Dict[str, Any]]:
    """
    Tests Python functions within a project structure against a list of test cases.
    Creates a temporary directory, writes project files, executes tests, and cleans up.
    """
    results = []
    if not project_structure or not project_structure.get("files"):
        logger.error("code_tester_tool: Invalid or empty project_structure provided.")
        for tc in test_cases:
            results.append({"test_case": tc, "status": "error", "message": "No project structure provided.", "actual_output": None})
        return results

    temp_dir = tempfile.mkdtemp()
    logger.info(f"code_tester_tool: Created temporary directory for testing: {temp_dir}")

    original_sys_path = list(sys.path)
    sys.path.insert(0, temp_dir) # Add temp_dir to path for imports

    try:
        # Write files to temp directory
        for file_info in project_structure["files"]:
            file_name = file_info["name"]
            file_content = file_info["content"]
            file_path = os.path.join(temp_dir, file_name)
            # Ensure subdirectories are created if file_name includes them
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)
            logger.debug(f"Wrote file: {file_path}")
        
        # Determine entry point if specified, otherwise assume tests specify target files
        entry_point_file_name = project_structure.get("entry_point_file")
        main_function_to_test = project_structure.get("main_function_to_test") # Could be used if test_cases don't specify func

        for test_case in test_cases:
            inputs = test_case.get("inputs", ())
            expected_output = test_case.get("expected_output")
            description = test_case.get("description", "Unnamed test")
            
            # Target function and file for this specific test case
            target_function_name = test_case.get("target_function", main_function_to_test)
            target_file_name = test_case.get("target_file", entry_point_file_name)

            if not target_function_name:
                logger.error(f"Test case '{description}' missing target_function name.")
                results.append({"test_case": test_case, "status": "error", "message": "Test case missing target_function name.", "actual_output": None})
                continue
            if not target_file_name:
                logger.error(f"Test case '{description}' for function '{target_function_name}' missing target_file name.")
                results.append({"test_case": test_case, "status": "error", "message": "Test case missing target_file name.", "actual_output": None})
                continue

            module_name = os.path.splitext(target_file_name)[0].replace(os.path.sep, '.')
            
            scope = {'__builtins__': __builtins__}
            func_to_test = None
            
            try:
                # Compile all files in the project scope first to resolve inter-dependencies
                for file_info_compile in project_structure["files"]:
                    compile_file_path = os.path.join(temp_dir, file_info_compile["name"])
                    with open(compile_file_path, "r", encoding="utf-8") as f_compile:
                        code_to_compile = f_compile.read()
                    # Compile in the shared scope. Errors during this phase are complex to attribute to a single test.
                    # We could try to exec all files into one scope first, then get func.
                    # For simplicity, MVP might rely on Python's import mechanism after adding to sys.path.
                    # The original exec(code_string, scope, scope) would not handle multi-file imports easily.
                    # Let's use import_module instead.
                
                imported_module = __import__(module_name, fromlist=[target_function_name])
                if not hasattr(imported_module, target_function_name):
                    raise AttributeError(f"Function '{target_function_name}' not found in module '{module_name}'.")
                func_to_test = getattr(imported_module, target_function_name)
            
            except ImportError as e:
                logger.error(f"code_tester_tool: ImportError for module '{module_name}': {e}", exc_info=True)
                results.append({"test_case": test_case, "status": "import_error", "message": f"Could not import module '{module_name}': {e}", "actual_output": None})
                continue # Skip this test case
            except AttributeError as e: # For getattr failing
                logger.error(f"code_tester_tool: AttributeError for function '{target_function_name}' in '{module_name}': {e}", exc_info=True)
                results.append({"test_case": test_case, "status": "error", "message": f"Function '{target_function_name}' not found in '{module_name}': {e}", "actual_output": None})
                continue
            except Exception as e: # Broad catch for compilation/initialization errors of the project code
                logger.error(f"code_tester_tool: Error setting up test environment for '{target_file_name}': {e}", exc_info=True)
                results.append({"test_case": test_case, "status": "setup_error", "message": f"Error setting up test environment: {e}", "actual_output": None})
                continue


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
                logger.error(f"code_tester_tool: Runtime error during test '{description}' for '{target_function_name}': {e}", exc_info=True)
                results.append({"test_case": test_case, "status": "runtime_error", "actual_output": None, "message": f"Runtime error: {e}."})
                
    finally:
        sys.path = original_sys_path # Restore original sys.path
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"code_tester_tool: Removed temporary directory: {temp_dir}")
        except Exception as e:
            logger.error(f"code_tester_tool: Error removing temporary directory {temp_dir}: {e}")
            
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("--- Testing extract_python_code (single file) ---")
    # ... (existing single file extraction tests remain the same) ...
    test_llm_output_python = "Some text before\n```python\ndef greet(name):\n  return f'Hello, {name}!'\n```\nSome text after"
    extracted = extract_python_code(test_llm_output_python)
    print(f"Extracted: \n{extracted}")
    assert extracted == "def greet(name):\n  return f'Hello, {name}!'"

    print("\n--- Testing extract_project_structure_from_llm ---")
    llm_project_output_md_json = """
    Some introductory text.
    ```json
    {
        "files": [
            {"name": "main.py", "content": "import helper\n\ndef main_func(x):\n  return helper.add_one(x)", "purpose": "Main entry"},
            {"name": "helper.py", "content": "def add_one(n):\n  return n + 1", "purpose": "Utility function"}
        ],
        "entry_point_file": "main.py",
        "main_function_to_test": "main_func"
    }
    ```
    Some concluding text.
    """
    project_structure = extract_project_structure_from_llm(llm_project_output_md_json)
    print(f"Extracted Project Structure: {json.dumps(project_structure, indent=2)}")
    assert project_structure is not None
    assert len(project_structure["files"]) == 2
    assert project_structure["files"][0]["name"] == "main.py"

    llm_project_output_raw_json = """
    {
        "files": [
            {"name": "app.py", "content": "print('Hello')", "purpose": "App entry"}
        ],
        "entry_point_file": "app.py"
    }
    """
    project_structure_raw = extract_project_structure_from_llm(llm_project_output_raw_json)
    print(f"Extracted Project Structure (raw json): {json.dumps(project_structure_raw, indent=2)}")
    assert project_structure_raw is not None
    assert project_structure_raw["files"][0]["name"] == "app.py"

    llm_project_output_md_generic = """
    ```
    {
        "files": [
            {"name": "lib.py", "content": "def lib_func(): return 42", "purpose": "Library"}
        ]
    }
    ```
    """
    project_structure_generic_md = extract_project_structure_from_llm(llm_project_output_md_generic)
    print(f"Extracted Project Structure (generic md): {json.dumps(project_structure_generic_md, indent=2)}")
    assert project_structure_generic_md is not None
    assert project_structure_generic_md["files"][0]["name"] == "lib.py"
    
    invalid_llm_output = "This is not JSON."
    project_structure_invalid = extract_project_structure_from_llm(invalid_llm_output)
    print(f"Extracted Project Structure (invalid): {project_structure_invalid}")
    assert project_structure_invalid is None or project_structure_invalid.get("error") is not None


    print("\n--- Testing code_tester_tool (multi-file project) ---")
    project_code_success = {
        "files": [
            {"name": "utils.py", "content": "def helper_add(x, y):\n  return x + y"},
            {"name": "main.py", "content": "from utils import helper_add\n\ndef main_calculation(a, b, c):\n  return helper_add(a, b) * c"}
        ],
        "entry_point_file": "main.py" # Not strictly used if test_cases specify target_file/target_function
    }
    test_cases_multi = [
        {"inputs": (2, 3, 4), "expected_output": 20, "description": "Test main_calculation", "target_function": "main_calculation", "target_file": "main.py"},
        {"inputs": (10, 5), "expected_output": 15, "description": "Test helper_add directly", "target_function": "helper_add", "target_file": "utils.py"},
        {"inputs": (1, 1, 1), "expected_output": 0, "description": "Intentional fail main_calculation", "target_function": "main_calculation", "target_file": "main.py"},
    ]
    results_multi = code_tester_tool(project_code_success, test_cases_multi)
    print("Test results for multi-file project:")
    for res in results_multi: print(res)
    assert results_multi[0]["status"] == "success"
    assert results_multi[1]["status"] == "success"
    assert results_multi[2]["status"] == "fail"

    project_import_error = {
        "files": [
            {"name": "main.py", "content": "from non_existent_module import some_func\n\ndef run_it():\n  return some_func()"}
        ]
    }
    test_cases_import_error = [
        {"inputs": (), "expected_output": None, "description": "Test import error", "target_function": "run_it", "target_file": "main.py"}
    ]
    results_import_error = code_tester_tool(project_import_error, test_cases_import_error)
    print("\nTest results for import error project:")
    for res in results_import_error: print(res)
    assert results_import_error[0]["status"] == "import_error"

    project_no_target_file = { "files": [{"name": "my_code.py", "content": "def my_func(): return 10"}]}
    test_no_target_file = [{"inputs": (), "expected_output": 10, "description": "No target file in test", "target_function": "my_func"}]
    results_no_target_file = code_tester_tool(project_no_target_file, test_no_target_file)
    print("\nTest results for project with no target_file in test_case (should fail to find func):")
    for res in results_no_target_file: print(res)
    assert results_no_target_file[0]["status"] == "error" # or "setup_error" depending on how it's caught
    assert "missing target_file" in results_no_target_file[0]["message"]