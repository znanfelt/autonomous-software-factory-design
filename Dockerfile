# Use an official Python runtime as a parent image
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# OPENAI_API_KEY will be passed at runtime using .env file
# ENV OPENAI_API_KEY="your_openai_api_key_here" # DO NOT HARDCODE HERE - pass at runtime

# Default LLM models (can be overridden at runtime via -e)
ENV ARCHITECT_LLM_MODEL="gpt-4o"
ENV PLANNER_LLM_MODEL="gpt-4o"
ENV DEVELOPER_LLM_MODEL="gpt-3.5-turbo"
ENV TEST_DESIGNER_LLM_MODEL="gpt-3.5-turbo"
ENV QA_LLM_MODEL="gpt-4o"
ENV VALIDATION_LLM_MODEL="gpt-3.5-turbo"
ENV CRITIQUE_LLM_MODEL="gpt-4o-mini"

ENV MAX_PLANNER_ITERATIONS="2"
ENV MAX_REFINEMENTS="3"

# Streamlit specific env vars
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_LOGGER_LEVEL=info
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_RUN_ON_SAVE=true

# Set the working directory in the container
WORKDIR /app

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install dependencies and development tools
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir watchdog[watchmedo]

# Create the database directory
RUN mkdir -p /app/database

# No COPY command here - we'll use volume mounting instead

# Expose the port Streamlit will run on
EXPOSE 8501

# Command to run the Streamlit application
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.runOnSave=true"]
