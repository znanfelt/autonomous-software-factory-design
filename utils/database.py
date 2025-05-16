
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
