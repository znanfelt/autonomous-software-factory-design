# tests/utils/test_database.py
import unittest
import sqlite3
import os
import json
from pathlib import Path
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock # Ensure MagicMock is imported

# Adjust path to import from parent directory (utils)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "autonomous-software-factory-design-main"))

from utils import database 

# Use a dedicated test database file
TEST_DB_DIR = Path(__file__).resolve().parent / "test_db_data_for_tests" 
TEST_DB_FILE = TEST_DB_DIR / "test_sdlc_tasks_suite.db"

class TestDatabaseFunctions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
        cls.original_db_file = database.DB_FILE
        database.DB_FILE = str(TEST_DB_FILE)
        if TEST_DB_FILE.exists():
            TEST_DB_FILE.unlink() 
        database.init_db()
        print(f"Test database initialized at: {TEST_DB_FILE}")

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = cls.original_db_file
        # if TEST_DB_FILE.exists():
            # TEST_DB_FILE.unlink() # Keep for inspection
            # print(f"Test database remains at: {TEST_DB_FILE} for inspection.")

    def setUp(self):
        conn = database.get_db_connection() 
        if conn:
            cursor = conn.cursor()
            tables = ["packaged_artifacts", "feedback_logs", "validation_logs", "test_run_results", "code_versions", "tasks"]
            for table in tables: cursor.execute(f"DELETE FROM {table};")
            conn.commit()
            conn.close()
        else: self.fail("Test DB connection failed in setUp")

    def test_01_init_db_creates_tables(self):
        conn = database.get_db_connection()
        self.assertIsNotNone(conn)
        cursor = conn.cursor()
        tables = ["tasks", "code_versions", "test_run_results", 
                  "validation_logs", "feedback_logs", "packaged_artifacts"]
        for table in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
            self.assertIsNotNone(cursor.fetchone(), f"Table {table} not created.")
        conn.close()

    def test_02_create_and_get_task(self):
        task_id = database.create_task("Test request 1")
        self.assertIsNotNone(task_id)
        task_data = database.get_task_data(task_id)
        self.assertIsNotNone(task_data)
        self.assertEqual(task_data["initial_request"], "Test request 1")
        self.assertEqual(task_data["status"], "created")
        self.assertIsNone(task_data["generated_test_cases_json"])

    def test_03_update_task_field_with_json_and_plain_text(self):
        task_id = database.create_task("Test request for update")
        self.assertIsNotNone(task_id)
        update_success_status = database.update_task_field(task_id, "status", "planning")
        self.assertTrue(update_success_status)
        task_data = database.get_task_data(task_id)
        self.assertEqual(task_data["status"], "planning")
        original_updated_at = task_data["updated_at"]

        arch_decision_dict = {"language": "python", "notes": "simple"}
        current_dt = datetime.fromisoformat(original_updated_at) # Make sure original_updated_at is valid ISO
        future_dt_iso = (current_dt + timedelta(seconds=1)).isoformat()
        
        with patch('utils.database.datetime') as mock_datetime_module:
            mock_now_instance = MagicMock()
            mock_now_instance.isoformat.return_value = future_dt_iso
            mock_datetime_module.now.return_value = mock_now_instance
            
            update_success_json = database.update_task_field(task_id, "architectural_decision", arch_decision_dict)
        
        self.assertTrue(update_success_json)
        task_data_json = database.get_task_data(task_id)
        self.assertEqual(task_data_json["architectural_decision"], arch_decision_dict)
        self.assertEqual(task_data_json["updated_at"], future_dt_iso)

        test_cases_list = [{"inputs": [1,2], "expected_output": 3, "description": "add test"}]
        update_success_tests = database.update_task_field(task_id, "generated_test_cases_json", test_cases_list)
        self.assertTrue(update_success_tests)
        task_data_tests = database.get_task_data(task_id)
        self.assertEqual(task_data_tests["generated_test_cases_json"], test_cases_list)

    def test_04_code_versions_with_project_structure(self):
        task_id = database.create_task("Code version with project structure")
        project_v1_dict = {"files": [{"name": "main.py", "content": "print('v1')"}]}
        cv_id1 = database.add_code_version(task_id, json.dumps(project_v1_dict), 0)
        latest_cv = database.get_latest_code_version(task_id)
        self.assertEqual(latest_cv["generated_code"], project_v1_dict)

    def test_05_test_run_results(self):
        task_id = database.create_task("Test run log test")
        cv_id = database.add_code_version(task_id, json.dumps({"files":[]}), 0)
        log_id = database.log_test_run_result(task_id, cv_id, "Test case 1 desc", "success", {"output": 5}, "Passed: Test case 1 desc")
        self.assertIsNotNone(log_id)
        results = database.get_test_results_for_version(cv_id)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
        self.assertEqual(results[0]["actual_output"], {"output": 5})
        self.assertEqual(results[0]["test_case"]["description"], "Test case 1 desc") # Access description from nested test_case
        self.assertEqual(results[0]["message"], "Passed: Test case 1 desc")


    def test_06_validation_logs(self):
        task_id = database.create_task("Validation log test")
        cv_id = database.add_code_version(task_id, json.dumps({"files":[]}), 0)
        log_id = database.log_validation_result(task_id, cv_id, "fail", ["Issue 1", "Issue 2"])
        self.assertIsNotNone(log_id)
        val_log = database.get_validation_log_for_version(cv_id)
        self.assertIsNotNone(val_log)
        self.assertEqual(val_log["status"], "fail")
        self.assertEqual(val_log["issues_found"], ["Issue 1", "Issue 2"])

    def test_07_feedback_logs(self):
        task_id = database.create_task("Feedback log test")
        cv_id = database.add_code_version(task_id, json.dumps({"files":[]}), 0)
        log_id = database.log_feedback(task_id, cv_id, "user_rejection", "Needs multi-file support.")
        self.assertIsNotNone(log_id)
        history = database.get_feedback_history_for_task(task_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["feedback_type"], "user_rejection") # Corrected key
        self.assertEqual(history[0]["feedback_text"], "Needs multi-file support.")

    def test_08_packaged_artifacts(self):
        task_id = database.create_task("Artifact test")
        info = {"project_files": [{"name":"final.py", "content":"final code"}], "entry_point":"final.py"}
        summary = "Task completed."
        artifact_id = database.add_packaged_artifact(task_id, info, summary)
        artifact_data = database.get_packaged_artifact(task_id)
        self.assertEqual(artifact_data["info"], info)

    def test_09_get_all_tasks_summary(self):
        long_request = "This is the first task, and it has a very very very long description designed specifically to test the truncation logic which should append ellipses if it exceeds seventy characters for display."
        self.assertTrue(len(long_request) > 70) 

        task_id1 = database.create_task(long_request)
        task_id2 = database.create_task("Second task")
        database.update_task_field(task_id1, "status", "completed")
        
        task2_data_before_update = database.get_task_data(task_id2)
        current_dt_iso = task2_data_before_update["updated_at"]
        current_dt = datetime.fromisoformat(current_dt_iso)
        future_dt_iso = (current_dt + timedelta(minutes=1)).isoformat()
        
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET updated_at = ? WHERE task_id = ?", (future_dt_iso, task_id2))
        conn.commit()
        conn.close()

        summaries = database.get_all_tasks_summary()
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0]["task_id"], task_id2) 
        self.assertEqual(summaries[0]["status"], "created") # Task2 status not changed
        
        summary_for_task1 = next((s for s in summaries if s["task_id"] == task_id1), None)
        self.assertIsNotNone(summary_for_task1)
        self.assertTrue(summary_for_task1["initial_request"].endswith("..."))
        self.assertEqual(len(summary_for_task1["initial_request"]), 70)
        self.assertEqual(summary_for_task1["status"], "completed")


    def test_10_load_task_state_from_db(self):
        task_id = database.create_task("Task to load")
        self.assertIsNotNone(task_id)
        arch_dec = {"lang": "python"}; plan_desc = {"name": "func_a", "target_file": "main.py", "component_name": "func_a"} # ensure component_name
        test_cases_json_list = [{"inputs": (1,), "expected_output": 2, "description": "test1", "target_file": "main.py", "target_function": "func_a"}] # inputs as tuple
        database.update_task_field(task_id, "architectural_decision", arch_dec)
        database.update_task_field(task_id, "planned_task_description", plan_desc)
        database.update_task_field(task_id, "generated_test_cases_json", test_cases_json_list) 
        database.update_task_field(task_id, "status", "human_review")
        database.update_task_field(task_id, "refinement_count", 1)

        cv1_code = {"files": [{"name": "main.py", "content": "def func_a(x): return x"}]}
        cv1_id = database.add_code_version(task_id, json.dumps(cv1_code), 0)
        cv2_code = {"files": [{"name": "main.py", "content": "def func_a(x): return x + 1"}]}
        cv2_id = database.add_code_version(task_id, json.dumps(cv2_code), 1)
        database.log_test_run_result(task_id, cv2_id, "test1 desc", "success", 2, "Passed for input (1)")
        database.log_validation_result(task_id, cv2_id, "pass", []) 
        database.log_feedback(task_id, cv1_id, "user_rejection", "Initial code was wrong.")
        database.log_feedback(task_id, cv2_id, "ai_critique", "Looks better now.")

        loaded_state = database.load_task_state_from_db(task_id)
        self.assertIsNotNone(loaded_state)
        self.assertEqual(loaded_state["active_task_id"], task_id)
        self.assertEqual(loaded_state["generated_test_cases"], test_cases_json_list)
        self.assertEqual(loaded_state["validation_status"], "pass")
        self.assertIsInstance(loaded_state["validation_issues"], list) 
        self.assertEqual(len(loaded_state["validation_issues"]), 0)


if __name__ == '__main__':
    db_dir_main = os.path.dirname(TEST_DB_FILE)
    if not os.path.exists(db_dir_main): os.makedirs(db_dir_main)
    database.DB_FILE = str(TEST_DB_FILE) 
    unittest.main()