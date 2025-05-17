# Example Multi-file Prompts
Here are three prompts designed to encourage the AI Planner/Developer to create a multi-file Python application, keeping in mind the MVP's focus on standard libraries. These prompts are for the *user* to input into the Streamlit app at the "INPUT_REQUIREMENTS" stage.

## Prompt 1: Simple Web Scraper and Data Saver**

```text
"


Create a Python application that consists of two main parts. 
First, a web scraper utility that can fetch the main text content from a given URL. This utility should be in its own file, say 'scraper_utils.py', and have a function like 'fetch_text(url)'.
Second, a main script, 'app.py', that takes a URL as input (e.g., from a hardcoded list for now), uses the scraper utility to get the text, and then saves this text to a file named after the URL's domain (e.g., 'example_com_content.txt').
The scraper should handle basic requests errors gracefully.

"
```
update test case 1 to actual. find another url for 3, the connection error isn't happening
**Why this should lead to multi-file:**

* Explicitly mentions two files: `scraper_utils.py` and `app.py`.
* Describes distinct functionalities for each, implying separation.
* Mentions one module importing another (`app.py` uses `scraper_utils.py`).

## Prompt 2: Basic Task Manager with CLI**

```text
"I need a simple command-line task manager in Python. 
It should have a module for task operations, let's call it 'task_logic.py'. This module should have functions to:
1. 'add_task(tasks_list, description)' - adds a new task (just a string) to a list.
2. 'view_tasks(tasks_list)' - prints all tasks with their index.
3. 'remove_task(tasks_list, task_index)' - removes a task by its index.
The main application, in 'main_cli.py', should provide a simple loop that asks the user to 'add', 'view', 'remove', or 'exit'. It will use the functions from 'task_logic.py' to manage an in-memory list of tasks."
```

**Why this should lead to multi-file:**

* Clearly defines two modules/files: `task_logic.py` and `main_cli.py`.
* Separates data manipulation logic (`task_logic.py`) from the user interface/control flow (`main_cli.py`).
* Implies `main_cli.py` will import and use functions from `task_logic.py`.

## Prompt 3: Simple Text File Analyzer**

```text
"Develop a Python tool that analyzes text files. 
I need a 'file_parser.py' that contains a function 'parse_file(filepath)' which reads a text file and returns its content as a string. 
Then, in 'analyzer.py', create a function 'analyze_text(text_content)' that calculates:
1. Word count.
2. Character count (including spaces).
3. Number of lines.
It should return these as a dictionary.
Finally, create a 'report_generator.py' with a function 'generate_report(analysis_dict, original_filepath)' that takes the analysis dictionary and the original file path, and prints a formatted report to the console.
For the MVP, the main execution script, say 'run_analysis.py', can hardcode a path to a sample text file, then call these functions in sequence: parse, then analyze, then generate report."
```

**Why this should lead to multi-file:**

* Explicitly names four distinct Python files: `file_parser.py`, `analyzer.py`, `report_generator.py`, and `run_analysis.py`.
* Assigns specific, modular responsibilities to each file, indicating a clear separation of concerns.
* The description of `run_analysis.py` calling functions "in sequence" implies imports and interactions between these modules.

These prompts try to be specific about the file structure and the distinct roles of different components, which should guide the `ArchitectPlannerNode` and subsequently the `DeveloperNode` towards generating a multi-file project structure. The key is to describe not just *what* the software should do, but also hint at *how* it might be organized if a multi-file structure is desired.
