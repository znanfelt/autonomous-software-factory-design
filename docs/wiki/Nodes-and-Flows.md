# Nodes and Flows

Nodes define discrete AI-driven steps in PocketFlow. Important nodes include:

- **ArchitectPlannerNode** – clarifies the request and outputs a plan
- **DeveloperNode** – generates or refines code
- **TestCaseDesignerNode** – proposes tests for the planned function
- **QANode** – runs tests using the provided `code_tester_tool`
- **ValidationNode** – checks style rules and guidelines
- **SecurityComplianceNode** – reviews basic security/compliance concerns
- **CritiqueNode** – gives feedback when tests or validation fail or when the user rejects the code
- **PackageNode** – assembles the final artifacts

Flows wire these nodes together to create stages such as elicitation, code generation, QA/validation, critique, and packaging.
