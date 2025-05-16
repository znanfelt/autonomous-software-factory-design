# tests/test_database.py
import unittest
import sqlite3
import os
import json
from pathlib import Path
import sys
from datetime import datetime

# Adjust path to import from parent directory (utils)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import database # This should now work

# Use a dedicated test database file
TEST_DB_FILE = "database/test_sdlc_tasks.db"

class TestDatabaseFunctions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Ensure test database directory exists and db is initialized for all tests."""
        db_dir = os.path.dirname(TEST_DB_FILE)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        database.init_db(db_file_path=TEST_DB_FILE)

    def setUp(self):
        """Create a fresh connection and cursor for each test, or clean tables."""
        # For a truly isolated test, you might recreate tables or use an in-memory DB.
        # For simplicity here, we'll delete data from tables.
        conn = database.get_db_connection(db_file_path=TEST_DB_FILE)
        if conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM packaged_artifacts;")
            cursor.execute("DELETE FROM feedback_logs;")
            cursor.execute("DELETE FROM validation_logs;")
            cursor.execute("DELETE FROM test_run_results;")
            cursor.execute("DELETE FROM code_versions;")
            cursor.execute("DELETE FROM tasks;")
            conn.commit()
            conn.close()
        else:
            self.fail("Test DB connection failed in setUp")


    def test_01_init_db(self):
        """Test if init_db creates all tables."""
        # setUpClass already calls init_db. We check if tables exist.
        conn = database.get_db_connection(db_file_path=TEST_DB_FILE)
        self.assertIsNotNone(conn)
        cursor = conn.cursor()
        tables = ["tasks", "code_versions", "test_run_results", "validation_logs", "feedback_logs", "packaged_artifacts"]
        for table in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
            self.assertIsNotNone(cursor.fetchone(), f"Table {table} not created.")
        conn.close()

    def test_02_create_and_get_task(self):
        task_id = database.create_task("Test request 1", db_file=TEST_DB_FILE)
        self.assertIsNotNone(task_id)
        task_data = database.get_task_data(task_id, db_file=TEST_DB_FILE)
        self.assertIsNotNone(task_data)
        self.assertEqual(task_data["initial_request"], "Test request 1")
        self.assertEqual(task_data["status"], "created")

    def test_03_update_task_field(self):
        task_id = database.create_task("Test request 2", db_file=TEST_DB_FILE)
        self.assertIsNotNone(task_id)
        
        update_success = database.update_task_field(task_id, "status", "in_progress", db_file=TEST_DB_FILE)
        self.assertTrue(update_success)
        task_data = database.get_task_data(task_id, db_file=TEST_DB_FILE)
        self.assertEqual(task_data["status"], "in_progress")

        # Test updating a JSON field
        arch_decision = {"lang": "python", "notes": "simple"}
        update_success_json = database.update_task_field(task_id, "architectural_decision", arch_decision, db_file=TEST_DB_FILE)
        self.assertTrue(update_success_json)
        task_data_json = database.get_task_data(task_id, db_file=TEST_DB_FILE)
        self.assertEqual(task_data_json["architectural_decision"], arch_decision)

        # Test updating an invalid field
        update_fail = database.update_task_field(task_id, "non_existent_field", "value", db_file=TEST_DB_FILE)
        self.assertFalse(update_fail)


    def test_04_code_versions(self):
        task_id = database.create_task("Code version test", db_file=TEST_DB_FILE)
        self.assertIsNotNone(task_id)
        cv_id1 = database.add_code_version(task_id, "print('v1')", 0, db_file=TEST_DB_FILE)
        self.assertIsNotNone(cv_id1)
        cv_id2 = database.add_code_version(task_id, "print('v2')", 1, db_file=TEST_DB_FILE)
        self.assertIsNotNone(cv_id2)
        
        latest_cv = database.get_latest_code_version(task_id, db_file=TEST_DB_FILE)
        self.assertIsNotNone(latest_cv)
        self.assertEqual(latest_cv["code_version_id"], cv_id2)
        self.assertEqual(latest_cv["generated_code"], "print('v2')")
        self.assertEqual(latest_cv["iteration_number"], 1)

    def test_05_test_run_results(self):
        task_id = database.create_task("Test run log test", db_file=TEST_DB_FILE)
        self.assertIsNotNone(task_id)
        cv_id = database.add_code_version(task_id, "code", 0, db_file=TEST_DB_FILE)
        self.assertIsNotNone(cv_id)

        log_id = database.log_test_run_result(task_id, cv_id, "Test case 1 desc", "success", {"output": 5}, "Passed", db_file=TEST_DB_FILE)
        self.assertIsNotNone(log_id)
        
        results = database.get_test_results_for_version(cv_id, db_file=TEST_DB_FILE)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
        self.assertEqual(results[0]["actual_output"], {"output": 5})
        self.assertIn("Test case 1 desc", results[0]["message"])

    def test_06_validation_logs(self):
        task_id = database.create_task("Validation log test", db_file=TEST_DB_FILE)
        self.assertIsNotNone(task_id)
        cv_id = database.add_code_version(task_id, "code", 0, db_file=TEST_DB_FILE)
        self.assertIsNotNone(cv_id)

        log_id = database.log_validation_result(task_id, cv_id, "fail", ["Issue 1", "Issue 2"], db_file=TEST_DB_FILE)
        self.assertIsNotNone(log_id)
        
        # Add a get_validation_logs_for_version function if needed for direct verification,
        # or verify through get_task_data if validation info is aggregated there.
        # For now, just ensures no error.

    def test_07_feedback_logs(self):
        task_id = database.create_task("Feedback log test", db_file=TEST_DB_FILE)
        self.assertIsNotNone(task_id)
        cv_id = database.add_code_version(task_id, "code", 0, db_file=TEST_DB_FILE)
        self.assertIsNotNone(cv_id)

        log_id = database.log_feedback(task_id, cv_id, "user_rejection", "Does not work for edge cases.", db_file=TEST_DB_FILE)
        self.assertIsNotNone(log_id)
        
        history = database.get_feedback_history_for_task(task_id, db_file=TEST_DB_FILE) # Changed to get_feedback_history_for_task
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["type"], "user_rejection")
        self.assertEqual(history[0]["text"], "Does not work for edge cases.")

    def test_08_packaged_artifacts(self):
        task_id = database.create_task("Artifact test", db_file=TEST_DB_FILE)
        self.assertIsNotNone(task_id)
        
        info = {"code_file": "final.py", "readme": "README content"}
        summary = "Task completed and packaged."
        artifact_id = database.add_packaged_artifact(task_id, info, summary, db_file=TEST_DB_FILE)
        self.assertIsNotNone(artifact_id)
        
        artifact_data = database.get_packaged_artifact(task_id, db_file=TEST_DB_FILE)
        self.assertIsNotNone(artifact_data)
        self.assertEqual(artifact_data["info"], info)
        self.assertEqual(artifact_data["handoff_summary"], summary)

    @classmethod
    def tearDownClass(cls):
        """Clean up the test database file after all tests."""
        if os.path.exists(TEST_DB_FILE):
            # os.remove(TEST_DB_FILE) # Comment out to inspect DB after tests
            # print(f"Removed test database: {TEST_DB_FILE}")
            pass


if __name__ == '__main__':
    # Ensure the test database directory exists before running tests
    db_dir_main = os.path.dirname(TEST_DB_FILE)
    if not os.path.exists(db_dir_main):
        os.makedirs(db_dir_main)
    unittest.main()