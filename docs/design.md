# Design: Simple SDLC App with PocketFlow, Streamlit GUI, and HITL

## 1. Requirements**

* **Goal:** Create a web application where a user can describe a simple Python function, and an AI system will attempt to generate the code, generate test cases, test it, and allow the user to review, approve, or request refinements.
* **User Stories:**
  * As a user, I want to input a natural language description of a Python function I need.
  * As a user, if my initial request is ambiguous, I want the system to ask me clarifying questions.
  * As a user, I want the system to generate Python code for my function.
  * As a user, I want the system to generate basic test cases for the code.
  * As a user, I want the system to run the tests and show me the results.
  * As a user, I want to review the generated code and test results.
  * As a user, I want to "Approve" the code if it's good, or "Reject" it and provide feedback if it needs changes.
  * As a user, if I reject the code, I want the system to try and refine it based on my feedback (up to a few times).
  * As a user, I want to see the final approved code or a message if the system couldn't satisfy my request after refinements.
* **GUI:** Streamlit will be used for the user interface.
* **HITL:** Human interaction will occur for initial requirements, clarifications, and final review/feedback.
* **PocketFlow:** The core SDLC logic (planning, coding, testing, critiquing, refining) will be managed by PocketFlow nodes and flows.

## 2. Flow Design (Conceptual Stages managed by Streamlit UI & PocketFlow)**

The application will progress through several stages, managed by `streamlit.session_state`. PocketFlow `Flow` instances will be run at different stages.

* **Stage 1: Requirement Elicitation**
  * User provides initial function description.
  * **PocketFlow `ElicitationFlow`:** `InputNode` -> `PlannerCoderNode`
    * `InputNode`: Gets input from UI.
    * `PlannerCoderNode`:
      * *If request is clear:* Plans the function (name, params, return) and generates initial code. Sets next UI stage to `TEST_GENERATION_EXECUTION`.
      * *If request is ambiguous:* Generates clarification questions. Sets next UI stage to `CLARIFICATION`.
* **Stage 2: Clarification (HITL)**
  * UI displays clarification questions. User provides more details.
  * **PocketFlow `ElicitationFlow` (re-run):** `InputNode` (with refined request) -> `PlannerCoderNode`.
    * Loop until `PlannerCoderNode` deems the request clear.
* **Stage 3: Test Generation & Execution**
  * **PocketFlow `TestAndReviewFlow`:** `TestDesignerExecutorNode`
    * `TestDesignerExecutorNode`: Generates test cases (e.g., 2-3 simple ones) based on the plan, then executes them against the generated code.
    * Sets next UI stage to `HUMAN_REVIEW`.
* **Stage 4: Human Review (HITL)**
  * UI displays generated code, test results, and validation notes.
  * User clicks "Approve" or "Reject" (can add a text box for rejection reason).
  * If "Approve": Sets next UI stage to `COMPLETED`.
  * If "Reject": Sets next UI stage to `CRITIQUE_AND_REFINE`.
* **Stage 5: Critique & Refine (Loop)**
  * **PocketFlow `RefinementFlow`:** `CritiqueNode` -> `PlannerCoderNode` (in refine mode)
    * `CritiqueNode`: Takes rejection reason/test failures, generates critique for `PlannerCoderNode`.
    * `PlannerCoderNode`: Attempts to generate revised code based on critique.
  * Loop back to Stage 3 (`TEST_GENERATION_EXECUTION`) with refined code.
  * Limit refinement loops (e.g., max 3 refinements). If exceeded, set UI stage to `MAX_REFINEMENTS_FAILED`.
* **Stage 6: Completed / Failed**
  * `COMPLETED`: **PocketFlow `PackagingFlow`:** `PackageNode` (displays final code and success message).
  * `MAX_REFINEMENTS_FAILED`: Display failure message.

**Simplified Flow Diagram for PocketFlow Segments:**

* **Elicitation & Initial Code Gen Flow:**

    ```text
    (User Input via UI) -> InputNode -> PlannerCoderNode -> (Code/Plan OR Clarification Questions)
    ```

* **Testing Flow:**

    ```text
    (Code/Plan from PlannerCoderNode) -> TestDesignerExecutorNode -> (Test Results)
    ```

* **Refinement Flow (if review rejected):**

    ```text
    (Rejection Reason/Test Failures, Old Code/Plan) -> CritiqueNode -> PlannerCoderNode (refine mode) -> (New Code)
    ```

* **Packaging Flow (if review approved):**

    ```text
    (Approved Code) -> PackageNode -> (Display Final Output)
    ```

**3. Utility Functions (`utils/`)**

* `call_llm.py`:
  * `call_llm(messages: list, model: str = "gpt-4o", temperature: float = 0.2) -> str`: Wrapper for OpenAI API.
* `tools.py`:
  * `extract_python_code(llm_output: str) -> str | None`: Extracts Python code from markdown code blocks.
  * `code_tester_tool(code_string: str, function_name: str, test_cases: list) -> list`:
    * Input: `test_cases` will be a list of dicts like `{"inputs": (arg1, arg2), "expected_output": val, "description": "..."}`.
    * Output: A list of dicts like `{"test_case": ..., "status": "success/fail/error", "actual_output": ..., "message": ...}`.
* `prompts.py`:
  * `ARCHITECT_PROMPT_TEMPLATE` (simplified for MVP - mainly to confirm language Python)
  * `PLANNER_CLARIFICATION_PROMPT_TEMPLATE`
  * `PLANNER_CODEGEN_PROMPT_TEMPLATE`
  * `DEVELOPER_CODEGEN_PROMPT_TEMPLATE` (for initial generation and refinement)
  * `TEST_CASE_DESIGNER_PROMPT_TEMPLATE`
  * `CRITIQUE_PROMPT_TEMPLATE`
  * `VALIDATION_PROMPT_TEMPLATE` (basic checks, e.g., function signature, docstrings)

**4. Node Design (`nodes.py`)**

* **`InitialRequestNode(Node)`:**
  * `prep`: Gets `user_raw_request` from `shared`.
  * `exec`: (No LLM, just passes through for now or simple validation).
  * `post`: Stores `initial_user_request` in `shared`. Returns "default".
* **`ArchitectPlannerNode(Node)`:** (Combines Architect and Planner for simplicity)
  * `prep`: Gets `current_request` (either initial or clarified), `architectural_principles_context`, `planning_guidelines_context`, `iteration_count` from `shared`.
  * `exec`:
        1. (Architect part) LLM call using `ARCHITECT_PROMPT_TEMPLATE` to confirm Python, standard lib.
        2. (Planner part) LLM call. If request clear: `PLANNER_CODEGEN_PROMPT_TEMPLATE` -> `planned_task_description` (function name, params, return type, behavior), `planner_notes`.
        3. If request ambiguous: `PLANNER_CLARIFICATION_PROMPT_TEMPLATE` -> `clarification_questions_for_user`.
  * `post`: Updates `shared` with `architectural_decision`, `planned_task_description`, `planner_notes`, `clarification_questions_for_user`. Increments `planner_iteration_count`. Returns "clarification_needed" or "plan_ready_for_code".
* **`DeveloperNode(Node)`:**
  * `prep`: Gets `planned_task_description`, `planner_notes`, `coding_standards_context`, `critique_feedback` (if in refinement loop) from `shared`.
  * `exec`: LLM call using `DEVELOPER_CODEGEN_PROMPT_TEMPLATE`. `extract_python_code()`.
  * `post`: Stores `generated_code` in `shared`. Increments `refinement_count`. Returns "code_ready_for_tests".
* **`TestCaseDesignerNode(Node)`:**
  * `prep`: Gets `planned_task_description`, `planner_notes`.
  * `exec`: LLM call using `TEST_CASE_DESIGNER_PROMPT_TEMPLATE` to generate a list of test case dicts.
  * `post`: Stores `generated_test_cases` in `shared`. Returns "tests_ready".
* **`QANode(Node)`:**
  * `prep`: Gets `generated_code`, `generated_test_cases`, `current_test_idx` from `shared`.
  * `exec`: Calls `code_tester_tool()` for `generated_test_cases[current_test_idx]`.
  * `post`: Appends `test_result` to `shared.test_results_summary`. Increments `current_test_idx`. Returns "run_next_test" or "all_tests_run".
* **`ValidationNode(Node)`:**
  * `prep`: Gets `generated_code`, `planned_task_description`, `validation_rules_context`.
  * `exec`: LLM call using `VALIDATION_PROMPT_TEMPLATE`.
  * `post`: Stores `validation_status`, `validation_issues` in `shared`. Returns "validation_done".
* **`CritiqueNode(Node)`:** (If tests fail or validation fails or user rejects)
  * `prep`: Gets `planned_task_description`, `generated_code`, `test_results_summary`, `validation_issues`, `user_rejection_reason`, `debugging_tips_context` from `shared`.
  * `exec`: LLM call using `CRITIQUE_PROMPT_TEMPLATE`.
  * `post`: Stores `critique_feedback` in `shared`. Appends to `feedback_history`. Returns "refine_code".
* **`PackageNode(Node)`:** (If approved)
  * `prep`: Gets `generated_code`, `planned_task_description`.
  * `exec`: (Simple formatting for display). Creates `packaged_artifacts_info`.
  * `post`: Stores `packaged_artifacts_info`, `handoff_summary` in `shared`. Returns "done".

**Shared Store Design (`st.session_state` will act as this):**

```python
{
    "user_raw_request": str,
    "current_request_for_planner": str, # Can be initial or clarified
    "architectural_decision": { "chosen_language": "python", "framework_hint": "standard_library", "high_level_notes": str },
    "planner_iteration_count": int,
    "max_planner_iterations": int,
    "clarification_questions_for_user": list[str] | None,
    "planned_task_description": str | None, # Specific details for the function
    "planner_notes": str | None,
    "generated_code": str | None,
    "generated_test_cases": list[dict] | None, # [{'inputs': (1,2), 'expected_output': 3, 'description':'...'}, ...]
    "current_test_case_index": int,
    "test_results_summary": list[dict], # [{'test_case':..., 'status':'success', 'actual_output':..., 'message':...}, ...]
    "all_tests_passed": bool,
    "validation_status": "pass" | "fail" | "error" | None,
    "validation_issues": list[str] | None,
    "user_rejection_reason": str | None,
    "critique_feedback": str | None,
    "feedback_history": list[str], # History of critiques
    "refinement_count": int,
    "max_refinements": int,
    "packaged_artifacts_info": dict | None, # e.g., {"code_file_path": "...", "readme": "..."}
    "handoff_summary": str | None,
    "current_error_message": str | None, # For displaying errors in UI
    # RAG Contexts (loaded once or on demand)
    "architectural_principles_context": str,
    "planning_guidelines_context": str,
    "coding_standards_context": str,
    "validation_rules_context": str,
    "debugging_tips_context": str
}
```

**5. Streamlit UI (`app.py`)**

* Main display area for current status, code, test results.
* Input area for initial request / clarifications / rejection reasons.
* Buttons for "Submit", "Send Clarification", "Approve", "Reject", "Start Over".
* The UI will manage `st.session_state.current_ui_stage` (e.g., "INPUT_REQUIREMENTS", "AWAITING_CLARIFICATION", "AWAITING_REVIEW", "COMPLETED", "FAILED").
* Based on `current_ui_stage`, it will render appropriate inputs/outputs and buttons.
* Button clicks will update `st.session_state` and then call the relevant PocketFlow execution logic.

**Directory Structure:**

```text
pocketflow_sft_dev_app/
├── app.py                     # Streamlit UI and main logic
├── nodes.py                   # PocketFlow Node definitions
├── flow.py                    # PocketFlow Flow definitions
├── utils/
│   ├── __init__.py
│   ├── call_llm.py
│   ├── tools.py
│   └── prompts.py
├── rag_contexts/              # Simple text files for RAG content
│   ├── architectural_principles.txt
│   ├── planning_guidelines.txt
│   ├── coding_standards.txt
│   ├── validation_rules.txt
│   └── debugging_tips.txt
├── output_artifacts/          # (Optional) For saving final generated code
├── requirements.txt
└── README.md
```

This design simplifies the complex SDLC into manageable parts suitable for a "simple app" while demonstrating PocketFlow's capabilities, GUI integration, and HITL.
The RAG contexts will be simple strings loaded from files for this version, rather than a full LlamaIndex setup, to keep the initial implementation focused.
I will start with this simplified design and we can iterate.

Do you approve this design?This is a comprehensive and well-thought-out design! It balances the complexity of an SDLC process with the need for a "simple app" demonstration, leveraging PocketFlow for the core logic and Streamlit for the GUI and HITL interactions.

I approve this design. Let's proceed with the implementation.

I'm particularly happy with:

* The clear breakdown of UI stages and how PocketFlow execution will be triggered within them.
* The simplified agent roles into more focused PocketFlow nodes.
* The use of `st.session_state` as the `shared` store for PocketFlow – this is a clean integration.
* The explicit definition of prompt templates and utility functions.
* The planned directory structure.
