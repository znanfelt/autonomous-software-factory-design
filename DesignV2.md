# Design: Simple SDLC App with PocketFlow, Streamlit GUI, and HITL

## 1. Requirements

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

## 2. Flow Design (Conceptual Stages managed by Streamlit UI & PocketFlow)

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

```
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

# Design: Simple SDLC App with PocketFlow, Streamlit GUI, HITL, Docker, and SQLite

## 1. Requirements

* **Goal:** Create a web application where a user can describe a simple Python function. An AI system will generate the code, test cases, test it, and allow the user to review, approve, or request refinements.
* **User Stories:** (Same as before)
* **GUI:** Streamlit.
* **HITL:** For initial requirements, clarifications, and review/feedback.
* **PocketFlow:** Manages core SDLC logic.
* **Persistence:** State (requests, code, tests, feedback) persisted in an SQLite database.
* **Deployment:** Application containerized using Docker.

## 2. Flow Design (Conceptual Stages managed by Streamlit UI & PocketFlow)

The conceptual flow remains the same. `st.session_state` will hold data for the *currently active* task, loaded from/saved to SQLite.

* **Elicitation & Initial Code Gen Flow:** `InputNode` -> `ArchitectPlannerNode`
* **Testing Flow:** `TestDesignerExecutorNode`
* **Refinement Flow:** `CritiqueNode` -> `DeveloperNode` (refine mode)
* **Packaging Flow:** `PackageNode`

## 3. Utility Functions (`utils/`)**

* `call_llm.py`: `call_llm(messages, model, temperature)` - OpenAI API wrapper.
* `tools.py`: `extract_python_code(llm_output)`, `code_tester_tool(code_string, function_name, test_cases)`.
* `prompts.py`: Templates for Architect, Planner (Clarification & Codegen), Developer, Test Case Designer, Validator, Critiquer.
* **New:** `database.py`:
  * `DB_FILE = "database/sdlc_tasks.db"`
  * `create_connection()`
  * `init_db()`: Creates tables (`tasks`, `code_versions`, `test_cases_generated`, `test_run_results`, `validation_logs`, `feedback_logs`, `packaged_artifacts`).
  * Functions for CRUD operations on these tables (e.g., `create_task`, `get_task_data`, `add_code_version`, `log_feedback`, etc.).

## 4. Node Design (`nodes.py`)**

Nodes interact with `shared` (which mirrors `st.session_state` for the active task). `app.py` handles SQLite persistence after node/flow execution.

* **`InitialRequestNode(Node)`:**
  * `prep`: Gets `user_raw_request` from `shared`.
  * `post`: Stores `initial_user_request` in `shared`. *(`app.py` calls `database.create_task()`)*.
* **`ArchitectPlannerNode(Node)`:**
  * `prep`: Gets `current_request_for_planner`, RAG contexts, `planner_iteration_count`.
  * `exec`: LLM calls for architecture (confirm Python) and planning (task description or clarification questions).
  * `post`: Updates `shared` with `architectural_decision`, `planned_task_description` / `clarification_questions_for_user`, `planner_notes`. Increments `planner_iteration_count`. Returns "clarification_needed" or "plan_ready_for_code". *(`app.py` calls `database.update_task_data()`)*.
* **`DeveloperNode(Node)`:**
  * `prep`: Gets `planned_task_description`, `planner_notes`, `coding_standards_context`, `critique_feedback`.
  * `exec`: LLM call to generate/refine code; `extract_python_code()`.
  * `post`: Stores `generated_code` in `shared`. Increments `refinement_count`. Returns "code_ready_for_tests". *(`app.py` calls `database.add_code_version()` and updates task)*.
* **`TestCaseDesignerNode(Node)`:**
  * `prep`: Gets `planned_task_description`, `planner_notes`.
  * `exec`: LLM call to generate test case dicts.
  * `post`: Stores `generated_test_cases` in `shared`. Returns "tests_ready". *(`app.py` updates task)*.
* **`QANode(Node)`:**
  * `prep`: Gets `generated_code`, `generated_test_cases`, `current_test_case_index`.
  * `exec`: Calls `code_tester_tool()` for current test case.
  * `post`: Appends `test_result` to `shared.test_results_summary`. Increments `current_test_case_index`. Returns "run_next_test" or "all_tests_run". *(`app.py` calls `database.add_test_result()`)*.
* **`ValidationNode(Node)`:**
  * `prep`: Gets `generated_code`, `planned_task_description`, `validation_rules_context`.
  * `exec`: LLM call for validation.
  * `post`: Stores `validation_status`, `validation_issues`. Returns "validation_done". *(`app.py` calls `database.add_validation_log()`)*.
* **`CritiqueNode(Node)`:**
  * `prep`: Gets `planned_task_description`, `generated_code`, test/validation results, user feedback, RAG context.
  * `exec`: LLM call for critique.
  * `post`: Stores `critique_feedback`, appends to `feedback_history`. Returns "refine_code". *(`app.py` calls `database.add_feedback()`)*.
* **`PackageNode(Node)`:**
  * `prep`: Gets `generated_code`, `planned_task_description`.
  * `exec`: Formats final output.
  * `post`: Stores `packaged_artifacts_info`, `handoff_summary`. Returns "done". *(`app.py` calls `database.add_packaged_artifact()`)*.

**Shared Store Design (`st.session_state` for active task):**

* `active_task_id: int | None`
* `user_raw_request: str`
* `current_request_for_planner: str`
* `architectural_decision: dict`
* `planner_iteration_count: int`, `max_planner_iterations: int`
* `llm_models_config: dict`
* `clarification_questions_for_user: list | None`
* `planned_task_description: str | None`
* `planner_notes: str | None`
* `generated_code: str | None`
* `active_code_version_id: int | None` (Tracks the ID of the code version being tested/reviewed)
* `generated_test_cases: list[dict] | None`
* `current_test_case_index: int`
* `test_results_summary: list[dict]`
* `all_tests_passed: bool`
* `validation_status: str | None`
* `validation_issues: list[str] | None`
* `user_rejection_reason: str | None`
* `critique_feedback: str | None`
* `feedback_history: list[str]` (Loaded from DB for current code version)
* `refinement_count: int`
* `max_refinements: int`
* `packaged_artifacts_info: dict | None`
* `handoff_summary: str | None`
* `current_error_message: str | None`
* RAG Contexts (loaded once): `architectural_principles_context`, `planning_guidelines_context`, etc.

**SQLite Database Schema (`sdlc_tasks.db`):**
(Conceptual design as previously outlined, with tables like `tasks`, `code_versions`, `test_cases_generated`, `test_run_results`, `validation_logs`, `feedback_logs`, `packaged_artifacts`.)

## 5. Streamlit UI (`app.py`)**

* **Task Management:**
  * `init_db()` called on startup.
  * UI allows starting a new task (creates a DB entry and sets `active_task_id`) or potentially listing/selecting existing tasks (more advanced). For MVP, one active task at a time.
  * Loads active task data from SQLite into `st.session_state`.
  * Persists changes from `st.session_state` to SQLite after PocketFlow stages or user actions.
* (UI stages and interactions as previously designed).

**6. Docker (`Dockerfile`)**

* Python base image.
* Set `OPENAI_API_KEY` (passed at runtime), and other `ENV` for LLM models, max iterations.
* Copy `requirements.txt`, install dependencies.
* Copy application code.
* Create `/app/database` directory.
* Expose Streamlit port (8501).
* `CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]`

**Directory Structure:**
(Same as previous update, with `database/sdlc_tasks.db` being created at runtime within the container if mapped to a volume, or just inside the container).

This refined design should provide a good foundation. I'll start by creating the `utils/` directory and its modules.

```python
import os
import sqlite3
import json
from typing import Any, List, Tuple, Dict, Optional
from datetime import datetime

DB_FILE = "database/sdlc_tasks.db"

def create_connection() -> Optional[sqlite3.Connection]:
    """Create a database connection to the SQLite database."""
    conn = None
    try:
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        conn = sqlite3.connect(DB_FILE)
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
    return conn

def init_db():
    """Initialize the database with necessary tables if they don't exist."""
    conn = create_connection()
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                initial_request TEXT NOT NULL,
                architectural_decision TEXT, -- JSON
                planned_task_description TEXT, -- JSON
                planner_notes TEXT,
                status TEXT DEFAULT 'created', -- e.g., created, planning, coding, review, completed, failed
                refinement_count INTEGER DEFAULT 0,
                current_error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_versions (
                code_version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                iteration_number INTEGER NOT NULL, -- Corresponds to refinement_count at time of generation
                generated_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_cases_generated (
                test_case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                -- code_version_id INTEGER, -- Link to specific code version if tests are versioned
                case_description TEXT,
                function_name TEXT,
                inputs TEXT, -- JSON serialized tuple
                expected_output TEXT, -- JSON serialized
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
                -- FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_run_results (
                test_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER NOT NULL,
                test_case_id INTEGER NOT NULL, -- Can be ID from test_cases_generated or a description if dynamic
                status TEXT NOT NULL, -- 'success', 'fail', 'error'
                actual_output TEXT, -- JSON serialized
                message TEXT,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id),
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id)
                -- Optionally link test_case_id if it's from a predefined set
                -- FOREIGN KEY (test_case_id) REFERENCES test_cases_generated(test_case_id) 
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_logs (
                validation_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER NOT NULL,
                status TEXT NOT NULL, -- 'pass', 'fail', 'error'
                issues_found TEXT, -- JSON serialized list of strings
                validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id),
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_logs (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER, -- Optional, could be general task feedback
                feedback_type TEXT NOT NULL, -- 'user_rejection', 'critique'
                feedback_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id),
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS packaged_artifacts (
                artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                info TEXT, -- JSON: e.g., {"code_file_path": "...", "readme": "..."}
                handoff_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            );
        """)
        conn.commit()
        print("Database initialized successfully.")
    except sqlite3.Error as e:
        print(f"Error initializing database: {e}")
    finally:
        if conn:
            conn.close()

def execute_query(query: str, params: Tuple = (), fetch_one=False, fetch_all=False, last_row_id=False):
    """Execute a SQL query and optionally fetch results."""
    conn = create_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        
        if last_row_id:
            return cursor.lastrowid
        if fetch_one:
            return cursor.fetchone()
        if fetch_all:
            return cursor.fetchall()
        return True # For non-select queries or when no fetch is needed
    except sqlite3.Error as e:
        print(f"Error executing query '{query[:50]}...': {e}")
        return None
    finally:
        if conn:
            conn.close()

# --- Task Management ---
def create_task(initial_request: str) -> Optional[int]:
    query = "INSERT INTO tasks (initial_request, status, updated_at) VALUES (?, ?, ?)"
    return execute_query(query, (initial_request, 'created', datetime.now().isoformat()), last_row_id=True)

def get_task_data(task_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM tasks WHERE task_id = ?"
    row = execute_query(query, (task_id,), fetch_one=True)
    if row:
        # Convert row tuple to dict
        col_names = ["task_id", "initial_request", "architectural_decision", "planned_task_description",
                     "planner_notes", "status", "refinement_count", "current_error_message", 
                     "created_at", "updated_at"]
        task_data = dict(zip(col_names, row))
        # Deserialize JSON fields
        for field in ["architectural_decision", "planned_task_description"]:
            if task_data[field]:
                try:
                    task_data[field] = json.loads(task_data[field])
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse JSON for field {field} in task {task_id}")
                    task_data[field] = None # Or keep as string, or handle error
        return task_data
    return None

def update_task_field(task_id: int, field_name: str, field_value: Any) -> bool:
    # Basic validation for field_name to prevent SQL injection via dynamic field names
    allowed_fields = ["architectural_decision", "planned_task_description", "planner_notes", 
                      "status", "refinement_count", "current_error_message", "updated_at"]
    if field_name not in allowed_fields:
        print(f"Error: Invalid field name '{field_name}' for task update.")
        return False
    
    value_to_store = json.dumps(field_value) if isinstance(field_value, (dict, list)) else field_value
    query = f"UPDATE tasks SET {field_name} = ?, updated_at = ? WHERE task_id = ?"
    return execute_query(query, (value_to_store, datetime.now().isoformat(), task_id)) is not None

# --- Code Version Management ---
def add_code_version(task_id: int, code: str, iteration: int) -> Optional[int]:
    query = "INSERT INTO code_versions (task_id, generated_code, iteration_number) VALUES (?, ?, ?)"
    return execute_query(query, (task_id, code, iteration), last_row_id=True)

def get_latest_code_version(task_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT code_version_id, generated_code, iteration_number FROM code_versions WHERE task_id = ? ORDER BY created_at DESC LIMIT 1"
    row = execute_query(query, (task_id,), fetch_one=True)
    if row:
        return {"code_version_id": row[0], "generated_code": row[1], "iteration_number": row[2]}
    return None

# --- Test Case & Result Management ---
def add_generated_test_cases(task_id: int, test_cases: List[Dict]) -> bool:
    # This could store them individually or as a JSON blob in the tasks table
    # For simplicity, let's update a JSON field in tasks table for now.
    # A more robust solution would be a separate test_cases_generated table.
    return update_task_field(task_id, 'generated_test_cases_json', json.dumps(test_cases))

def log_test_run_result(task_id: int, code_version_id: int, test_case_desc: str, status: str, actual_output: Any, message: str) -> Optional[int]:
    query = """
        INSERT INTO test_run_results 
        (task_id, code_version_id, test_case_id, status, actual_output, message) 
        VALUES (?, ?, ?, ?, ?, ?)
    """ 
    # Assuming test_case_id is a description or can be null if we don't pre-store test cases
    # For this MVP, let's use test_case_desc for the 'test_case_id' field (which expects INT). 
    # This is a simplification. A proper setup would link to a test_cases_generated table.
    # Let's store description as message for now and simplify test_case_id
    return execute_query(query, (task_id, code_version_id, -1, status, json.dumps(actual_output), f"{test_case_desc} - {message}"), last_row_id=True)

def get_test_results_for_version(code_version_id: int) -> List[Dict]:
    query = "SELECT test_case_id, status, actual_output, message FROM test_run_results WHERE code_version_id = ?"
    rows = execute_query(query, (code_version_id,), fetch_all=True)
    results = []
    if rows:
        for row in rows:
            results.append({
                "test_case_id_or_desc": row[0], # Placeholder for simplification
                "status": row[1],
                "actual_output": json.loads(row[2]) if row[2] else None,
                "message": row[3]
            })
    return results

# --- Validation & Feedback Logs ---
def log_validation_result(task_id: int, code_version_id: int, status: str, issues: Optional[List[str]]) -> Optional[int]:
    issues_json = json.dumps(issues) if issues else None
    query = "INSERT INTO validation_logs (task_id, code_version_id, status, issues_found) VALUES (?, ?, ?, ?)"
    return execute_query(query, (task_id, code_version_id, status, issues_json), last_row_id=True)

def log_feedback(task_id: int, code_version_id: Optional[int], feedback_type: str, feedback_text: str) -> Optional[int]:
    query = "INSERT INTO feedback_logs (task_id, code_version_id, feedback_type, feedback_text) VALUES (?, ?, ?, ?)"
    return execute_query(query, (task_id, code_version_id, feedback_type, feedback_text), last_row_id=True)

def get_feedback_history_for_version(code_version_id: int) -> List[Dict]:
    query = "SELECT feedback_type, feedback_text, created_at FROM feedback_logs WHERE code_version_id = ? ORDER BY created_at ASC"
    rows = execute_query(query, (code_version_id,), fetch_all=True)
    history = []
    if rows:
        for row in rows:
            history.append({"type": row[0], "text": row[1], "timestamp": row[2]})
    return history
    
# --- Artifact Management ---
def add_packaged_artifact(task_id: int, info: Dict, handoff_summary: str) -> Optional[int]:
    query = "INSERT INTO packaged_artifacts (task_id, info, handoff_summary) VALUES (?, ?, ?)"
    return execute_query(query, (task_id, json.dumps(info), handoff_summary), last_row_id=True)

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Creating a sample task...")
    sample_task_id = create_task("Create a Python function to add two numbers.")
    if sample_task_id:
        print(f"Sample task created with ID: {sample_task_id}")
        task = get_task_data(sample_task_id)
        print(f"Retrieved task data: {task}")

        update_task_field(sample_task_id, "status", "planning_done")
        updated_task = get_task_data(sample_task_id)
        print(f"Updated task data: {updated_task}")

        cv_id = add_code_version(sample_task_id, "def add(a, b): return a + b", 0)
        if cv_id:
            print(f"Code version added with ID: {cv_id}")
            log_test_run_result(sample_task_id, cv_id, "Test with 2,3", "success", 5, "Passed.")
            tests = get_test_results_for_version(cv_id)
            print(f"Test results for version {cv_id}: {tests}")
    else:
        print("Failed to create sample task.")

```

```python
# utils/call_llm.py
import os
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY environment variable not set. LLM calls will likely fail or use mocks.")
        # Optionally, raise an error or return a mock client
        # raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

DEFAULT_MODEL = "gpt-4o" # Define a default model

def call_llm(messages: list, model: str = DEFAULT_MODEL, temperature: float = 0.2) -> str:
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"} # Assuming you want JSON output for structured prompts
        )
        content = response.choices[0].message.content
        if content is None:
            logger.error("LLM response content is None.")
            return '{"error": "LLM returned no content"}' # Return valid JSON error string
        return content
    except Exception as e:
        logger.error(f"Error calling LLM API: {e}", exc_info=True)
        return f'{{"error": "LLM API call failed: {str(e)}"}}' # Return valid JSON error string


if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)
    
    print("Testing call_llm (expecting JSON parsable string):")
    # Test with a prompt that should ideally produce JSON
    test_messages = [
        {"role": "system", "content": "You are a helpful assistant. Respond in JSON format."},
        {"role": "user", "content": "What is the meaning of life? Respond with a key 'answer'."}
    ]
    # Ensure API key is set in your environment for this test to run properly
    if os.getenv("OPENAI_API_KEY"):
        response_str = call_llm(test_messages)
        print(f"Raw LLM Response: {response_str}")
        try:
            import json
            response_json = json.loads(response_str)
            print(f"Parsed JSON Response: {response_json}")
            if "error" in response_json:
                print("LLM call resulted in an error or could not produce valid JSON as requested.")
        except json.JSONDecodeError as e:
            print(f"Failed to parse LLM response as JSON: {e}")
            print("This might indicate the LLM did not adhere to the JSON output format request, or an API error occurred.")
    else:
        print("OPENAI_API_KEY not set. Skipping live API call test.")

```

```python
# utils/tools.py
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

```

```python
# utils/prompts.py

ARCHITECT_PROMPT_TEMPLATE = """
You are a Senior Software Architect. Your task is to make high-level technical decisions for a user's software request.
Consider the Architectural Principles provided below.

--- BEGIN ARCHITECTURAL PRINCIPLES ---
{architectural_principles_context}
--- END ARCHITECTURAL PRINCIPLES ---

User Request: "{user_request}"

For the MVP, we are focusing on simple Python functions using the standard library.
Based on this, output ONLY a valid JSON object with the following keys:
- "chosen_language": Always "python" for this MVP.
- "framework_hint": Always "standard_library" for this MVP.
- "high_level_notes": Brief notes (1-2 sentences) for the planner, confirming the task is a simple Python function.
"""

PLANNER_CLARIFICATION_PROMPT_TEMPLATE = """
You are an expert Requirements Analyst and Planner.
Architect Decision: Language='{chosen_language}', Framework Hint='{framework_hint}', Architect Notes='{architect_notes}'.

Current User Request (potentially refined): "{user_request_to_process}"

Consult the Planning Guidelines.
--- BEGIN PLANNING GUIDELINES ---
{planning_guidelines_context}
--- END PLANNING GUIDELINES ---

The current request seems ambiguous or incomplete for direct code generation.
Identify up to 3 specific, concise questions to ask the user to clarify the requirements for a single Python function.
Focus on function name, parameters (names, types, order), return type, and core behavior.
Output ONLY a valid JSON object with one key:
- "clarification_questions": A list of strings, where each string is a question for the user.
  Example: {"clarification_questions": ["What should the function be named?", "What are the input parameters and their types?"]}
"""

PLANNER_CODEGEN_PROMPT_TEMPLATE = """
You are an expert Requirements Analyst and Planner.
Architect Decision: Language='{chosen_language}', Framework Hint='{framework_hint}', Architect Notes='{architect_notes}'.

Current User Request (refined and deemed clear): "{user_request_to_process}"

Consult the Planning Guidelines.
--- BEGIN PLANNING GUIDELINES ---
{planning_guidelines_context}
--- END PLANNING GUIDELINES ---

Define a specific plan for a single Python function based on the request.
Output ONLY a valid JSON object with the following keys:
- "planned_task_description": A detailed description including:
    - Suggested function_name (e.g., "calculate_sum").
    - Input parameters (list of dicts: [{"name": "param1", "type": "int"}, {"name": "param2", "type": "str"}]). If no params, use empty list.
    - Return type (e.g., "int", "str", "list[int]", "None").
    - Core behavior and any specific logic to implement.
- "planner_notes": Any brief, critical notes for the developer (1-2 sentences).
- "clarification_questions": An empty list `[]` as the request is now considered clear.
"""

DEVELOPER_CODEGEN_PROMPT_TEMPLATE = """
You are an expert Python coding assistant.
Task: {developer_task_description}
Planner Notes: {developer_notes}

Consult the Coding Standards.
--- BEGIN CODING STANDARDS ---
{coding_standards_context}
--- END CODING STANDARDS ---

LATEST FEEDBACK TO ADDRESS (if any):
Critique: {critique_message}
--- END LATEST FEEDBACK ---

Full Feedback History (for context, address any unresolved issues from here too):
{full_feedback_history}

Based on the task, planner notes, and ALL feedback (prioritizing the latest), write or revise the Python function.
Include a concise docstring explaining what the function does, its parameters, and what it returns.
Output ONLY the Python code block for the function, enclosed in ```python ... ```. No other text.
"""

TEST_CASE_DESIGNER_PROMPT_TEMPLATE = """
You are a Test Case Designer.
Function Plan:
{function_plan_json_str} 
Planner Notes (for context): {planner_notes}

Your task is to create 2 to 3 diverse test cases for the Python function described in the plan.
Each test case should be a JSON object with:
1. "inputs": A JSON tuple of input values for the function (e.g., `[1, 2]` for two args, `["hello"]` for one string arg, `[]` for no args).
2. "expected_output": The expected output when the function is called with these inputs.
3. "description": A brief (1-sentence) explanation of what this test case covers.

Consider typical cases and simple edge cases (e.g., empty inputs if applicable for strings/lists, zero for numbers).
Output ONLY a valid JSON object with a single key "test_cases", which is a list of these test case objects.

Example for a function `def add(a: int, b: int) -> int:`:
```json
{{
  "test_cases": [
    {{"inputs": [2, 3], "expected_output": 5, "description": "Test with positive integers."}},
    {{"inputs": [-1, 1], "expected_output": 0, "description": "Test with negative and positive integers."}},
    {{"inputs": [0, 0], "expected_output": 0, "description": "Test with zero values."}}
  ]
}}
```

"""

VALIDATION_PROMPT_TEMPLATE = """
You are a Code Validation Agent.
Task Description (for context): {task_description}
Planner Notes (for context): {planner_notes}

Code to Validate:

```python
{code_to_validate}
```

Consult the Validation Rules.
--- BEGIN VALIDATION RULES ---
{validation_rules_context}
--- END VALIDATION RULES ---

Analyze the code against these rules.
Output ONLY a valid JSON object with two keys:
* "validation_passed": boolean (true if no issues, false if any issues are found).
* "issues_found": A list of strings, where each string describes a specific validation issue found. Empty list if validation_passed is true.
"""

CRITIQUE_PROMPT_TEMPLATE = """
You are a Code Critique Agent.
Task Description (for context): {task_description}
Planner Notes (for context): {planner_notes}

Code in Question:

```python
{code_in_question}
```

Reason(s) for Critique:
Test Failure Message (if any): {test_failure_message}
Validation Issues (if any): {validation_issues_list}
User Rejection Reason (if any): {user_rejection_reason}

Consult Debugging Tips if relevant.
--- BEGIN DEBUGGING TIPS ---
{debugging_tips_context}
--- END DEBUGGING TIPS ---

Based on the reasons provided, provide concise, constructive feedback for a developer (1-3 sentences).
Focus on the root cause and suggest specific areas for improvement. Do not rewrite the code yourself.
Output ONLY a valid JSON object with a single key "critique_feedback", which is a string containing your feedback.
Example: {"critique_feedback": "The function fails for empty lists. Add a check for empty input before iterating."}
"""

```

```python
# utils/__init__.py
# This file can be empty, or you can import functions here for easier access
# from .call_llm import call_llm
# from .tools import extract_python_code, code_tester_tool
# from .prompts import (
#     ARCHITECT_PROMPT_TEMPLATE, 
#     PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
#     # ... etc.
# )
# from .database import (
#     init_db,
#     create_task,
#     # ... etc.
# )

```

```python
# rag_contexts/architectural_principles.txt
1. Simplicity: For the MVP, prioritize simple solutions using standard Python libraries.
2. Focus: The primary goal is to generate a single, well-defined Python function.
3. Clarity: Ensure the plan for the function (name, parameters, return type, behavior) is unambiguous.
4. Testability: The function should be easily testable with clear inputs and outputs.
```

```python
# rag_contexts/planning_guidelines.txt
1. Understand the Core Request: Identify the primary action or computation the user wants the function to perform.
2. Define Function Signature:
    - Suggest a clear and descriptive `function_name`.
    - Identify input `parameters`, including their likely names and Python types (e.g., int, str, list, dict).
    - Determine the `return_type` of the function. If it doesn't return anything, use "None".
3. Specify Behavior: Clearly describe what the function should do with the inputs to produce the output. Mention any key logic or steps.
4. Handle Ambiguity: If the user's request is too vague to define the signature or behavior, formulate specific questions to ask the user for clarification. Focus on what's needed to write the function.
5. Task Description Output: The `planned_task_description` should be a concise yet complete specification for the developer. It should be a JSON string containing "function_name", "parameters" (as a list of dicts like `[{"name": "x", "type": "int"}]`), "return_type", and "behavior".
6. Planner Notes: Add any brief, critical implementation notes for the developer if necessary (e.g., "Handle division by zero.").
```

```python
# rag_contexts/coding_standards.txt
1. Function Naming: Use snake_case for function names (e.g., `calculate_total_price`).
2. Docstrings: All functions must have a Google-style docstring.
   Example:
   ```python
   def my_function(param1, param2):
       \"\"\"Does something interesting.

       Args:
           param1 (type): Description of param1.
           param2 (type): Description of param2.

       Returns:
           type: Description of return value.
       \"\"\"
       # ... function body ...
       pass
   ```

3. Type Hinting: Use Python type hints for all function parameters and return values.
4. Imports: Place all imports at the top of the script (though for single functions, imports might be inside if they are very specific and not standard library). For this MVP, assume standard library imports are fine and don't need explicit import statements in the generated function block unless absolutely necessary for clarity (e.g., `import math`).
5. Simplicity: Keep functions concise and focused on a single responsibility.
6. No Print Statements: Functions should return values, not print them, unless printing is the explicit purpose of the function.
7. Error Handling: For MVP, assume valid inputs unless specified in planner_notes. Robust error handling can be added later.

```

```python
# rag_contexts/validation_rules.txt
1. Function Definition: The code must contain a valid Python function definition (`def function_name(...):`).
2. Docstring Presence: The function must have a docstring.
3. Type Hints: Parameters and return type should ideally have type hints (though this is a soft rule for MVP if the LLM struggles).
4. No Infinite Loops: Avoid obvious infinite loop constructs if detectable by static analysis (hard for LLM to fully check).
5. Basic Security: Avoid using `eval()` or `exec()` with unsanitized user input (less relevant for MVP function generation but good practice).
6. Python Syntax: The code must be syntactically valid Python.
7. Adherence to Plan: The function signature (name, parameters) should reasonably match the `planned_task_description`.
```

```python
# rag_contexts/debugging_tips.txt
1. Check Inputs: Ensure the function is called with the correct number and types of arguments as defined

```
------------------


```python
# nodes.py
import logging
import json # Ensure json is imported
from typing import Any, Dict, List, Optional, Tuple

from pocketflow import Node
from utils.call_llm import call_llm
from utils.tools import extract_python_code, code_tester_tool
from utils.prompts import (
    ARCHITECT_PROMPT_TEMPLATE, PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
    PLANNER_CODEGEN_PROMPT_TEMPLATE, DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
    TEST_CASE_DESIGNER_PROMPT_TEMPLATE, VALIDATION_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT_TEMPLATE
)

logger = logging.getLogger(__name__)

class SimpleJsonOutputParser: # Basic parser, can be enhanced
    def parse(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parsing Error in SimpleJsonOutputParser: {e} in text: {text[:200]}...")
            # Return a dict with an error key, so downstream can check state.get("llm_output_error")
            return {"error": f"JSON parsing failed: {e}", "raw_text": text}


class InitialRequestNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Optional[str]:
        logger.info("Entering InitialRequestNode - Prep")
        return shared.get("user_raw_request")

    def exec(self, prep_res: Optional[str]) -> Optional[str]:
        logger.info(f"InitialRequestNode - Executing with: {str(prep_res)[:100]}...")
        # For MVP, just pass through. Could add initial validation here.
        if not prep_res:
            logger.error("InitialRequestNode: No user request provided.")
            return None
        return prep_res

    def post(self, shared: Dict[str, Any], prep_res: Optional[str], exec_res: Optional[str]):
        logger.info("InitialRequestNode - Post")
        if exec_res is None:
            shared["current_error_message"] = "Initial request was empty."
            return "error_encountered" # Or a specific error action

        shared["initial_user_request"] = exec_res
        shared["current_request_for_planner"] = exec_res # Start with raw request for planner
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

        # 1. Architect part (simplified for MVP)
        architect_llm_model = llm_models_config.get("architect_llm", "gpt-4o")
        arch_prompt = ARCHITECT_PROMPT_TEMPLATE.format(
            user_request=current_request,
            architectural_principles_context=arch_principles_ctx
        )
        logger.debug(f"Architect Prompt: {arch_prompt[:200]}...")
        arch_response_str = call_llm(messages=[{"role": "user", "content": arch_prompt}], model=architect_llm_model, temperature=0.1)
        arch_decision = SimpleJsonOutputParser().parse(arch_response_str)
        
        if arch_decision.get("error"):
            logger.error(f"Architect LLM error or parsing failed: {arch_decision['error']}")
            return {"error": "Architect LLM failed", "details": arch_decision.get("raw_text", arch_response_str)}

        logger.info(f"Architect decision: {arch_decision}")

        # 2. Planner part (Clarification or Codegen plan)
        planner_llm_model = llm_models_config.get("planner_llm", "gpt-4o")
        
        # Try to get a codegen plan first
        planner_codegen_prompt = PLANNER_CODEGEN_PROMPT_TEMPLATE.format(
            user_request_to_process=current_request, # Use the potentially clarified request
            planning_guidelines_context=plan_guidelines_ctx,
            chosen_language=arch_decision.get("chosen_language", "python"),
            framework_hint=arch_decision.get("framework_hint", "standard_library"),
            architect_notes=arch_decision.get("high_level_notes", "N/A")
        )
        logger.debug(f"Planner Codegen Prompt: {planner_codegen_prompt[:300]}...")
        planner_response_str = call_llm(messages=[{"role": "user", "content": planner_codegen_prompt}], model=planner_llm_model, temperature=0.2)
        planned_output = SimpleJsonOutputParser().parse(planner_response_str)

        if planned_output.get("error"):
            logger.error(f"Planner Codegen LLM error or parsing failed: {planned_output['error']}")
            # Fallback or re-attempt clarification if direct planning fails due to parsing
            return {"error": "Planner Codegen LLM failed", "details": planned_output.get("raw_text", planner_response_str), "architect_decision": arch_decision}

        # Check if the planner thinks it's clear (empty clarification_questions)
        if planned_output.get("planned_task_description") and not planned_output.get("clarification_questions"):
            logger.info(f"Planner created task description: {str(planned_output['planned_task_description'])[:100]}...")
            return {"architect_decision": arch_decision, "planned_output": planned_output, "needs_clarification": False}

        # If not clear, or if planned_task_description is missing, try asking for clarification questions
        logger.info("Planner determined request needs clarification or codegen plan was insufficient. Asking clarification questions.")
        planner_clar_prompt = PLANNER_CLARIFICATION_PROMPT_TEMPLATE.format(
             user_request_to_process=current_request,
             planning_guidelines_context=plan_guidelines_ctx,
             chosen_language=arch_decision.get("chosen_language", "python"),
             framework_hint=arch_decision.get("framework_hint", "standard_library"),
             architect_notes=arch_decision.get("high_level_notes", "N/A")
        )
        logger.debug(f"Planner Clarification Prompt: {planner_clar_prompt[:300]}...")
        clar_response_str = call_llm(messages=[{"role": "user", "content": planner_clar_prompt}], model=planner_llm_model, temperature=0.3)
        clar_output = SimpleJsonOutputParser().parse(clar_response_str)
        
        if clar_output.get("error"):
            logger.error(f"Planner Clarification LLM error or parsing failed: {clar_output['error']}")
            return {"error": "Planner Clarification LLM failed", "details": clar_output.get("raw_text", clar_response_str), "architect_decision": arch_decision}
            
        logger.info(f"Planner generated clarification questions: {clar_output.get('clarification_questions')}")
        return {"architect_decision": arch_decision, "planned_output": clar_output, "needs_clarification": True}


    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        logger.info("ArchitectPlannerNode - Post")
        shared["planner_iteration_count"] = shared.get("planner_iteration_count", 0) + 1

        if exec_res.get("error"):
            shared["current_error_message"] = f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            logger.error(f"ArchitectPlannerNode error: {shared['current_error_message']}")
            return "error_encountered" # Or a specific error action

        shared["architectural_decision"] = exec_res["architect_decision"]
        planned_output = exec_res["planned_output"]
        
        if exec_res["needs_clarification"] and planned_output.get("clarification_questions"):
            shared["clarification_questions_for_user"] = planned_output["clarification_questions"]
            shared["planned_task_description"] = None # Clear any previous plan
            shared["planner_notes"] = None
            logger.debug("Returning 'clarification_needed'")
            return "clarification_needed"
        elif planned_output.get("planned_task_description"):
            shared["planned_task_description"] = planned_output["planned_task_description"]
            shared["planner_notes"] = planned_output.get("planner_notes")
            shared["task_description"] = str(planned_output["planned_task_description"]) # Ensure it's a string for dev
            shared["clarification_questions_for_user"] = None # Clear questions
            logger.debug("Returning 'plan_ready_for_code'")
            return "plan_ready_for_code"
        else:
            # Should not happen if LLM adheres to one of the two outputs.
            error_msg = "Planner failed to produce a plan or clarification questions."
            logger.error(error_msg + f" LLM output: {planned_output}")
            shared["current_error_message"] = error_msg
            return "error_encountered"


class DeveloperNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering DeveloperNode - Prep")
        return {
            "task_description": shared.get("task_description", ""),
            "planner_notes": shared.get("planner_notes", ""),
            "coding_standards_context": shared.get("coding_standards_context", "N/A"),
            "critique_feedback": shared.get("critique_feedback", "N/A (first attempt or no critique)"),
            "feedback_history": "\n".join([f"- {item}" for item in shared.get("feedback_history", [])]) or "No prior feedback.",
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[str]:
        logger.info(f"DeveloperNode - Executing with task: {str(prep_res['task_description'])[:100]}...")
        llm_model = prep_res["llm_models_config"].get("developer_llm", "gpt-4o")
        
        dev_prompt = DEVELOPER_CODEGEN_PROMPT_TEMPLATE.format(
            developer_task_description=prep_res["task_description"],
            developer_notes=prep_res["planner_notes"],
            coding_standards_context=prep_res["coding_standards_context"],
            critique_message=prep_res["critique_feedback"],
            full_feedback_history=prep_res["feedback_history"]
        )
        logger.debug(f"Developer Prompt: {dev_prompt[:300]}...")
        llm_response_str = call_llm(messages=[{"role": "user", "content": dev_prompt}], model=llm_model, temperature=0.1)
        # The LLM for code gen might not return JSON, so we don't parse it with SimpleJsonOutputParser here.
        # extract_python_code will handle the markdown.
        
        code = extract_python_code(llm_response_str)
        if not code:
            logger.error(f"DeveloperNode: Could not extract Python code. LLM response: {llm_response_str[:200]}...")
            return f"Error: No code block found.\nLLM_Response:\n{llm_response_str}" # Return error string
        return code

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[str]):
        logger.info("DeveloperNode - Post")
        shared["refinement_count"] = shared.get("refinement_count", 0) + 1

        if exec_res and "Error: No code block found" in exec_res:
            shared["current_error_message"] = exec_res
            shared["generated_code"] = None # Ensure no old code persists
            # Add to feedback history to inform next critique/dev attempt
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"DevAttempt {shared['refinement_count']}: Failed to generate code. {exec_res}")
            logger.error(f"DeveloperNode error: {exec_res}")
            return "code_generation_failed"
        
        shared["generated_code"] = exec_res
        logger.debug(f"Generated code (attempt {shared['refinement_count']}):\n{exec_res}")
        # Reset critique after new code is generated
        shared["critique_feedback"] = None 
        shared["current_error_message"] = None
        return "code_ready_for_tests"

class TestCaseDesignerNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering TestCaseDesignerNode - Prep")
        return {
            "planned_task_description": shared.get("planned_task_description"), # This is the structured JSON plan
            "planner_notes": shared.get("planner_notes", ""),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        plan_desc = prep_res["planned_task_description"]
        if not plan_desc or not isinstance(plan_desc, dict):
            logger.error(f"TestCaseDesignerNode: Invalid or missing planned_task_description: {plan_desc}")
            return {"error": "Invalid plan for test case design"}

        # Serialize the plan_desc dict to a JSON string for the prompt
        function_plan_json_str = json.dumps(plan_desc, indent=2)
        logger.info(f"TestCaseDesignerNode - Executing with plan: {function_plan_json_str[:200]}...")
        
        llm_model = prep_res["llm_models_config"].get("developer_llm", "gpt-4o") # Using dev model for this too

        test_case_prompt = TEST_CASE_DESIGNER_PROMPT_TEMPLATE.format(
            function_plan_json_str=function_plan_json_str,
            planner_notes=prep_res["planner_notes"]
        )
        logger.debug(f"TestCaseDesigner Prompt: {test_case_prompt[:300]}...")
        response_str = call_llm(messages=[{"role": "user", "content": test_case_prompt}], model=llm_model, temperature=0.4)
        response_json = SimpleJsonOutputParser().parse(response_str)

        if response_json.get("error"):
            logger.error(f"TestCaseDesigner LLM error or parsing failed: {response_json['error']}")
            return {"error": "Test Case Designer LLM failed", "details": response_json.get("raw_text", response_str)}

        test_cases = response_json.get("test_cases")
        if not test_cases or not isinstance(test_cases, list):
            logger.error(f"TestCaseDesignerNode: 'test_cases' key missing or not a list in LLM response: {response_json}")
            return {"error": "LLM did not return a valid list of test cases"}
        
        # Basic validation of test case structure
        valid_test_cases = []
        for tc in test_cases:
            if isinstance(tc, dict) and "inputs" in tc and "expected_output" in tc and "description" in tc:
                # Ensure inputs is a tuple
                if isinstance(tc["inputs"], list): 
                    tc["inputs"] = tuple(tc["inputs"]) 
                elif not isinstance(tc["inputs"], tuple): # if it's a single non-list/tuple item, wrap in tuple
                    tc["inputs"] = (tc["inputs"],)

                # Ensure function_name is present, deriving from plan if missing
                if "function_name" not in tc or not tc["function_name"]:
                    tc["function_name"] = plan_desc.get("function_name", "unknown_function")
                valid_test_cases.append(tc)
            else:
                logger.warning(f"Skipping malformed test case from LLM: {tc}")
        
        if not valid_test_cases:
            logger.error("TestCaseDesignerNode: No valid test cases generated by LLM.")
            return {"error": "No valid test cases generated"}
            
        return valid_test_cases

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Optional[List[Dict[str, Any]]]):
        logger.info("TestCaseDesignerNode - Post")
        if isinstance(exec_res, dict) and exec_res.get("error"):
            shared["current_error_message"] = f"{exec_res['error']}: {str(exec_res.get('details', ''))[:200]}"
            shared["generated_test_cases"] = []
            logger.error(f"TestCaseDesignerNode error: {shared['current_error_message']}")
            return "error_encountered"

        shared["generated_test_cases"] = exec_res
        shared["current_test_case_index"] = 0
        shared["all_tests_passed"] = False # Reset for new set of tests
        shared["test_results_summary"] = [] # Reset summary
        logger.debug(f"Generated test cases: {exec_res}")
        return "tests_ready"


class QANode(Node):
    def prep(self, shared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger.info("Entering QANode - Prep")
        code = shared.get("generated_code")
        test_cases = shared.get("generated_test_cases")
        current_idx = shared.get("current_test_case_index", 0)

        if not code:
            logger.error("QANode: No generated code to test.")
            return {"error": "No code to test"}
        if not test_cases or current_idx >= len(test_cases):
            logger.info("QANode: No more test cases to run or test cases not generated.")
            return {"error": "No more tests or tests not found"}
        
        current_test_case = test_cases[current_idx]
        # Extract function name from the current test case or overall plan
        function_name = current_test_case.get("function_name") or \
                        (shared.get("planned_task_description", {}).get("function_name") if isinstance(shared.get("planned_task_description"), dict) else "unknown_function")

        return {
            "code_string": code,
            "function_name": function_name,
            "test_case": current_test_case
        }

    def exec(self, prep_res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not prep_res or prep_res.get("error"):
            logger.error(f"QANode - Exec: Skipping due to prep error: {prep_res.get('error') if prep_res else 'No prep_res'}")
            return {"status": "error", "message": prep_res.get("error") if prep_res else "Prep failed", "test_case": None, "actual_output": None}

        code_string = prep_res["code_string"]
        function_name = prep_res["function_name"]
        test_case = prep_res["test_case"]
        
        logger.info(f"QANode - Executing test: {test_case.get('description', 'N/A')} for function '{function_name}'")
        # code_tester_tool expects a list of test cases, so wrap current_test_case
        single_test_results = code_tester_tool(code_string, function_name, [test_case])
        
        if not single_test_results: # Should always return a list
            logger.error("QANode: code_tester_tool returned empty result.")
            return {"status": "error", "message": "Test tool malfunctioned.", "test_case": test_case, "actual_output": None}
            
        return single_test_results[0] # Return the result for the single test case

    def post(self, shared: Dict[str, Any], prep_res: Optional[Dict[str, Any]], exec_res: Optional[Dict[str, Any]]):
        logger.info("QANode - Post")
        if not exec_res or exec_res.get("status") == "error":
            error_msg = exec_res.get("message", "QA execution failed or was skipped.") if exec_res else "QA prep failed."
            logger.error(f"QANode error: {error_msg}")
            shared["current_test_status"] = "error"
            shared["current_test_message"] = error_msg
            # Potentially add to feedback history to indicate tool/QA setup error
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"QA Attempt {shared.get('refinement_count',0)}: Error during test execution - {error_msg}")
            return "testing_error_or_done" # Or a specific error action

        test_result = exec_res
        shared.setdefault("test_results_summary", []).append(test_result)
        shared["current_test_status"] = test_result["status"]
        shared["current_test_message"] = test_result["message"]
        logger.debug(f"Test result: {test_result['status']} - {test_result['message']}")

        shared["current_test_case_index"] = shared.get("current_test_case_index", 0) + 1
        
        if test_result["status"] != "success":
            shared["all_tests_passed"] = False # Mark as failed if any test fails
            # Add specific failure to feedback history for critique
            if "feedback_history" not in shared: shared["feedback_history"] = []
            shared["feedback_history"].append(f"Test Failure (DevAttempt {shared.get('refinement_count',0)} on test '{test_result['test_case'].get('description')}'): {test_result['message']} (Actual: {test_result.get('actual_output')})")
            return "testing_error_or_done" # Go to critique/validation

        if shared["current_test_case_index"] >= len(shared.get("generated_test_cases", [])):
            # All tests for this version have run
            # Check if all passed *in this specific run of tests for the current code version*
            all_current_tests_passed_this_round = all(
                res['status'] == 'success' for res in shared['test_results_summary']
                if res['test_case'] in shared.get("generated_test_cases", []) # Ensure we only check current set
            )
            shared["all_tests_passed"] = all_current_tests_passed_this_round
            logger.info(f"All tests run. Overall pass status for this version: {shared['all_tests_passed']}")
            return "testing_error_or_done" # Go to validation or critique
        else:
            return "run_next_test"


class ValidationNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering ValidationNode - Prep")
        return {
            "generated_code": shared.get("generated_code"),
            "task_description": shared.get("task_description", "N/A"),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "validation_rules_context": shared.get("validation_rules_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        code = prep_res["generated_code"]
        if not code:
            logger.error("ValidationNode: No code to validate.")
            return {"validation_passed": False, "issues_found": ["No code provided for validation."]}

        logger.info(f"ValidationNode - Executing for task: {prep_res['task_description'][:100]}...")
        llm_model = prep_res["llm_models_config"].get("validation_llm", "gpt-4o")

        val_prompt = VALIDATION_PROMPT_TEMPLATE.format(
            task_description=prep_res["task_description"],
            planner_notes=prep_res["planner_notes"],
            code_to_validate=code,
            validation_rules_context=prep_res["validation_rules_context"]
        )
        logger.debug(f"Validation Prompt: {val_prompt[:300]}...")
        response_str = call_llm(messages=[{"role": "user", "content": val_prompt}], model=llm_model, temperature=0.1)
        validation_result = SimpleJsonOutputParser().parse(response_str)
        
        if validation_result.get("error"):
            logger.error(f"Validation LLM error or parsing failed: {validation_result['error']}")
            return {"validation_passed": False, "issues_found": [f"Validation LLM failed: {validation_result['error']}"], "details": validation_result.get("raw_text", response_str)}

        return validation_result

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, Any]):
        logger.info("ValidationNode - Post")
        if isinstance(exec_res, dict) and "validation_passed" in exec_res:
            shared["validation_status"] = "pass" if exec_res["validation_passed"] and not exec_res.get("issues_found") else "fail"
            shared["validation_issues"] = exec_res.get("issues_found", [])
            if not isinstance(shared["validation_issues"], list): # Ensure it's a list
                shared["validation_issues"] = [str(shared["validation_issues"])] if shared["validation_issues"] else []
            if exec_res.get("validation_passed") and shared["validation_issues"]:
                 logger.warning("Validation conflict: LLM said passed but issues were found. Marking as fail.")
                 shared["validation_status"] = "fail"
                 shared["validation_issues"].append("Internal Consistency: LLM reported pass but listed issues.")

        else: # Error case from exec
            shared["validation_status"] = "error"
            shared["validation_issues"] = [str(exec_res.get("details", "Validation agent returned malformed output."))]

        logger.debug(f"Validation status: {shared['validation_status']}, Issues: {shared['validation_issues']}")
        return "validation_done"


class CritiqueNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering CritiqueNode - Prep")
        return {
            "task_description": shared.get("task_description", "N/A"),
            "planner_notes": shared.get("planner_notes", "N/A"),
            "generated_code": shared.get("generated_code", "# No code available"),
            "test_failure_message": shared.get("current_test_message", "N/A (or tests passed/not run)"),
            "validation_issues": shared.get("validation_issues", []),
            "user_rejection_reason": shared.get("user_rejection_reason", "N/A"),
            "debugging_tips_context": shared.get("debugging_tips_context", "N/A"),
            "llm_models_config": shared.get("llm_models_config", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> str:
        logger.info(f"CritiqueNode - Executing...")
        llm_model = prep_res["llm_models_config"].get("critique_llm", "gpt-4o-mini")

        critique_prompt = CRITIQUE_PROMPT_TEMPLATE.format(
            task_description=prep_res["task_description"],
            planner_notes=prep_res["planner_notes"],
            code_in_question=prep_res["generated_code"],
            test_failure_message=prep_res["test_failure_message"],
            validation_issues_list="; ".join(prep_res["validation_issues"]) if prep_res["validation_issues"] else "N/A",
            user_rejection_reason=prep_res["user_rejection_reason"],
            debugging_tips_context=prep_res["debugging_tips_context"]
        )
        logger.debug(f"Critique Prompt: {critique_prompt[:300]}...")
        response_str = call_llm(messages=[{"role": "user", "content": critique_prompt}], model=llm_model, temperature=0.25)
        critique_json = SimpleJsonOutputParser().parse(response_str)

        if critique_json.get("error"):
            logger.error(f"Critique LLM error or parsing failed: {critique_json['error']}")
            return f"Error in critique generation: {critique_json['error']}. Details: {critique_json.get('raw_text', response_str)[:100]}"
            
        feedback = critique_json.get("critique_feedback", "Critique LLM did not provide feedback.")
        return feedback

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: str):
        logger.info("CritiqueNode - Post")
        shared["critique_feedback"] = exec_res
        
        current_feedback_history = shared.get("feedback_history", [])
        # Add latest test/validation results explicitly BEFORE this critique
        # (DeveloperNode will see this full history)
        # This is now handled in QANode and ValidationNode before routing to CritiqueNode
        
        # Add the new critique
        # current_feedback_history.append(f"Critique (DevAttempt {shared.get('refinement_count',0)}): {exec_res}")
        # No, DeveloperNode adds this critique to history after it receives it.
        # CritiqueNode just generates it.

        logger.debug(f"Generated critique: {exec_res}")
        return "refine_code"


class PackageNode(Node):
    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Entering PackageNode - Prep")
        return {
            "generated_code": shared.get("generated_code", "# No final code"),
            "planned_task_description": shared.get("planned_task_description", {})
        }

    def exec(self, prep_res: Dict[str, Any]) -> Dict[str, str]:
        logger.info("PackageNode - Executing")
        code = prep_res["generated_code"]
        plan = prep_res["planned_task_description"]
        
        function_name = plan.get("function_name", "unnamed_function") if isinstance(plan, dict) else "unnamed_function"
        
        # Simple packaging: create a string for a Python file and a basic README
        py_file_content = f"# Auto-generated by FlowForge AI (Simple SDLC App)\n\n{code}\n"
        readme_content = f"""# Function: {function_name}

## Description
This function was automatically generated based on the following plan:
```json
{json.dumps(plan, indent=2)}
```

## Code
```python
{code}
```
"""
        logger.info(f"Packaging artifacts for function: {function_name}")
        return {
            "code_file_content": py_file_content,
            "readme_content": readme_content,
            "function_name": function_name
        }

    def post(self, shared: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Dict[str, str]):
        logger.info("PackageNode - Post")
        shared["packaged_artifacts_info"] = exec_res
        shared["handoff_summary"] = f"Successfully generated and packaged function '{exec_res.get('function_name', 'N/A')}'."
        logger.debug(f"Packaged artifacts: {exec_res.get('function_name')}")
        return "done" # End of flow

```

```python
# flow.py
import logging
from pocketflow import Flow
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
)

logger = logging.getLogger(__name__)

def create_sdlc_flow() -> Flow:
    logger.info("Creating SDLC Flow definition...")
    # Instantiate nodes
    initial_request_node = InitialRequestNode()
    architect_planner_node = ArchitectPlannerNode()
    developer_node = DeveloperNode()
    test_case_designer_node = TestCaseDesignerNode()
    qa_node = QANode()
    validation_node = ValidationNode()
    critique_node = CritiqueNode()
    package_node = PackageNode()
    # Placeholder for a human interaction node (not a PocketFlow node, managed by UI)
    # human_clarification_node = "HUMAN_CLARIFICATION_STAGE_MARKER" 

    # Define the main flow sequence and branches
    initial_request_node >> architect_planner_node

    architect_planner_node - "clarification_needed" >> None # UI will handle this, then re-trigger architect_planner_node
    architect_planner_node - "plan_ready_for_code" >> test_case_designer_node
    architect_planner_node - "error_encountered" >> None # End flow on critical planner error

    test_case_designer_node >> developer_node # Default transition if tests are designed
    test_case_designer_node - "error_encountered" >> None # End flow if test design fails critically

    developer_node - "code_ready_for_tests" >> qa_node
    developer_node - "code_generation_failed" >> critique_node # If dev can't even produce code

    # QA loop for multiple test cases
    qa_node - "run_next_test" >> qa_node # Loop to run all test cases
    qa_node - "testing_error_or_done" >> validation_node # After all tests or if one fails/errors
    
    validation_node - "validation_done" >> critique_node # Always critique after validation unless approved by human
    validation_node - "error_encountered" >> critique_node # If validation itself errors, critique might help

    critique_node - "refine_code" >> developer_node # Loop back to developer for refinement

    # Final packaging after potential human approval (handled by UI state change)
    # For PocketFlow, we assume critique_node directly leads to dev.
    # The UI logic will break this loop if max_refinements is hit or user approves.
    # If we had a "final_approval" action from a HITL node:
    # validation_node - "approved_by_human" >> package_node (This path is managed by Streamlit logic)

    # For now, let's assume the flow ends if critique leads to too many refinements (handled by UI)
    # or if an error path leads to None. `PackageNode` would be triggered by UI after human approval.

    # The flow starting point for the initial request processing.
    # Subsequent stages (like triggering PackageNode) will be handled by Streamlit app.py
    # by running different "sub-flows" or re-running parts of a larger conceptual flow.
    
    # For this simulation, we'll make a linear path to packaging if all goes well.
    # In Streamlit, human review would interrupt this.
    # Simplified "happy path" for pure PocketFlow run:
    validation_node - "validation_done_and_passed" >> package_node # Add this hypothetical path
    
    # For a fully contained PocketFlow, you'd need a node representing human review.
    # Since Streamlit handles that, PocketFlow parts are more like sub-routines.
    # Let's define a main elicitation flow for now.
    
    main_elicitation_and_dev_flow = Flow(start=initial_request_node)
    logger.info("SDLC Flow definition created.")
    return main_elicitation_and_dev_flow


# Separate flow for testing and review cycle
def create_test_review_refine_flow() -> Flow:
    logger.info("Creating Test-Review-Refine Flow definition...")
    # Nodes are already instantiated globally for simplicity in this example
    # In a larger app, you might pass them or re-instantiate.
    developer_node = DeveloperNode()
    test_case_designer_node = TestCaseDesignerNode()
    qa_node = QANode()
    validation_node = ValidationNode()
    critique_node = CritiqueNode()

    # This flow assumes plan and initial code OR critique exist
    # It starts from developer (if refining) or test_case_designer (if first code for plan)
    
    # Path for new code: Design Tests -> Develop -> QA -> Validate -> Critique (if needed)
    test_case_designer_node >> developer_node
    developer_node - "code_ready_for_tests" >> qa_node
    developer_node - "code_generation_failed" >> critique_node
    
    qa_node - "run_next_test" >> qa_node
    qa_node - "testing_error_or_done" >> validation_node # If tests pass or one fails/errors
    
    validation_node - "validation_done" >> critique_node # Always go to critique after automated checks. UI handles approval.
    validation_node - "error_encountered" >> critique_node

    critique_node - "refine_code" >> developer_node # Loop back for refinement

    # This flow is typically started at test_case_designer_node or developer_node via Streamlit
    # For testing, can define a start point.
    # This is more a "segment" of the overall process managed by UI.
    # Let's make a runnable flow starting from test_case_designer for this segment:
    test_refine_flow = Flow(start=test_case_designer_node)
    logger.info("Test-Review-Refine Flow definition created.")
    return test_refine_flow


def create_packaging_flow() -> Flow:
    logger.info("Creating Packaging Flow definition...")
    package_node = PackageNode()
    packaging_flow = Flow(start=package_node)
    logger.info("Packaging Flow definition created.")
    return packaging_flow

# These flows will be invoked by app.py at different stages.

```

```python
# app.py
import streamlit as st
import os
import json
import logging
from pathlib import Path
import sys

# Ensure the package is discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pocketflow import Flow # PocketFlow
from nodes import (
    InitialRequestNode, ArchitectPlannerNode, DeveloperNode,
    TestCaseDesignerNode, QANode, ValidationNode, CritiqueNode, PackageNode
)
from utils.database import (
    init_db, create_task, update_task_field, get_task_data,
    add_code_version, get_latest_code_version,
    log_test_run_result, get_test_results_for_version,
    log_validation_result, log_feedback, get_feedback_history_for_version,
    add_packaged_artifact
)
from utils.prompts import ( # Assuming these are string templates
    ARCHITECT_PROMPT_TEMPLATE, PLANNER_CLARIFICATION_PROMPT_TEMPLATE,
    PLANNER_CODEGEN_PROMPT_TEMPLATE, DEVELOPER_CODEGEN_PROMPT_TEMPLATE,
    TEST_CASE_DESIGNER_PROMPT_TEMPLATE, VALIDATION_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT_TEMPLATE
)

# --- Logger Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constants ---
RAG_CONTEXTS_DIR = Path(__file__).parent / "rag_contexts"
MAX_PLANNER_ITERATIONS = int(os.getenv("MAX_PLANNER_ITERATIONS", "2"))
MAX_REFINEMENTS = int(os.getenv("MAX_REFINEMENTS", "3"))
LLM_MODELS_CONFIG = {
    "architect_llm":  os.getenv("ARCHITECT_LLM_MODEL", "gpt-4o"),
    "planner_llm":    os.getenv("PLANNER_LLM_MODEL", "gpt-4o"),
    "developer_llm":  os.getenv("DEVELOPER_LLM_MODEL", "gpt-3.5-turbo"), # Cheaper for code gen
    "test_designer_llm": os.getenv("TEST_DESIGNER_LLM_MODEL", "gpt-3.5-turbo"),
    "qa_llm":         os.getenv("QA_LLM_MODEL", "gpt-4o"), # QA might need more capability for tool use prompt
    "validation_llm": os.getenv("VALIDATION_LLM_MODEL", "gpt-3.5-turbo"),
    "critique_llm":   os.getenv("CRITIQUE_LLM_MODEL", "gpt-4o-mini")
}

# --- RAG Context Loading ---
def load_rag_context(filename: str) -> str:
    try:
        with open(RAG_CONTEXTS_DIR / filename, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading RAG context {filename}: {e}")
        return f"Error loading {filename}: {e}"

ARCH_PRINCIPLES_CTX = load_rag_context("architectural_principles.txt")
PLAN_GUIDELINES_CTX = load_rag_context("planning_guidelines.txt")
CODE_STANDARDS_CTX = load_rag_context("coding_standards.txt")
VALIDATION_RULES_CTX = load_rag_context("validation_rules.txt")
DEBUGGING_TIPS_CTX = load_rag_context("debugging_tips.txt")

# --- PocketFlow Setup ---
# Instantiate nodes (could be done within flow creation too)
initial_request_node = InitialRequestNode()
architect_planner_node = ArchitectPlannerNode()
developer_node = DeveloperNode()
test_case_designer_node = TestCaseDesignerNode()
qa_node = QANode()
validation_node = ValidationNode()
critique_node = CritiqueNode()
package_node = PackageNode()

# Define elicitation flow
initial_request_node >> architect_planner_node
elicitation_flow = Flow(start=initial_request_node)

# Define test generation and execution flow segment
# Starts from test_case_designer, then dev, then QA loop, then validation
test_case_designer_node >> developer_node
developer_node - "code_ready_for_tests" >> qa_node
developer_node - "code_generation_failed" >> critique_node # Handle direct code gen failure
qa_node - "run_next_test" >> qa_node
qa_node - "testing_error_or_done" >> validation_node
validation_node - "validation_done" >> None # End of this segment, UI decides next
validation_node - "error_encountered" >> None
testing_flow_segment = Flow(start=test_case_designer_node) # Starts with designing tests for a plan

# Define refinement flow segment (Critique -> Developer)
critique_node - "refine_code" >> developer_node
refinement_flow_segment = Flow(start=critique_node)

# Define packaging flow
packaging_flow = Flow(start=package_node)


# --- Streamlit UI ---
st.set_page_config(layout="wide")
st.title("🚧 Simple Autonomous Software Factory (MVP) 🏭")
st.caption("Describe a Python function, and AI agents will try to build, test, and validate it with your guidance.")

# --- Initialize Session State ---
if "ui_stage" not in st.session_state:
    st.session_state.ui_stage = "INPUT_REQUIREMENTS"
    st.session_state.active_task_id = None
    st.session_state.user_raw_request = ""
    st.session_state.current_request_for_planner = ""
    st.session_state.architectural_decision = None
    st.session_state.planner_iteration_count = 0
    st.session_state.clarification_questions_for_user = None
    st.session_state.planned_task_description = None
    st.session_state.planner_notes = None
    st.session_state.generated_code = None
    st.session_state.active_code_version_id = None
    st.session_state.generated_test_cases = None
    st.session_state.current_test_case_index = 0
    st.session_state.test_results_summary = []
    st.session_state.all_tests_passed = False
    st.session_state.validation_status = None
    st.session_state.validation_issues = None
    st.session_state.user_rejection_reason = ""
    st.session_state.critique_feedback = None
    st.session_state.feedback_history = []
    st.session_state.refinement_count = 0
    st.session_state.packaged_artifacts_info = None
    st.session_state.handoff_summary = None
    st.session_state.current_error_message = None
    init_db() # Ensure DB and tables exist

# --- RAG Contexts (Load once and store in session state if not already there) ---
if "rag_contexts_loaded" not in st.session_state:
    st.session_state.architectural_principles_context = ARCH_PRINCIPLES_CTX
    st.session_state.planning_guidelines_context = PLAN_GUIDELINES_CTX
    st.session_state.coding_standards_context = CODE_STANDARDS_CTX
    st.session_state.validation_rules_context = VALIDATION_RULES_CTX
    st.session_state.debugging_tips_context = DEBUGGING_TIPS_CTX
    st.session_state.rag_contexts_loaded = True

# --- Helper functions for UI stages ---
def reset_for_new_task():
    st.session_state.ui_stage = "INPUT_REQUIREMENTS"
    st.session_state.active_task_id = None
    st.session_state.user_raw_request = "" # Cleared for new input
    st.session_state.current_request_for_planner = ""
    st.session_state.architectural_decision = None
    st.session_state.planner_iteration_count = 0
    st.session_state.clarification_questions_for_user = None
    st.session_state.planned_task_description = None
    st.session_state.planner_notes = None
    st.session_state.generated_code = None
    st.session_state.active_code_version_id = None
    st.session_state.generated_test_cases = None
    st.session_state.current_test_case_index = 0
    st.session_state.test_results_summary = []
    st.session_state.all_tests_passed = False
    st.session_state.validation_status = None
    st.session_state.validation_issues = None
    st.session_state.user_rejection_reason = ""
    st.session_state.critique_feedback = None
    st.session_state.feedback_history = []
    st.session_state.refinement_count = 0
    st.session_state.packaged_artifacts_info = None
    st.session_state.handoff_summary = None
    st.session_state.current_error_message = None
    logger.info("UI state reset for new task.")

def display_error():
    if st.session_state.current_error_message:
        st.error(f"An error occurred: {st.session_state.current_error_message}")
        st.session_state.current_error_message = None # Clear after displaying

# --- UI Rendering based on Stage ---

if st.session_state.ui_stage == "INPUT_REQUIREMENTS":
    st.header("1. Describe Your Python Function")
    user_input = st.text_area("What function would you like the AI to create?", 
                              value=st.session_state.user_raw_request, height=150, key="raw_req_input")
    
    if st.button("Generate Function Plan"):
        if not user_input.strip():
            st.warning("Please describe the function you need.")
        else:
            st.session_state.user_raw_request = user_input
            st.session_state.current_request_for_planner = user_input # Initial request
            
            task_id = create_task(st.session_state.user_raw_request)
            if task_id:
                st.session_state.active_task_id = task_id
                logger.info(f"New task created with ID: {task_id} for request: {user_input[:50]}...")
                
                # Prepare shared state for PocketFlow
                shared_for_flow = {
                    "user_raw_request": st.session_state.user_raw_request,
                    "current_request_for_planner": st.session_state.current_request_for_planner,
                    "architectural_principles_context": st.session_state.architectural_principles_context,
                    "planning_guidelines_context": st.session_state.planning_guidelines_context,
                    "planner_iteration_count": 0, # Reset for new task
                    "llm_models_config": LLM_MODELS_CONFIG
                }
                
                with st.spinner("Architect & Planner are thinking..."):
                    try:
                        action = elicitation_flow.run(shared_for_flow)
                        # Update session state from shared_for_flow
                        st.session_state.update(shared_for_flow)
                        update_task_field(task_id, "architectural_decision", json.dumps(shared_for_flow.get("architectural_decision")) if shared_for_flow.get("architectural_decision") else None)
                        update_task_field(task_id, "planner_iteration_count", shared_for_flow.get("planner_iteration_count", 0))
                        
                        if action == "clarification_needed":
                            st.session_state.ui_stage = "CLARIFICATION"
                            update_task_field(task_id, "status", "clarification_needed")
                        elif action == "plan_ready_for_code":
                            st.session_state.ui_stage = "TEST_GENERATION"
                            update_task_field(task_id, "planned_task_description", json.dumps(shared_for_flow.get("planned_task_description")))
                            update_task_field(task_id, "planner_notes", shared_for_flow.get("planner_notes"))
                            update_task_field(task_id, "status", "plan_ready")
                        else: # Error or unexpected
                            st.session_state.current_error_message = shared_for_flow.get("current_error_message", "Planning failed.")
                            update_task_field(task_id, "current_error_message", st.session_state.current_error_message)
                            update_task_field(task_id, "status", "planning_error")
                    except Exception as e:
                        logger.error(f"Error during elicitation flow: {e}", exc_info=True)
                        st.session_state.current_error_message = f"Critical error in planning: {e}"
                        update_task_field(task_id, "current_error_message", st.session_state.current_error_message)
                        update_task_field(task_id, "status", "planning_error")
                st.rerun()
            else:
                st.error("Failed to create a new task in the database.")

elif st.session_state.ui_stage == "CLARIFICATION":
    st.header("1b. Clarification Needed")
    st.info("The planner needs more information to proceed. Please answer the questions below:")
    
    questions = st.session_state.get("clarification_questions_for_user", [])
    user_answers = {}
    for i, q_text in enumerate(questions):
        user_answers[f"answer_{i}"] = st.text_area(f"Question {i+1}: {q_text}", key=f"clar_q_{i}")

    if st.button("Submit Clarifications"):
        refined_request_parts = [st.session_state.current_request_for_planner] # Start with previous request
        for i, q_text in enumerate(questions):
            refined_request_parts.append(f"\nRegarding '{q_text}': {user_answers[f'answer_{i}']}")
        
        st.session_state.current_request_for_planner = " ".join(refined_request_parts)
        st.session_state.clarification_questions_for_user = None # Clear questions
        
        # Log this interaction (optional, could be a feedback log)
        log_feedback(st.session_state.active_task_id, None, "user_clarification", st.session_state.current_request_for_planner)
        
        if st.session_state.planner_iteration_count >= MAX_PLANNER_ITERATIONS:
            st.session_state.current_error_message = "Maximum planner iterations reached. Please refine your initial request and start over."
            st.session_state.ui_stage = "FAILED_PLANNING"
            update_task_field(st.session_state.active_task_id, "status", "failed_planning_max_iterations")
        else:
            # Re-run planner part of elicitation_flow
            shared_for_flow = {
                "user_raw_request": st.session_state.user_raw_request, # Keep original for reference
                "current_request_for_planner": st.session_state.current_request_for_planner,
                "architectural_decision": st.session_state.architectural_decision, # Pass existing
                "architectural_principles_context": st.session_state.architectural_principles_context,
                "planning_guidelines_context": st.session_state.planning_guidelines_context,
                "planner_iteration_count": st.session_state.planner_iteration_count,
                "llm_models_config": LLM_MODELS_CONFIG
            }
            with st.spinner("Planner is re-evaluating with your clarifications..."):
                try:
                    # Directly run architect_planner_node as we are iterating on planning
                    action = architect_planner_node.run(shared_for_flow) 
                    st.session_state.update(shared_for_flow) # Update session state with results
                    update_task_field(st.session_state.active_task_id, "planner_iteration_count", shared_for_flow.get("planner_iteration_count", 0))

                    if action == "clarification_needed":
                        st.session_state.ui_stage = "CLARIFICATION" # Stay if more questions
                        update_task_field(st.session_state.active_task_id, "status", "clarification_needed")
                    elif action == "plan_ready_for_code":
                        st.session_state.ui_stage = "TEST_GENERATION"
                        update_task_field(st.session_state.active_task_id, "planned_task_description", json.dumps(shared_for_flow.get("planned_task_description")))
                        update_task_field(st.session_state.active_task_id, "planner_notes", shared_for_flow.get("planner_notes"))
                        update_task_field(st.session_state.active_task_id, "status", "plan_ready")
                    else:
                        st.session_state.current_error_message = shared_for_flow.get("current_error_message", "Planning failed after clarification.")
                        update_task_field(st.session_state.active_task_id, "current_error_message", st.session_state.current_error_message)
                        update_task_field(st.session_state.active_task_id, "status", "planning_error")
                except Exception as e:
                    logger.error(f"Error during planner re-evaluation: {e}", exc_info=True)
                    st.session_state.current_error_message = f"Critical error in re-planning: {e}"
                    update_task_field(st.session_state.active_task_id, "current_error_message", st.session_state.current_error_message)
                    update_task_field(st.session_state.active_task_id, "status", "planning_error")
        st.rerun()

elif st.session_state.ui_stage == "TEST_GENERATION":
    st.header("2. Generating Code & Tests")
    st.info("AI is now generating test cases and the initial code based on the plan...")
    
    shared_for_flow = {
        "planned_task_description": st.session_state.planned_task_description,
        "planner_notes": st.session_state.planner_notes,
        "coding_standards_context": st.session_state.coding_standards_context,
        "feedback_history": [], # Fresh start for code gen
        "refinement_count": 0, # First attempt
        "llm_models_config": LLM_MODELS_CONFIG,
        # For QA node later
        "test_results_summary": [],
        "all_tests_passed": False,
        "current_test_case_index": 0
    }

    with st.spinner("Designing test cases and writing initial code..."):
        try:
            # Run the testing_flow_segment which starts with TestCaseDesignerNode
            # This flow will design tests, then generate code, then run QA, then validate
            action = testing_flow_segment.run(shared_for_flow)
            st.session_state.update(shared_for_flow) # Update with all results
            
            # Persist to DB
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "status", "review_pending")
                if shared_for_flow.get("generated_code"):
                    cv_id = add_code_version(st.session_state.active_task_id, shared_for_flow["generated_code"], shared_for_flow.get("refinement_count", 0))
                    st.session_state.active_code_version_id = cv_id
                    if shared_for_flow.get("test_results_summary"):
                        for res in shared_for_flow["test_results_summary"]:
                            log_test_run_result(st.session_state.active_task_id, cv_id, res["test_case"].get("description","N/A"), res["status"], res.get("actual_output"), res["message"])
                if shared_for_flow.get("validation_status"):
                     log_validation_result(st.session_state.active_task_id, st.session_state.active_code_version_id, shared_for_flow["validation_status"], shared_for_flow.get("validation_issues"))
            
            st.session_state.ui_stage = "HUMAN_REVIEW"
        except Exception as e:
            logger.error(f"Error during test generation/code/QA flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critical error in test/code/QA stage: {e}"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "current_error_message", str(e))
                update_task_field(st.session_state.active_task_id, "status", "error_in_test_code_qa")
    st.rerun()


elif st.session_state.ui_stage == "HUMAN_REVIEW":
    st.header("3. Review Code, Tests, and Validation")
    
    st.subheader("Generated Code:")
    st.code(st.session_state.get("generated_code", "# No code generated yet."), language="python")

    st.subheader("Test Cases & Results:")
    if st.session_state.get("generated_test_cases"):
        for i, tc_result in enumerate(st.session_state.get("test_results_summary", [])):
            tc = tc_result["test_case"]
            status_icon = "✅" if tc_result["status"] == "success" else "❌"
            with st.expander(f"Test {i+1}: {status_icon} {tc.get('description', 'N/A')}", expanded=(tc_result["status"] != "success")):
                st.json({"inputs": tc["inputs"], "expected_output": tc["expected_output"]})
                st.write(f"Status: {tc_result['status']}")
                st.write(f"Message: {tc_result['message']}")
                if tc_result["status"] != "success":
                    st.write(f"Actual Output: {tc_result.get('actual_output')}")
    else:
        st.info("No test cases were generated or run.")

    st.subheader("Validation Status:")
    val_status = st.session_state.get("validation_status", "Not run")
    if val_status == "pass":
        st.success("Validation Passed.")
    elif val_status in ["fail", "error"]:
        st.error(f"Validation Failed/Errored: {val_status}")
        issues = st.session_state.get("validation_issues", [])
        if issues:
            st.write("Issues Found:")
            for issue in issues: st.warning(f"- {issue}")
        else:
            st.write("No specific issues listed by validator.")
    else:
        st.info("Validation not yet run or status unknown.")

    overall_pass = st.session_state.get("all_tests_passed", False) and st.session_state.get("validation_status") == "pass"
    
    col1, col2, col3 = st.columns([1,1,3])
    with col1:
        if st.button("✅ Approve Code", disabled=not overall_pass):
            st.session_state.ui_stage = "COMPLETED"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "status", "approved_by_human")
                log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "user_approval", "Code approved by user.")
            st.rerun()
    
    with col2:
        if st.button("❌ Reject & Refine"):
            if st.session_state.refinement_count >= MAX_REFINEMENTS:
                st.session_state.ui_stage = "MAX_REFINEMENTS_FAILED"
                if st.session_state.active_task_id:
                     update_task_field(st.session_state.active_task_id, "status", "failed_max_refinements")
            else:
                st.session_state.ui_stage = "PROVIDE_REJECTION_FEEDBACK"
            st.rerun()

    if not overall_pass:
        st.warning("Code cannot be approved until all tests pass and validation is successful.")


elif st.session_state.ui_stage == "PROVIDE_REJECTION_FEEDBACK":
    st.header("3b. Provide Feedback for Refinement")
    st.info(f"This is refinement attempt {st.session_state.refinement_count + 1} of {MAX_REFINEMENTS}.")
    st.subheader("Current Code:")
    st.code(st.session_state.get("generated_code", ""), language="python")
    st.subheader("Test/Validation Issues:")
    if st.session_state.get("test_results_summary"):
        for res in st.session_state.test_results_summary:
            if res["status"] != "success": st.warning(f"Test Fail: {res['test_case'].get('description','N/A')} - {res['message']}")
    if st.session_state.get("validation_issues"):
        for issue in st.session_state.validation_issues: st.warning(f"Validation Issue: {issue}")

    rejection_reason = st.text_area("Reason for rejection / specific feedback for the AI developer:", 
                                    value=st.session_state.user_rejection_reason, height=100, key="rejection_input")
    if st.button("Submit Feedback & Retry Generation"):
        if not rejection_reason.strip() and not st.session_state.get("test_results_summary") and not st.session_state.get("validation_issues"):
            st.warning("Please provide a reason if there are no automated failures.")
        else:
            st.session_state.user_rejection_reason = rejection_reason
            st.session_state.ui_stage = "CRITIQUE_AND_REFINE"
            if st.session_state.active_task_id:
                log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "user_rejection", rejection_reason)
            st.rerun()

elif st.session_state.ui_stage == "CRITIQUE_AND_REFINE":
    st.header("4. AI Critiquing & Refining Code")
    st.info("The AI Critique Agent is reviewing the issues and providing feedback to the Developer Agent...")

    shared_for_flow = {
        "task_description": st.session_state.task_description,
        "planner_notes": st.session_state.planner_notes,
        "generated_code": st.session_state.generated_code,
        "current_test_message": "\n".join([f"{r['test_case'].get('description')}: {r['message']}" for r in st.session_state.test_results_summary if r['status'] != 'success']),
        "validation_issues": st.session_state.validation_issues,
        "user_rejection_reason": st.session_state.user_rejection_reason, # Added
        "debugging_tips_context": st.session_state.debugging_tips_context,
        "feedback_history": st.session_state.feedback_history, # Pass current history
        "refinement_count": st.session_state.refinement_count, # Pass current count
        "llm_models_config": LLM_MODELS_CONFIG
    }
    
    with st.spinner("AI agents are collaborating on a revision..."):
        try:
            # Run refinement_flow_segment (Critique -> Developer)
            action = refinement_flow_segment.run(shared_for_flow)
            st.session_state.update(shared_for_flow) # Update with critique and new code
            
            if st.session_state.active_task_id and shared_for_flow.get("critique_feedback"):
                log_feedback(st.session_state.active_task_id, st.session_state.active_code_version_id, "ai_critique", shared_for_flow["critique_feedback"])
            
            if action == "code_ready_for_tests": # Means DeveloperNode in refinement flow finished
                st.session_state.ui_stage = "TEST_GENERATION_REFINED" # New stage to re-run tests on new code
                if st.session_state.active_task_id:
                    update_task_field(st.session_state.active_task_id, "status", "refining_code")
                    update_task_field(st.session_state.active_task_id, "refinement_count", shared_for_flow.get("refinement_count"))
            else: # e.g. code_generation_failed from DeveloperNode
                st.session_state.current_error_message = shared_for_flow.get("current_error_message", "Refinement failed.")
                if st.session_state.active_task_id:
                    update_task_field(st.session_state.active_task_id, "current_error_message", st.session_state.current_error_message)
                    update_task_field(st.session_state.active_task_id, "status", "refinement_error")
        except Exception as e:
            logger.error(f"Error during critique/refinement flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critical error in critique/refinement: {e}"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "current_error_message", str(e))
                update_task_field(st.session_state.active_task_id, "status", "refinement_error")
    st.rerun()

elif st.session_state.ui_stage == "TEST_GENERATION_REFINED":
    st.header(f"2b. Testing Refined Code (Attempt {st.session_state.refinement_count})")
    st.info("AI is now re-running tests and validation on the refined code...")
    
    shared_for_flow = {
        "generated_code": st.session_state.generated_code, # Use the newly refined code
        "generated_test_cases": st.session_state.generated_test_cases, # Re-use same test cases
        "current_test_case_index": 0, # Reset test index
        "test_results_summary": [],   # Reset summary for this round
        "all_tests_passed": False,
        "task_description": st.session_state.task_description, # For validation
        "planner_notes": st.session_state.planner_notes, # For validation
        "validation_rules_context": st.session_state.validation_rules_context,
        "llm_models_config": LLM_MODELS_CONFIG
    }
    
    with st.spinner(f"Re-testing and validating code (Attempt {st.session_state.refinement_count})..."):
        try:
            # We need a flow that starts from QA, then goes to Validation.
            # The testing_flow_segment starts from TestCaseDesigner, which we don't want here.
            # Let's manually run qa_node and then validation_node.
            
            # Run QA loop
            current_test_idx = 0
            temp_test_results = []
            all_passed_this_round = True

            while current_test_idx < len(shared_for_flow["generated_test_cases"]):
                shared_for_flow["current_test_case_index"] = current_test_idx
                qa_action = qa_node.run(shared_for_flow) # shared_for_flow will be updated by qa_node
                temp_test_results.append(shared_for_flow["test_results_summary"][-1]) # Store latest result
                if shared_for_flow["current_test_status"] != "success":
                    all_passed_this_round = False
                    # No need to break, run all tests to get full feedback
                current_test_idx +=1 # qa_node post already increments, but for clarity
            
            shared_for_flow["test_results_summary"] = temp_test_results
            shared_for_flow["all_tests_passed"] = all_passed_this_round

            # Run Validation
            validation_action = validation_node.run(shared_for_flow) # shared_for_flow updated

            st.session_state.update(shared_for_flow) # Update main session state
            
            # Persist to DB
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "status", "review_pending_refined")
                if shared_for_flow.get("generated_code"): # This is the refined code
                    # We might want to log this as a new version tied to the same task_id but new refinement_count
                    cv_id = add_code_version(st.session_state.active_task_id, shared_for_flow["generated_code"], shared_for_flow.get("refinement_count", 0))
                    st.session_state.active_code_version_id = cv_id # Update active code version
                    if shared_for_flow.get("test_results_summary"):
                        for res in shared_for_flow["test_results_summary"]:
                             log_test_run_result(st.session_state.active_task_id, cv_id, res["test_case"].get("description","N/A"), res["status"], res.get("actual_output"), res["message"])
                if shared_for_flow.get("validation_status"):
                    log_validation_result(st.session_state.active_task_id, st.session_state.active_code_version_id, shared_for_flow["validation_status"], shared_for_flow.get("validation_issues"))

            st.session_state.ui_stage = "HUMAN_REVIEW" # Back to human review
        except Exception as e:
            logger.error(f"Error during refined test/validation flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Critical error in refined test/validation: {e}"
            if st.session_state.active_task_id:
                update_task_field(st.session_state.active_task_id, "current_error_message", str(e))
                update_task_field(st.session_state.active_task_id, "status", "error_in_refined_test_qa")
    st.rerun()

elif st.session_state.ui_stage == "COMPLETED":
    st.header("5. Task Completed Successfully! 🎉")
    
    shared_for_flow = {
        "generated_code": st.session_state.generated_code,
        "planned_task_description": st.session_state.planned_task_description
    }
    with st.spinner("Packaging final artifacts..."):
        try:
            action = packaging_flow.run(shared_for_flow)
            st.session_state.update(shared_for_flow)
            
            if st.session_state.active_task_id and shared_for_flow.get("packaged_artifacts_info"):
                add_packaged_artifact(st.session_state.active_task_id, shared_for_flow["packaged_artifacts_info"], shared_for_flow.get("handoff_summary", ""))
                update_task_field(st.session_state.active_task_id, "status", "completed")
        except Exception as e:
            logger.error(f"Error during packaging flow: {e}", exc_info=True)
            st.session_state.current_error_message = f"Error packaging artifacts: {e}"


    st.balloons()
    st.subheader("Final Generated Code:")
    st.code(st.session_state.get("generated_code", "# Error retrieving final code."), language="python")
    if st.session_state.get("packaged_artifacts_info"):
        st.subheader("Packaged Artifacts Info:")
        st.json(st.session_state.packaged_artifacts_info)
    if st.session_state.get("handoff_summary"):
        st.success(st.session_state.handoff_summary)
    
    if st.button("Start New Function Request"):
        reset_for_new_task()
        st.rerun()

elif st.session_state.ui_stage in ["MAX_REFINEMENTS_FAILED", "FAILED_PLANNING"]:
    if st.session_state.ui_stage == "MAX_REFINEMENTS_FAILED":
        st.header("😔 Task Failed: Maximum Refinements Reached")
        st.error(f"The AI could not produce a satisfactory function after {MAX_REFINEMENTS} refinement attempts.")
        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "failed_max_refinements")
    elif st.session_state.ui_stage == "FAILED_PLANNING":
        st.header("😔 Task Failed: Planning Stage")
        st.error(f"The AI planner could not create a satisfactory plan after {st.session_state.planner_iteration_count} iterations or encountered an error.")
        if st.session_state.active_task_id: update_task_field(st.session_state.active_task_id, "status", "failed_planning")

    st.subheader("Last Generated Code (if any):")
    st.code(st.session_state.get("generated_code", "# No code was generated or an error occurred before code generation."), language="python")
    st.subheader("Last Critique/Feedback (if any):")
    st.warning(st.session_state.get("critique_feedback", "No specific critique available."))
    if st.session_state.get("current_error_message"):
        st.error(f"Last Error: {st.session_state.current_error_message}")
    
    if st.button("Start New Function Request"):
        reset_for_new_task()
        st.rerun()

# Display any error messages at the bottom
display_error()

# --- Sidebar for Task History / Load (Future Enhancement) ---
# st.sidebar.title("Task History")
# task_list = get_all_tasks_summary() # New DB function needed
# if task_list:
#     for task_info in task_list:
#         if st.sidebar.button(f"Load Task {task_info['task_id']}: {task_info['initial_request'][:30]}...", key=f"load_{task_info['task_id']}"):
#             load_task_into_session_state(task_info['task_id']) # New helper needed
#             st.rerun()
# else:
#     st.sidebar.info("No tasks yet.")

with st.sidebar:
    st.header("Debug Info")
    if st.session_state.active_task_id:
        st.write(f"Active Task ID: {st.session_state.active_task_id}")
    st.write(f"Current UI Stage: {st.session_state.ui_stage}")
    st.write(f"Planner Iterations: {st.session_state.planner_iteration_count}/{MAX_PLANNER_ITERATIONS}")
    st.write(f"Refinement Iterations: {st.session_state.refinement_count}/{MAX_REFINEMENTS}")
    if st.button("Force Reset Full State"):
        for key in list(st.session_state.keys()): # Iterate over a copy of keys
            del st.session_state[key]
        st.rerun() # Re-initializes to default

    with st.expander("Session State Details"):
        st.json({k: str(v)[:200] + '...' if isinstance(v, str) and len(str(v)) > 200 else v for k,v in st.session_state.items()})

```

**Next Steps:**

1.  **Dockerfile:** Create the `Dockerfile`.
2.  **requirements.txt:** Create `requirements.txt`.

I'll provide these next. After that, we should be able to build and run the Docker container.