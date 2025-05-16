import os

# Define the directory structure
structure = [
    {
        "pocketflow_sft_dev_app": [
            "app.py",
            "nodes.py",
            "flow.py",
            {
                "utils": [
                    "__init__.py",
                    "call_llm.py",
                    "tools.py",
                    "prompts.py"
                ]
            },
            {
                "rag_contexts": [
                    "architectural_principles.txt",
                    "planning_guidelines.txt",
                    "coding_standards.txt",
                    "validation_rules.txt",
                    "debugging_tips.txt"
                ]
            },
            "output_artifacts",
            "requirements.txt",
            "README.md"
        ]
    }
]

# Function to create directories and files
def create_structure(base_path, structure):
    for item in structure:
        if isinstance(item, dict):
            for folder, contents in item.items():
                folder_path = os.path.join(base_path, folder)
                os.makedirs(folder_path, exist_ok=True)
                create_structure(folder_path, contents)
        else:
            file_path = os.path.join(base_path, item)
            if "." in item:  # It's a file
                open(file_path, 'a').close()
            else:  # It's a directory
                os.makedirs(file_path, exist_ok=True)

# Create the directory structure
base_directory = "pocketflow_sft_dev_app"
create_structure(base_directory, structure)