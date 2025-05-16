# Part 1: Instructions for Building and Running Docker

1. **Build the Docker Image:**
    Open your terminal in the directory containing these files and run:

    ```bash
    docker build -t autonomous_coder_demo .
    ```

2. **Run the Docker Container:**
    You **MUST** provide your OpenAI API key as an environment variable when running the container.

    ```bash
    docker run -it --rm \
      -e OPENAI_API_KEY="sk-your_openai_api_key_here" \
      autonomous_coder_demo
    ```

    * `-it`: Runs the container in interactive mode with a pseudo-TTY (so you can see output and interact with HITL).
    * `--rm`: Automatically removes the container when it exits.
    * `-e OPENAI_API_KEY="sk-your_openai_api_key_here"`: Passes your API key.
    * You can also override other `ENV` variables set in the Dockerfile here, e.g., `-e MAX_REFINEMENTS="2"`.

    If you want to map the `output_artifacts_demo` directory from the container to your host machine to inspect the generated files:

    ```bash
    docker run -it --rm \
      -e OPENAI_API_KEY="sk-your_openai_api_key_here" \
      -v "$(pwd)/output_artifacts_host:/app/output_artifacts_demo" \
      autonomous_coder_demo
    ```

    (This creates `output_artifacts_host` in your current directory on the host and maps it to `/app/output_artifacts_demo` inside the container.)
