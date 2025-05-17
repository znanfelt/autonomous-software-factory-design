# tests/utils/test_database.py
import unittest
import sqlite3
import os
import json
from pathlib import Path
import sys
from datetime import datetime

# Adjust path to import from parent directory (utils)
# Assuming 'tests' is a top-level directory, and 'utils' is parallel to 'pocketflow_sft_dev_app'
# If 'tests' is inside 'pocketflow_sft_dev_app', this needs adjustment.
# For the provided structure where 'tests' is at the root with 'autonomous-software-factory-design-main':
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "autonomous-software-factory-design-main"))

# Now import from the correct location
from utils import database # This should now work

# Use a dedicated test database file, ensure it's in a writable location
TEST_DB_DIR = Path(__file__).resolve().parent / "test_db_data"
TEST_DB_FILE = TEST_DB_DIR / "test_sdlc_tasks.db"
database.DB_FILE = str(TEST_DB_FILE) # Override the default DB_FILE for tests

class TestDatabaseFunctions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Ensure test database directory exists and db is initialized for all tests."""
        TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
        if TEST_DB_FILE.exists():
            TEST_DB_FILE.unlink() # Ensure a clean start for each test run session
        database.init_db(db_file_path=str(TEST_DB_FILE))
        print(f"Test database initialized at: {TEST_DB_FILE}")


    def setUp(self):
        """Clean tables before each test method."""
        conn = database.get_db_connection(db_file_path=str(TEST_DB_FILE))
        if conn:
            cursor = conn.cursor()
            # Order of deletion matters due to foreign key constraints if they were ON DELETE RESTRICT
            # For ON DELETE CASCADE (as implicitly in SQLite by default unless specified), order is less critical
            # but good practice to delete from child tables first.
            cursor.execute("DELETE FROM packaged_artifacts;")
            cursor.execute("DELETE FROM feedback_logs;")
            cursor.execute("DELETE FROM validation_logs;")
            cursor.execute("DELETE FROM test_run_results;")
            cursor.execute("DELETE FROM code_versions;")
            # cursor.execute("DELETE FROM test_cases_generated;") # This table was removed in latest DB schema
            cursor.execute("DELETE FROM tasks;")
            conn.commit()
            conn.close()
        else:
            self.fail("Test DB connection failed in setUp")

    def test_01_init_db_creates_tables(self):
        conn = database.get_db_connection(db_file_path=str(TEST_DB_FILE))
        self.assertIsNotNone(conn)
        cursor = conn.cursor()
        tables = ["tasks", "code_versions", "test_run_results", 
                  "validation_logs", "feedback_logs", "packaged_artifacts"]
        for table in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
            self.assertIsNotNone(cursor.fetchone(), f"Table {table} not created.")
        conn.close()

    def test_02_create_and_get_task(self):
        task_id = database.create_task("Test request 1", db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(task_id)
        task_data = database.get_task_data(task_id, db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(task_data)
        self.assertEqual(task_data["initial_request"], "Test request 1")
        self.assertEqual(task_data["status"], "created")
        self.assertIsNone(task_data["architectural_decision"]) # Should be None initially

    def test_03_update_task_field_with_json_and_plain_text(self):
        task_id = database.create_task("Test request for update", db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(task_id)
        
        # Test updating a plain text field
        update_success_status = database.update_task_field(task_id, "status", "planning", db_file=str(TEST_DB_FILE))
        self.assertTrue(update_success_status)
        task_data = database.get_task_data(task_id, db_file=str(TEST_DB_FILE))
        self.assertEqual(task_data["status"], "planning")

        # Test updating a JSON field (architectural_decision)
        arch_decision_dict = {"language": "python", "framework": "standard_library", "notes": "Keep it simple"}
        update_success_json = database.update_task_field(task_id, "architectural_decision", arch_decision_dict, db_file=str(TEST_DB_FILE))
        self.assertTrue(update_success_json)
        task_data_json = database.get_task_data(task_id, db_file=str(TEST_DB_FILE))
        self.assertEqual(task_data_json["architectural_decision"], arch_decision_dict) # get_task_data should deserialize

        # Test updating another JSON field (planned_task_description)
        plan_desc_dict = {"function_name": "add", "params": [{"name":"a", "type":"int"}]}
        update_success_plan = database.update_task_field(task_id, "planned_task_description", plan_desc_dict, db_file=str(TEST_DB_FILE))
        self.assertTrue(update_success_plan)
        task_data_plan = database.get_task_data(task_id, db_file=str(TEST_DB_FILE))
        self.assertEqual(task_data_plan["planned_task_description"], plan_desc_dict)

        # Test updating generated_test_cases_json
        test_cases_list = [{"input": [1,2], "output": 3}]
        update_success_tests = database.update_task_field(task_id, "generated_test_cases_json", test_cases_list, db_file=str(TEST_DB_FILE))
        self.assertTrue(update_success_tests)
        task_data_tests = database.get_task_data(task_id, db_file=str(TEST_DB_FILE))
        self.assertEqual(task_data_tests["generated_test_cases_json"], test_cases_list)


    def test_04_code_versions_with_project_structure(self):
        task_id = database.create_task("Code version with project structure", db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(task_id)
        
        project_v1 = {"files": [{"name": "main.py", "content": "print('v1')"}]}
        project_v2 = {"files": [{"name": "main.py", "content": "print('v2')"}, {"name": "utils.py", "content": "def helper(): pass"}]}
        
        cv_id1 = database.add_code_version(task_id, json.dumps(project_v1), 0, db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(cv_id1)
        cv_id2 = database.add_code_version(task_id, json.dumps(project_v2), 1, db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(cv_id2)
        
        latest_cv = database.get_latest_code_version(task_id, db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(latest_cv)
        self.assertEqual(latest_cv["code_version_id"], cv_id2)
        self.assertEqual(json.loads(latest_cv["generated_code"]), project_v2) # Compare deserialized dicts
        self.assertEqual(latest_cv["iteration_number"], 1)

    def test_05_test_run_results(self):
        task_id = database.create_task("Test run log test", db_file=str(TEST_DB_FILE))
        cv_id = database.add_code_version(task_id, json.dumps({"files": [{"name":"test.py", "content":"def func(): return 1"}]}), 0, db_file=str(TEST_DB_FILE))
        
        log_id = database.log_test_run_result(task_id, cv_id, "Test case 1 desc", "success", {"output": 5}, "Passed", db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(log_id)
        
        results = database.get_test_results_for_version(cv_id, db_file=str(TEST_DB_FILE))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
        self.assertEqual(results[0]["actual_output"], {"output": 5})
        self.assertIn("Test case 1 desc", results[0]["message"]) # Message now includes description

    def test_06_validation_logs(self):
        task_id = database.create_task("Validation log test", db_file=str(TEST_DB_FILE))
        cv_id = database.add_code_version(task_id, json.dumps({"files": [{"name":"test.py", "content":"valid code"}]}), 0, db_file=str(TEST_DB_FILE))

        log_id = database.log_validation_result(task_id, cv_id, "fail", ["Issue 1", "Issue 2"], db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(log_id)
        # To verify, you might add a get_validation_logs_for_version function or similar
        # For now, just ensuring it runs without error.

    def test_07_feedback_logs(self):
        task_id = database.create_task("Feedback log test", db_file=str(TEST_DB_FILE))
        cv_id = database.add_code_version(task_id, json.dumps({"files": [{"name":"test.py", "content":"code with issues"}]}), 0, db_file=str(TEST_DB_FILE))

        log_id = database.log_feedback(task_id, cv_id, "user_rejection", "Needs multi-file support.", db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(log_id)
        
        history = database.get_feedback_history_for_task(task_id, db_file=str(TEST_DB_FILE))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["type"], "user_rejection")
        self.assertEqual(history[0]["text"], "Needs multi-file support.")
        self.assertEqual(history[0]["code_version_id"], cv_id)

        history_for_version = database.get_feedback_history_for_version(cv_id, db_file=str(TEST_DB_FILE))
        self.assertEqual(len(history_for_version), 1)


    def test_08_packaged_artifacts_with_project_structure(self):
        task_id = database.create_task("Artifact with project structure", db_file=str(TEST_DB_FILE))
        
        project_info = {"files": [{"name":"final.py", "content":"final code"}], "entry_point":"final.py"}
        summary = "Task completed and packaged with multiple files."
        artifact_id = database.add_packaged_artifact(task_id, project_info, summary, db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(artifact_id)
        
        artifact_data = database.get_packaged_artifact(task_id, db_file=str(TEST_DB_FILE))
        self.assertIsNotNone(artifact_data)
        self.assertEqual(artifact_data["info"], project_info) # Compare deserialized dicts
        self.assertEqual(artifact_data["handoff_summary"], summary)

    @classmethod
    def tearDownClass(cls):
        """Clean up the test database file after all tests."""
        # if TEST_DB_FILE.exists():
        #     TEST_DB_FILE.unlink() # Keep for inspection if needed
        #     print(f"Removed test database: {TEST_DB_FILE}")
        pass

if __name__ == '__main__':
    db_dir_main = os.path.dirname(TEST_DB_FILE)
    if not os.path.exists(db_dir_main):
        os.makedirs(db_dir_main)
    database.DB_FILE = str(TEST_DB_FILE) # Ensure the global in database module is also set
    unittest.main()