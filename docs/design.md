# Design Document: Simple Autonomous Software Factory (MVP)

**Version:** 1.0 (Reflecting Docker & SQLite Integration)

## 1. Requirements

* **Goal:** Create a web application where a user can describe a simple Python function. An AI system will then attempt to autonomously generate, test, validate, and refine this function with human oversight.
* **User Interface:** Streamlit for interactive web GUI.
* **Workflow Orchestration:** PocketFlow to manage the sequence of AI-driven tasks.
* **AI Capabilities:** Leverage OpenAI LLMs for planning, code generation, test case design, validation, and critique.
* **Human-in-the-Loop (HITL):**
  * Initial requirement input.
  * Optional clarification phase if the initial request is ambiguous.
  * Review and approval/rejection of the generated and tested code.
* **Persistence:** Use SQLite to store task details, generated code versions, test cases, test results, and feedback.
* **Deployment:** Containerize the application using Docker for portability and consistent environments.
* **RAG Context:** Provide simple file-based contextual information (guidelines, standards) to AI agents.

## 2. High-Level System Flow & UI Stages

The application progresses through distinct UI stages, managed by `streamlit.session_state.ui_stage`. PocketFlow flows are invoked at specific stages to perform AI-driven tasks.

1. **`INPUT_REQUIREMENTS` (UI Stage):**
    * User inputs a natural language description of the Python function.
    * **Action:** `Submit` button triggers the `ElicitationFlow`.
    * **PocketFlow `ElicitationFlow`:**
        * `InitialRequestNode`: Captures input.
        * `ArchitectPlannerNode`:
            * Architect part: Confirms Python, standard library (MVP constraint).
            * Planner part:
                * If request is clear: Generates `planned_task_description` (function signature, behavior) and `planner_notes`. Transitions UI to `TEST_GENERATION`.
                * If request is ambiguous: Generates `clarification_questions_for_user`. Transitions UI to `CLARIFICATION`.
    * *DB Interaction:* New task created. Architectural decision and planner output/questions saved.

2. **`CLARIFICATION` (UI Stage - HITL):**
    * Displays questions from `ArchitectPlannerNode`. User provides answers.
    * **Action:** `Submit Clarifications` button re-triggers the `ArchitectPlannerNode` (within `ElicitationFlow`) with the refined request.
    * Loop until `plan_ready_for_code` or `max_planner_iterations` reached. If max iterations, UI to `FAILED_PLANNING`.
    * *DB Interaction:* User clarifications logged (e.g., as feedback). Task planner fields updated.

3. **`TEST_GENERATION` (UI Stage):**
    * System indicates it's generating tests and initial code.
    * **PocketFlow `TestAndInitialCodeFlow` (conceptual grouping, runs sequentially):**
        * `TestCaseDesignerNode`: Generates `generated_test_cases` based on `planned_task_description`.
        * `DeveloperNode`: Generates initial `generated_code` based on `planned_task_description` and `planner_notes`.
        * Transitions UI to `QA_EXECUTION`.
    * *DB Interaction:* Generated test cases and initial code version saved.

4. **`QA_EXECUTION` (UI Stage):**
    * System indicates it's running tests and validation.
    * **PocketFlow `QAValidationFlow` (conceptual grouping):**
        * `QANode`: Iteratively runs each test case from `generated_test_cases` against `generated_code` using `code_tester_tool`. Stores `test_results_summary` and `all_tests_passed`.
        * `ValidationNode`: Validates `generated_code` against `validation_rules_context`. Stores `validation_status` and `validation_issues`.
        * Transitions UI to `HUMAN_REVIEW`.
    * *DB Interaction:* Test run results and validation logs saved.

5. **`HUMAN_REVIEW` (UI Stage - HITL):**
    * Displays `generated_code`, `test_results_summary`, and `validation_issues`.
    * **Actions:**
        * `Approve Code`: If `all_tests_passed` is true and `validation_status` is "pass". Transitions UI to `COMPLETED`.
        * `Reject & Refine`: Transitions UI to `PROVIDE_REJECTION_FEEDBACK`.
    * *DB Interaction:* User approval/rejection intent can be logged.

6. **`PROVIDE_REJECTION_FEEDBACK` (UI Stage - HITL):**
    * User provides `user_rejection_reason`.
    * **Action:** `Submit Feedback & Retry` button. Transitions UI to `CRITIQUE_AND_REFINE`.
    * *DB Interaction:* User rejection reason logged as feedback.

7. **`CRITIQUE_AND_REFINE` (UI Stage):**
    * System indicates AI is critiquing and refining.
    * **PocketFlow `RefinementFlow`:**
        * `CritiqueNode`: Generates `critique_feedback` based on test failures, validation issues, and user rejection reason.
        * `DeveloperNode` (refine mode): Takes `critique_feedback` and previous `generated_code` to produce new `generated_code`. Increments `refinement_count`.
    * If `refinement_count` < `max_refinements`: Transitions UI back to `QA_EXECUTION` (to test the new code).
    * If `refinement_count` >= `max_refinements`: Transitions UI to `MAX_REFINEMENTS_FAILED`.
    * *DB Interaction:* AI critique logged as feedback. New code version saved. Refinement count updated.

8. **`COMPLETED` (UI Stage):**
    * **PocketFlow `PackagingFlow`:**
        * `PackageNode`: Generates `packaged_artifacts_info` and `handoff_summary`.
    * Displays success message and packaged info.
    * *DB Interaction:* Packaged artifacts info saved. Task status set to 'completed'.

9. **`FAILED_PLANNING` / `MAX_REFINEMENTS_FAILED` (UI Stages):**
    * Displays appropriate failure message.
    * *DB Interaction:* Task status updated to 'failed'.

**Flow Diagrams (PocketFlow Segments):**

* **Elicitation & Initial Planning Flow (`elicitation_flow`):**

    ```text
    InitialRequestNode -> ArchitectPlannerNode
    ```

    (ArchitectPlannerNode internally decides if clarification is needed, UI handles the loop)

* **Test Design, Initial Code Gen, QA, Validation (`testing_flow_segment` - triggered after planning):**

    ```text
    TestCaseDesignerNode -> DeveloperNode ("code_ready_for_tests") -> QANode ("run_next_test" loop) -> QANode ("testing_error_or_done") -> ValidationNode
    DeveloperNode ("code_generation_failed") -> CritiqueNode (This path bypasses QA/Validation if dev fails outright) 
    ```

* **Refinement Cycle Flow (`refinement_flow_segment` - triggered after rejection):**

    ```text
    CritiqueNode ("refine_code") -> DeveloperNode 
    ```

    (DeveloperNode then goes back to `QA_EXECUTION` stage via UI logic)

* **Packaging Flow (`packaging_flow` - triggered after approval):**

    ```text
    PackageNode
    ```

## 3. Utility Functions (`utils/`)

* **`call_llm.py`**:
  * `call_llm(messages: list, model: str, temperature: float)`: OpenAI API wrapper. Returns JSON string or error dict.
* **`tools.py`**:
  * `extract_python_code(llm_output: str) -> str | None`: Extracts Python code from markdown.
  * `code_tester_tool(code_string: str, function_name: str, test_cases: list[dict]) -> list[dict]`: Executes code against test cases.
* **`prompts.py`**: Contains all LLM prompt templates as constants.
  * `ARCHITECT_PROMPT_TEMPLATE`
  * `PLANNER_CLARIFICATION_PROMPT_TEMPLATE`
  * `PLANNER_CODEGEN_PROMPT_TEMPLATE`
  * `DEVELOPER_CODEGEN_PROMPT_TEMPLATE`
  * `TEST_CASE_DESIGNER_PROMPT_TEMPLATE`
  * `VALIDATION_PROMPT_TEMPLATE`
  * `CRITIQUE_PROMPT_TEMPLATE`
* **`database.py`**: SQLite interaction functions.
  * `DB_FILE`: Path to the database.
  * `create_connection()`: Returns `sqlite3.Connection`.
  * `init_db()`: Creates tables if they don't exist.
  * `execute_query(query, params, fetch_one, fetch_all, last_row_id)`: General query executor.
  * CRUD functions for `tasks`, `code_versions`, `test_cases_generated` (optional if tests are part of task state), `test_run_results`, `validation_logs`, `feedback_logs`, `packaged_artifacts`.

## 4. Node Design (`nodes.py`)

(Detailed descriptions for each node as provided in the previous iteration, focusing on their `prep`, `exec`, and `post` methods and interaction with the `shared` state passed by `app.py`.)

* **`InitialRequestNode`**: Captures raw user request.
* **`ArchitectPlannerNode`**: High-level tech decisions (Python for MVP) + detailed function planning or clarification question generation.
* **`DeveloperNode`**: Generates/refines Python code based on plan and feedback.
* **`TestCaseDesignerNode`**: Generates test cases from the function plan.
* **`QANode`**: Executes a single test case against the current code.
* **`ValidationNode`**: Validates code against predefined rules using an LLM.
* **`CritiqueNode`**: Generates critique based on test failures, validation issues, or user feedback.
* **`PackageNode`**: Formats final code and creates a handoff summary.

**Shared State for PocketFlow (`shared` dict passed to `flow.run()`):**
This dictionary will be constructed by `app.py` for each PocketFlow run, populated with data from `st.session_state` and relevant RAG contexts.

```python
{
    # Input data for the current flow/node
    "user_raw_request": "...",       # From InitialRequestNode
    "current_request_for_planner": "...", # From ArchitectPlannerNode
    "planned_task_description": {...}, # From ArchitectPlannerNode, input to DeveloperNode & TestCaseDesignerNode
    "planner_notes": "...",          # From ArchitectPlannerNode
    "generated_code": "...",         # From DeveloperNode, input to QANode & ValidationNode
    "generated_test_cases": [...],   # From TestCaseDesignerNode, input to QANode
    "current_test_case_index": 0,    # For QANode iteration
    "test_results_summary": [...],   # Aggregated by QANode
    "validation_issues": [...],      # From ValidationNode
    "user_rejection_reason": "...",  # From UI, input to CritiqueNode
    "critique_feedback": "...",      # From CritiqueNode, input to DeveloperNode for refinement
    "feedback_history": [...],       # List of past critiques for DeveloperNode
    "refinement_count": 0,           # Tracked for DeveloperNode
    
    # RAG Contexts (loaded once by app.py)
    "architectural_principles_context": "...",
    "planning_guidelines_context": "...",
    "coding_standards_context": "...",
    "validation_rules_context": "...",
    "debugging_tips_context": "...",

    # Control/Config
    "llm_models_config": {...},
    "max_planner_iterations": 2,
    "max_refinements": 3,

    # Output fields (populated by nodes)
    # Note: Some of these are intermediate and might be overwritten or cleared.
    # The final persistent state is in SQLite, managed by app.py.
    "architectural_decision": {...},
    "clarification_questions_for_user": [...],
    "all_tests_passed": False,
    "validation_status": None,
    "packaged_artifacts_info": None,
    "handoff_summary": None,
    "current_error_message": None # For internal flow errors
}
```

Note: The Streamlit app.py will be responsible for mapping its st.session_state (which holds the state for the active task) to this shared dictionary before calling a PocketFlow run() method, and then updating st.session_state and the SQLite DB from the shared dictionary afterwards.
5. Streamlit UI (app.py)
Manages st.session_state.ui_stage to control UI flow.
On app start, calls init_db().
Provides input fields and buttons relevant to the current ui_stage.
On button clicks:
Updates st.session_state (e.g., user_raw_request, user_rejection_reason).
Constructs the shared dictionary for the appropriate PocketFlow segment.
Calls the relevant PocketFlow flow.run(shared).
Updates st.session_state from the shared dictionary returned by the flow.
Persists changes to the SQLite database (e.g., updating task status, saving new code version).
Sets the next st.session_state.ui_stage and calls st.rerun().
Displays errors from st.session_state.current_error_message.
6. Docker (Dockerfile)
Base Python image (e.g., python:3.11-slim).
Set ENV for OPENAI_API_KEY (to be passed at runtime), LLM model names, and other configurations.
Copy requirements.txt and install dependencies.
Copy all application files (app.py, nodes.py, flow.py, utils/, rag_contexts/).
Create /app/database directory (SQLite DB file will be created here by database.py).
Expose Streamlit port (8501).
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"].
7. RAG Contexts (rag_contexts/)
Simple .txt files containing guidelines for each agent, loaded into st.session_state by app.py.
This design is now more aligned with a typical web application structure where the UI (app.py) drives interactions, manages application-level state (st.session_state), persists to a database (utils/database.py), and calls business logic modules (PocketFlow flows defined in flow.py which use nodes.py).
