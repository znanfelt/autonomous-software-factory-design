import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from main_pipeline.tools import code_tester_tool, extract_python_code

def test_code_tester_tool_success():
    code = """def add(a, b):\n    return a + b"""
    result = code_tester_tool(code, "add", (2, 3), 5)
    assert result["status"] == "success"
    assert result["actual_output"] == 5

def test_extract_python_code():
    code_block = """```python\ndef foo():\n    return 42\n```"""
    assert extract_python_code(code_block) == "def foo():\n    return 42"