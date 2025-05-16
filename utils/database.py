# utils/database.py
import sqlite3
import json
import os
from typing import Any, List, Tuple, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DB_FILE = "database/sdlc_tasks.db" # Default, can be overridden for testing

def get_db_connection(db_file_path: str = DB_FILE) -> Optional[sqlite3.Connection]:
    """Establish a connection to the SQLite database."""
    try:
        # Ensure the directory for the database exists
        db_dir = os.path.dirname(db_file_path)
        if db_dir: # Only create if db_file_path includes a directory
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(db_file_path)
        conn.row_factory = sqlite3.Row # Access columns by name
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database at {db_file_path}: {e}", exc_info=True)
        return None

def init_db(db_file_path: str = DB_FILE):
    """Initialize the database with necessary tables if they don't exist."""
    conn = get_db_connection(db_file_path)
    if conn is None:
        logger.error(f"Cannot initialize database, connection failed for {db_file_path}.")
        return

    try:
        cursor = conn.cursor()
        # Tasks table: Core information about each SDLC task
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                initial_request TEXT NOT NULL,
                architectural_decision TEXT,        -- JSON: chosen_language, framework_hint, high_level_notes
                planned_task_description TEXT,      -- JSON: function_name, parameters, return_type, behavior
                planner_notes TEXT,
                status TEXT DEFAULT 'created',      -- e.g., created, planning, coding, review, completed, failed
                refinement_count INTEGER DEFAULT 0,
                current_error_message TEXT,
                planner_iteration_count INTEGER DEFAULT 0,
                generated_test_cases_json TEXT,    -- JSON: List of test case dicts
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Code Versions: Stores each version of generated code for a task
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_versions (
                code_version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                iteration_number INTEGER NOT NULL, -- Corresponds to refinement_count
                generated_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
            );
        """)
        # Test Run Results: Log for each test case executed against a code version
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_run_results (
                test_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER NOT NULL,
                test_case_description TEXT, -- Store description for clarity
                status TEXT NOT NULL,       -- 'success', 'fail', 'error', 'compilation_error', 'runtime_error'
                actual_output TEXT,         -- JSON serialized
                message TEXT,               -- Error message or details
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id) ON DELETE CASCADE
            );
        """)
        # Validation Logs: Records of validation attempts on code versions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_logs (
                validation_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER NOT NULL,
                status TEXT NOT NULL,       -- 'pass', 'fail', 'error'
                issues_found TEXT,          -- JSON serialized list of strings
                validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id) ON DELETE CASCADE
            );
        """)
        # Feedback Logs: User feedback, AI critiques
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_logs (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER,    -- Optional, could be general task feedback
                feedback_type TEXT NOT NULL, -- 'user_rejection', 'user_clarification', 'ai_critique', 'system_error'
                feedback_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id) ON DELETE CASCADE
            );
        """)
        # Packaged Artifacts: Final output of a successful task
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS packaged_artifacts (
                artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL UNIQUE, -- Each task has one set of final artifacts
                info TEXT,                   -- JSON: e.g., {"code_file_content": "...", "readme_content": "..."}
                handoff_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
            );
        """)
        conn.commit()
        logger.info(f"Database initialized successfully at {db_file_path}.")
    except sqlite3.Error as e:
        logger.error(f"Error initializing database at {db_file_path}: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def execute_query(db_file_path: str, query: str, params: Tuple = (), fetch_one=False, fetch_all=False, last_row_id=False):
    """Execute a SQL query and optionally fetch results."""
    conn = get_db_connection(db_file_path)
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        
        if last_row_id: return cursor.lastrowid
        if fetch_one: return cursor.fetchone()
        if fetch_all: return cursor.fetchall()
        return True 
    except sqlite3.Error as e:
        logger.error(f"Error executing query '{query[:50]}...': {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()

# --- Task Management ---
ALLOWED_TASK_FIELDS = [
    "initial_request", "architectural_decision", "planned_task_description", 
    "planner_notes", "status", "refinement_count", "current_error_message", 
    "planner_iteration_count", "generated_test_cases_json", "updated_at"
]

def create_task(initial_request: str, db_file: str = DB_FILE) -> Optional[int]:
    query = "INSERT INTO tasks (initial_request, status, updated_at) VALUES (?, ?, ?)"
    return execute_query(db_file, query, (initial_request, 'created', datetime.now().isoformat()), last_row_id=True)

def get_task_data(task_id: int, db_file: str = DB_FILE) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM tasks WHERE task_id = ?"
    row = execute_query(db_file, query, (task_id,), fetch_one=True)
    if row:
        task_data = dict(row) # sqlite3.Row can be directly converted to dict
        for field in ["architectural_decision", "planned_task_description", "generated_test_cases_json"]:
            if field in task_data and task_data[field]:
                try:
                    task_data[field] = json.loads(task_data[field])
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Could not parse JSON for field {field} in task {task_id}. Value: {task_data[field]}")
                    task_data[field] = None 
        return task_data
    return None

def update_task_field(task_id: int, field_name: str, field_value: Any, db_file: str = DB_FILE) -> bool:
    if field_name not in ALLOWED_TASK_FIELDS:
        logger.error(f"Error: Invalid field name '{field_name}' for task update. Allowed: {ALLOWED_TASK_FIELDS}")
        return False
    
    value_to_store = json.dumps(field_value) if isinstance(field_value, (dict, list)) else field_value
    query = f"UPDATE tasks SET {field_name} = ?, updated_at = ? WHERE task_id = ?"
    return execute_query(db_file, query, (value_to_store, datetime.now().isoformat(), task_id)) is True # Ensure it's boolean

# --- Code Version Management ---
def add_code_version(task_id: int, code: str, iteration: int, db_file: str = DB_FILE) -> Optional[int]:
    query = "INSERT INTO code_versions (task_id, generated_code, iteration_number) VALUES (?, ?, ?)"
    return execute_query(db_file, query, (task_id, code, iteration), last_row_id=True)

def get_latest_code_version(task_id: int, db_file: str = DB_FILE) -> Optional[Dict[str, Any]]:
    query = "SELECT code_version_id, generated_code, iteration_number FROM code_versions WHERE task_id = ? ORDER BY created_at DESC LIMIT 1"
    row = execute_query(db_file, query, (task_id,), fetch_one=True)
    if row: return dict(row)
    return None

# --- Test Case & Result Management ---
def log_test_run_result(task_id: int, code_version_id: int, test_case_desc: str, status: str, 
                        actual_output: Any, message: str, db_file: str = DB_FILE) -> Optional[int]:
    query = """
        INSERT INTO test_run_results 
        (task_id, code_version_id, test_case_description, status, actual_output, message) 
        VALUES (?, ?, ?, ?, ?, ?)
    """ 
    return execute_query(db_file, query, (task_id, code_version_id, test_case_desc, status, json.dumps(actual_output), message), last_row_id=True)

def get_test_results_for_version(code_version_id: int, db_file: str = DB_FILE) -> List[Dict]:
    query = "SELECT test_case_description, status, actual_output, message FROM test_run_results WHERE code_version_id = ? ORDER BY test_run_id ASC"
    rows = execute_query(db_file, query, (code_version_id,), fetch_all=True)
    results = []
    if rows:
        for row_val in rows:
            results.append({
                "test_case": {"description": row_val["test_case_description"]}, 
                "status": row_val["status"],
                "actual_output": json.loads(row_val["actual_output"]) if row_val["actual_output"] else None,
                "message": row_val["message"]
            })
    return results

# --- Validation & Feedback Logs ---
def log_validation_result(task_id: int, code_version_id: int, status: str, issues: Optional[List[str]], db_file: str = DB_FILE) -> Optional[int]:
    issues_json = json.dumps(issues) if issues else None
    query = "INSERT INTO validation_logs (task_id, code_version_id, status, issues_found) VALUES (?, ?, ?, ?)"
    return execute_query(db_file, query, (task_id, code_version_id, status, issues_json), last_row_id=True)

def log_feedback(task_id: int, code_version_id: Optional[int], feedback_type: str, feedback_text: str, db_file: str = DB_FILE) -> Optional[int]:
    query = "INSERT INTO feedback_logs (task_id, code_version_id, feedback_type, feedback_text) VALUES (?, ?, ?, ?)"
    return execute_query(db_file, query, (task_id, code_version_id, feedback_type, feedback_text), last_row_id=True)

def get_feedback_history_for_task(task_id: int, db_file: str = DB_FILE) -> List[Dict]:
    # Get all feedback for a task, ordered by time. Could also filter by code_version_id if needed.
    query = "SELECT feedback_type, feedback_text, created_at, code_version_id FROM feedback_logs WHERE task_id = ? ORDER BY created_at ASC"
    rows = execute_query(db_file, query, (task_id,), fetch_all=True)
    history = []
    if rows:
        for row in rows:
            history.append({"type": row["feedback_type"], "text": row["feedback_text"], 
                            "timestamp": row["created_at"], "code_version_id": row["code_version_id"]})
    return history

def get_feedback_history_for_version(code_version_id: int, db_file: str = DB_FILE) -> list:
    # Get all feedback for a specific code version, ordered by time.
    query = "SELECT feedback_type, feedback_text, created_at, code_version_id FROM feedback_logs WHERE code_version_id = ? ORDER BY created_at ASC"
    rows = execute_query(db_file, query, (code_version_id,), fetch_all=True)
    history = []
    if rows:
        for row in rows:
            history.append({
                "type": row["feedback_type"],
                "text": row["feedback_text"],
                "timestamp": row["created_at"],
                "code_version_id": row["code_version_id"]
            })
    return history
    
# --- Artifact Management ---
def add_packaged_artifact(task_id: int, info: Dict, handoff_summary: str, db_file: str = DB_FILE) -> Optional[int]:
    query = "INSERT INTO packaged_artifacts (task_id, info, handoff_summary) VALUES (?, ?, ?)"
    return execute_query(db_file, query, (task_id, json.dumps(info), handoff_summary), last_row_id=True)

def get_packaged_artifact(task_id: int, db_file: str = DB_FILE) -> Optional[Dict[str, Any]]:
    query = "SELECT info, handoff_summary, created_at FROM packaged_artifacts WHERE task_id = ?"
    row = execute_query(db_file, query, (task_id,), fetch_one=True)
    if row:
        artifact_data = dict(row)
        if artifact_data["info"]:
            try:
                artifact_data["info"] = json.loads(artifact_data["info"])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse JSON for artifact info for task {task_id}")
                artifact_data["info"] = None
        return artifact_data
    return None

if __name__ == "__main__":
    # Ensure the database directory exists before trying to init
    db_dir = os.path.dirname(DB_FILE)
    if db_dir and not os.path.exists(db_dir): # Check if db_dir is not empty (i.e. not just filename)
        os.makedirs(db_dir)
        print(f"Created database directory: {db_dir}")
    
    print(f"Initializing database at {DB_FILE}...")
    init_db()
    
    print("Creating a sample task...")
    sample_task_id = create_task("Create a Python function to add two numbers.")
    if sample_task_id:
        print(f"Sample task created with ID: {sample_task_id}")
        task = get_task_data(sample_task_id)
        print(f"Retrieved task data: {task}")

        update_success = update_task_field(sample_task_id, "status", "planning_done")
        print(f"Update task status success: {update_success}")
        updated_task = get_task_data(sample_task_id)
        print(f"Updated task data: {updated_task}")

        cv_id = add_code_version(sample_task_id, "def add(a, b):\n  return a + b", 0)
        if cv_id:
            print(f"Code version added with ID: {cv_id}")
            log_test_run_result(sample_task_id, cv_id, "Test with 2,3", "success", 5, "Passed.")
            tests = get_test_results_for_version(cv_id)
            print(f"Test results for version {cv_id}: {tests}")
            
            log_feedback(sample_task_id, cv_id, "user_rejection", "Needs to handle strings too.")
            feedback_hist = get_feedback_history_for_task(sample_task_id)
            print(f"Feedback history for task {sample_task_id}: {feedback_hist}")
    else:
        print("Failed to create sample task.")