# utils/database.py
import sqlite3
import json
import os
from typing import Any, List, Tuple, Dict, Optional
from datetime import datetime, timedelta  # Added timedelta for tests
import logging

logger = logging.getLogger(__name__)

DB_FILE = "database/sdlc_tasks.db"


def get_db_connection(db_file_path: str = DB_FILE) -> Optional[sqlite3.Connection]:
    # ... (same as before)
    try:
        db_dir = os.path.dirname(db_file_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
        conn = sqlite3.connect(db_file_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(
            f"Error connecting to database at {db_file_path}: {e}", exc_info=True
        )
        return None


def init_db(db_file_path: str = DB_FILE):
    # ... (same as before)
    conn = get_db_connection(db_file_path)
    if conn is None:
        logger.error(
            f"Cannot initialize database, connection failed for {db_file_path}."
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                initial_request TEXT NOT NULL,
                architectural_decision TEXT,        
                planned_task_description TEXT,      
                planner_notes TEXT,
                status TEXT DEFAULT 'created',      
                refinement_count INTEGER DEFAULT 0,
                current_error_message TEXT,
                planner_iteration_count INTEGER DEFAULT 0,
                generated_test_cases_json TEXT,    
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        )
        logger.info("Checked/Created 'tasks' table.")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS code_versions (
                code_version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                iteration_number INTEGER NOT NULL, 
                generated_code TEXT, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
            );
        """
        )
        logger.info("Checked/Created 'code_versions' table.")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS test_run_results (
                test_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER NOT NULL,
                test_case_description TEXT, 
                status TEXT NOT NULL,       
                actual_output TEXT,         
                message TEXT,               
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id) ON DELETE CASCADE
            );
        """
        )
        logger.info("Checked/Created 'test_run_results' table.")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_logs (
                validation_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER NOT NULL,
                status TEXT NOT NULL,       
                issues_found TEXT,          
                validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id) ON DELETE CASCADE
            );
        """
        )
        logger.info("Checked/Created 'validation_logs' table.")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_logs (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                code_version_id INTEGER,    
                feedback_type TEXT NOT NULL, 
                feedback_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
                FOREIGN KEY (code_version_id) REFERENCES code_versions (code_version_id) ON DELETE CASCADE
            );
        """
        )
        logger.info("Checked/Created 'feedback_logs' table.")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS packaged_artifacts (
                artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL UNIQUE, 
                info TEXT,                   
                handoff_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
            );
        """
        )
        logger.info("Checked/Created 'packaged_artifacts' table.")
        conn.commit()
        logger.info(f"Database initialized successfully at {db_file_path}.")
    except sqlite3.Error as e:
        logger.error(
            f"Error initializing database at {db_file_path}: {e}", exc_info=True
        )
    finally:
        if conn:
            conn.close()


def execute_query(
    db_file_path: str,
    query: str,
    params: Tuple = (),
    fetch_one=False,
    fetch_all=False,
    last_row_id=False,
):
    # ... (same as before)
    conn = get_db_connection(db_file_path)
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
        return True
    except sqlite3.Error as e:
        logger.error(f"Error executing query '{query[:50]}...': {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


ALLOWED_TASK_FIELDS = [
    "initial_request",
    "architectural_decision",
    "planned_task_description",
    "planner_notes",
    "status",
    "refinement_count",
    "current_error_message",
    "planner_iteration_count",
    "generated_test_cases_json",
    "updated_at",
]


def create_task(initial_request: str, db_file: str = DB_FILE) -> Optional[int]:
    # ... (same as before)
    query = "INSERT INTO tasks (initial_request, status, created_at, updated_at) VALUES (?, ?, ?, ?)"
    now = datetime.now().isoformat()
    return execute_query(
        db_file, query, (initial_request, "created", now, now), last_row_id=True
    )


def get_task_data(task_id: int, db_file: str = DB_FILE) -> Optional[Dict[str, Any]]:
    # ... (same as before)
    query = "SELECT * FROM tasks WHERE task_id = ?"
    row = execute_query(db_file, query, (task_id,), fetch_one=True)
    if row:
        task_data = dict(row)
        for field in [
            "architectural_decision",
            "planned_task_description",
            "generated_test_cases_json",
        ]:
            if field in task_data and task_data[field]:
                try:
                    task_data[field] = json.loads(task_data[field])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(
                        f"Could not parse JSON for field {field} in task {task_id}. Value: {task_data[field]}. Error: {e}"
                    )
                    task_data[field] = None
        return task_data
    return None


def update_task_field(
    task_id: int, field_name: str, field_value: Any, db_file: str = DB_FILE
) -> bool:
    # ... (same as before)
    if field_name not in ALLOWED_TASK_FIELDS:
        logger.error(
            f"Error: Invalid field name '{field_name}' for task update. Allowed: {ALLOWED_TASK_FIELDS}"
        )
        return False
    value_to_store = (
        json.dumps(field_value)
        if isinstance(field_value, (dict, list))
        else field_value
    )
    query = f"UPDATE tasks SET {field_name} = ?, updated_at = ? WHERE task_id = ?"
    return (
        execute_query(
            db_file, query, (value_to_store, datetime.now().isoformat(), task_id)
        )
        is True
    )


def add_code_version(
    task_id: int,
    code_project_structure_json: str,
    iteration: int,
    db_file: str = DB_FILE,
) -> Optional[int]:
    # ... (same as before)
    query = "INSERT INTO code_versions (task_id, generated_code, iteration_number) VALUES (?, ?, ?)"
    return execute_query(
        db_file,
        query,
        (task_id, code_project_structure_json, iteration),
        last_row_id=True,
    )


def get_latest_code_version(
    task_id: int, db_file: str = DB_FILE
) -> Optional[Dict[str, Any]]:
    # ... (same as before)
    query = "SELECT code_version_id, generated_code, iteration_number FROM code_versions WHERE task_id = ? ORDER BY code_version_id DESC LIMIT 1"
    row = execute_query(db_file, query, (task_id,), fetch_one=True)
    if row:
        data = dict(row)
        if data.get("generated_code"):
            try:
                data["generated_code"] = json.loads(data["generated_code"])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    f"Could not parse JSON for generated_code in version {data['code_version_id']}. Error: {e}"
                )
                data["generated_code"] = {
                    "error": "Failed to parse code structure",
                    "raw": data["generated_code"],
                }
        return data
    return None


def log_test_run_result(
    task_id: int,
    code_version_id: int,
    test_case_desc: str,
    status: str,
    actual_output: Any,
    message: str,
    db_file: str = DB_FILE,
) -> Optional[int]:
    # ... (same as before)
    query = """
        INSERT INTO test_run_results 
        (task_id, code_version_id, test_case_description, status, actual_output, message) 
        VALUES (?, ?, ?, ?, ?, ?)
    """
    return execute_query(
        db_file,
        query,
        (
            task_id,
            code_version_id,
            test_case_desc,
            status,
            json.dumps(actual_output),
            message,
        ),
        last_row_id=True,
    )


def get_test_results_for_version(
    code_version_id: int, db_file: str = DB_FILE
) -> List[Dict]:
    # ... (same as before)
    query = "SELECT test_case_description, status, actual_output, message FROM test_run_results WHERE code_version_id = ? ORDER BY test_run_id ASC"
    rows = execute_query(db_file, query, (code_version_id,), fetch_all=True)
    results = []
    if rows:
        for row_val in rows:
            results.append(
                {
                    "test_case": {"description": row_val["test_case_description"]},
                    "status": row_val["status"],
                    "actual_output": (
                        json.loads(row_val["actual_output"])
                        if row_val["actual_output"]
                        else None
                    ),
                    "message": row_val["message"],
                }
            )
    return results


def log_validation_result(
    task_id: int,
    code_version_id: int,
    status: str,
    issues: Optional[List[str]],
    db_file: str = DB_FILE,
) -> Optional[int]:
    # ... (same as before)
    issues_json = json.dumps(issues) if issues else None
    query = "INSERT INTO validation_logs (task_id, code_version_id, status, issues_found) VALUES (?, ?, ?, ?)"
    return execute_query(
        db_file,
        query,
        (task_id, code_version_id, status, issues_json),
        last_row_id=True,
    )


def get_validation_log_for_version(
    code_version_id: int, db_file: str = DB_FILE
) -> Optional[Dict[str, Any]]:
    # Updated to ensure issues_found is always a list if present, or empty list if NULL/empty
    query = "SELECT status, issues_found, validated_at FROM validation_logs WHERE code_version_id = ? ORDER BY validation_log_id DESC LIMIT 1"
    row = execute_query(db_file, query, (code_version_id,), fetch_one=True)
    if row:
        data = dict(row)
        if data.get("issues_found"):
            try:
                parsed_issues = json.loads(data["issues_found"])
                data["issues_found"] = (
                    parsed_issues
                    if isinstance(parsed_issues, list)
                    else [str(parsed_issues)]
                )
            except (json.JSONDecodeError, TypeError):
                data["issues_found"] = [f"Error parsing issues: {data['issues_found']}"]
        else:
            data["issues_found"] = []  # Default to empty list if NULL or empty string
        return data
    return None


def log_feedback(
    task_id: int,
    code_version_id: Optional[int],
    feedback_type: str,
    feedback_text: str,
    db_file: str = DB_FILE,
) -> Optional[int]:
    # ... (same as before)
    query = "INSERT INTO feedback_logs (task_id, code_version_id, feedback_type, feedback_text) VALUES (?, ?, ?, ?)"
    return execute_query(
        db_file,
        query,
        (task_id, code_version_id, feedback_type, feedback_text),
        last_row_id=True,
    )


def get_feedback_history_for_task(task_id: int, db_file: str = DB_FILE) -> List[Dict]:
    # ... (same as before)
    query = "SELECT feedback_id, code_version_id, feedback_type, feedback_text, created_at FROM feedback_logs WHERE task_id = ? ORDER BY created_at ASC"
    rows = execute_query(db_file, query, (task_id,), fetch_all=True)
    return [dict(row) for row in rows] if rows else []


def get_feedback_history_for_version(
    code_version_id: int, db_file: str = DB_FILE
) -> list:
    # ... (same as before)
    query = "SELECT feedback_type, feedback_text, created_at, code_version_id FROM feedback_logs WHERE code_version_id = ? ORDER BY created_at ASC"
    rows = execute_query(db_file, query, (code_version_id,), fetch_all=True)
    history = []
    if rows:
        for row in rows:
            history.append(dict(row))
    return history


def add_packaged_artifact(
    task_id: int, info: Dict, handoff_summary: str, db_file: str = DB_FILE
) -> Optional[int]:
    # ... (same as before)
    query = "INSERT INTO packaged_artifacts (task_id, info, handoff_summary) VALUES (?, ?, ?)"
    return execute_query(
        db_file, query, (task_id, json.dumps(info), handoff_summary), last_row_id=True
    )


def get_packaged_artifact(
    task_id: int, db_file: str = DB_FILE
) -> Optional[Dict[str, Any]]:
    # ... (same as before)
    query = "SELECT artifact_id, info, handoff_summary, created_at FROM packaged_artifacts WHERE task_id = ?"
    row = execute_query(db_file, query, (task_id,), fetch_one=True)
    if row:
        artifact_data = dict(row)
        if artifact_data["info"]:
            try:
                artifact_data["info"] = json.loads(artifact_data["info"])
            except (json.JSONDecodeError, TypeError):
                artifact_data["info"] = {
                    "error": "parsing failed",
                    "raw": artifact_data["info"],
                }
        return artifact_data
    return None


def get_all_tasks_summary(db_file: str = DB_FILE) -> List[Dict]:
    # ... (same as before)
    query = "SELECT task_id, initial_request, status, updated_at FROM tasks ORDER BY updated_at DESC"
    rows = execute_query(db_file, query, fetch_all=True)
    summaries = []
    if rows:
        for row in rows:
            summary = dict(row)
            if summary["initial_request"] and len(summary["initial_request"]) > 70:
                summary["initial_request"] = summary["initial_request"][:67] + "..."
            summaries.append(summary)
    return summaries


def load_task_state_from_db(
    task_id: int, db_file: str = DB_FILE
) -> Optional[Dict[str, Any]]:
    logger.info(f"Loading state for task_id: {task_id}")
    task_data = get_task_data(task_id, db_file)
    if not task_data:
        logger.error(f"No task data found for task_id: {task_id}")
        return None

    loaded_state = {
        "active_task_id": task_id,
        "user_raw_request": task_data.get("initial_request"),
        "current_request_for_planner": task_data.get("initial_request"),
        "architectural_decision": task_data.get("architectural_decision"),
        "planner_iteration_count": task_data.get("planner_iteration_count", 0),
        "clarification_questions_for_user": None,
        "planned_task_description": task_data.get("planned_task_description"),
        "suggested_project_outline": (
            task_data.get("planned_task_description", {}).get(
                "suggested_project_structure"
            )
            if isinstance(task_data.get("planned_task_description"), dict)
            else None
        ),
        "planner_notes": task_data.get("planner_notes"),
        "generated_project_structure": None,
        "active_code_version_id": None,
        "generated_test_cases": task_data.get("generated_test_cases_json"),
        "current_test_case_index": 0,
        "test_results_summary": [],
        "all_tests_passed": False,
        "validation_status": None,
        "validation_issues": [],
        "user_rejection_reason": "",
        "critique_feedback": None,
        "feedback_history": get_feedback_history_for_task(task_id, db_file),
        "refinement_count": task_data.get("refinement_count", 0),
        "packaged_artifacts_info": None,
        "handoff_summary": None,
        "current_error_message": task_data.get("current_error_message"),
        "ui_stage": task_data.get("status", "INPUT_REQUIREMENTS"),
    }

    # Ensure 'inputs' in loaded test cases are tuples
    if loaded_state["generated_test_cases"] and isinstance(
        loaded_state["generated_test_cases"], list
    ):
        for tc in loaded_state["generated_test_cases"]:
            if (
                isinstance(tc, dict)
                and "inputs" in tc
                and isinstance(tc["inputs"], list)
            ):
                tc["inputs"] = tuple(tc["inputs"])
            elif (
                isinstance(tc, dict)
                and "inputs" in tc
                and not isinstance(tc["inputs"], tuple)
            ):  # Handle single non-list item
                tc["inputs"] = (tc["inputs"],)

    latest_code_version = get_latest_code_version(task_id, db_file)
    if latest_code_version:
        loaded_state["generated_project_structure"] = latest_code_version.get(
            "generated_code"
        )
        loaded_state["active_code_version_id"] = latest_code_version.get(
            "code_version_id"
        )
        if loaded_state["active_code_version_id"]:
            loaded_state["test_results_summary"] = get_test_results_for_version(
                loaded_state["active_code_version_id"], db_file
            )
            val_log = get_validation_log_for_version(
                loaded_state["active_code_version_id"], db_file
            )
            if val_log:
                loaded_state["validation_status"] = val_log.get("status")
                loaded_state["validation_issues"] = val_log.get("issues_found", [])
            else:
                loaded_state["validation_status"] = None
                loaded_state["validation_issues"] = []
            if loaded_state["test_results_summary"]:
                loaded_state["all_tests_passed"] = all(
                    tr.get("status") == "success"
                    for tr in loaded_state["test_results_summary"]
                )

    if loaded_state["ui_stage"] == "completed":
        packaged_artifact = get_packaged_artifact(task_id, db_file)
        if packaged_artifact:
            loaded_state["packaged_artifacts_info"] = packaged_artifact.get("info")
            loaded_state["handoff_summary"] = packaged_artifact.get("handoff_summary")

    logger.info(
        f"Successfully loaded state for task {task_id}. Resuming at stage: {loaded_state['ui_stage']}"
    )
    return loaded_state


if __name__ == "__main__":
    db_dir_main = os.path.dirname(TEST_DB_FILE)
    if db_dir_main and not os.path.exists(db_dir_main):
        os.makedirs(db_dir_main)

    current_db_to_use = str(TEST_DB_FILE)  # Use the test DB for this main block too
    if os.path.exists(current_db_to_use):
        os.remove(current_db_to_use)

    print(f"Initializing database at {current_db_to_use}...")
    init_db(db_file_path=current_db_to_use)

    print("\n--- Testing Task Creation & Retrieval ---")
    task_id1 = create_task("Create a hello world function.", db_file=current_db_to_use)
    if task_id1:
        print(f"Created task 1 with ID: {task_id1}")
        data1 = get_task_data(task_id1, db_file=current_db_to_use)
        print(f"Retrieved task 1: {data1}")
        update_task_field(
            task_id1, "status", "planning_done", db_file=current_db_to_use
        )
        data1_updated = get_task_data(task_id1, db_file=current_db_to_use)
        print(
            f"Updated task 1 status: {data1_updated['status']}, updated_at: {data1_updated['updated_at']}"
        )

    print("\n--- Testing Code Versioning ---")
    if task_id1:
        code_v1 = {
            "files": [{"name": "hello.py", "content": "def hello(): print('world')"}]
        }
        cv1_id = add_code_version(
            task_id1, json.dumps(code_v1), 0, db_file=current_db_to_use
        )
        print(f"Added code version {cv1_id} for task {task_id1}")
        latest_cv = get_latest_code_version(task_id1, db_file=current_db_to_use)
        print(f"Latest code version for task {task_id1}: {latest_cv}")
        # self.assertEqual(latest_cv["generated_code"], code_v1) # Cannot use self in if __name__

    print("\n--- Testing Task Summary & Loading ---")
    task_id2 = create_task(
        "Create a complex calculation utility.", db_file=current_db_to_use
    )
    if task_id1 and task_id2:
        summaries = get_all_tasks_summary(db_file=current_db_to_use)
        print(f"\nAll Task Summaries ({len(summaries)} total):")
        for s in summaries:
            print(s)

        print(f"\nLoading state for task ID: {task_id1}...")
        loaded_state1 = load_task_state_from_db(task_id1, db_file=current_db_to_use)
        if loaded_state1:
            print(
                f"Loaded state for task {task_id1} (status: {loaded_state1['status']}):"
            )
        else:
            print(f"Could not load state for task {task_id1}")

    print("\nDatabase direct run tests finished.")
