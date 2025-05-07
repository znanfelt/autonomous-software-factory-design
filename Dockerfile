# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# OPENAI_API_KEY will be passed at runtime
ENV OPENAI_API_KEY="" 
# Other configurable env vars (can be overridden at runtime)
ENV LOG_LEVEL="INFO"
ENV MAX_REFINEMENTS="3"
ENV MAX_PLANNER_ITERATIONS="2"
ENV ARCHITECT_LLM_MODEL="gpt-4o-mini"
ENV PLANNER_LLM_MODEL="gpt-4o-mini"
ENV DEVELOPER_LLM_MODEL="gpt-3.5-turbo-instruct"
ENV DATACONTRACT_LLM_MODEL="gpt-3.5-turbo"
ENV QA_LLM_MODEL="gpt-4o-mini"
ENV VALIDATION_LLM_MODEL="gpt-3.5-turbo"
ENV CRITIQUE_LLM_MODEL="gpt-4o-mini"

# Set the working directory in the container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .
# If RAG files were separate, they'd be copied here too.
# e.g. COPY rag_contexts/ /app/rag_contexts/

# Command to run the application
# Assuming your main script is named main_pipeline.py
CMD ["python", "main_pipeline.py"]