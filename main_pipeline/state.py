from typing import TypedDict, Optional, List, Any, Tuple, Literal, Dict

class TestCase(TypedDict):
    function_name: str
    inputs: Tuple[Any, ...]
    expected_output: Any
    description: Optional[str]

class TestResult(TypedDict):
    test_case: TestCase
    status: Optional[Literal['success', 'compilation_error', 'runtime_error', 'test_fail', 'tool_error']]
    message: Optional[str]
    actual_output: Optional[Any]

class GraphState(TypedDict):
    initial_user_request: str
    architectural_decision: Optional[Dict[str, Any]]
    clarified_user_input: Optional[str]
    clarification_questions_for_user: Optional[List[str]]
    planner_iteration_count: int
    max_planner_iterations: int
    llm_models_config: Dict[str, str]
    planned_task_description: Optional[str]
    planner_notes: Optional[str]
    task_description: str
    generated_test_cases: Optional[List[TestCase]]
    current_test_case_index: int
    all_tests_passed: bool
    generated_code: Optional[str]
    current_test_status: Optional[Literal['success', 'compilation_error', 'runtime_error', 'test_fail', 'tool_error']]
    current_test_message: Optional[str]
    test_results_summary: List[TestResult]
    critique: Optional[str]
    validation_status: Optional[Literal['pass', 'fail', 'error']]
    validation_issues: Optional[List[str]]
    packaged_artifacts_info: Optional[Dict[str, str]]
    handoff_summary: Optional[str]
    feedback_history: List[str]
    refinement_count: int
    max_refinements: int
    current_error: Optional[str]
    qa_agent_messages: List