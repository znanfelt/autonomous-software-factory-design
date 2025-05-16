# Dockerfile
# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# OPENAI_API_KEY will be passed at runtime using -e or Docker Compose environment section
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

# Set the working directory in the container
WORKDIR /app

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Create the database directory (Streamlit will run as root by default, so it can write here)
# The init_db() function in database.py will create the actual file if it doesn't exist.
RUN mkdir -p /app/database

# Expose the port Streamlit will run on
EXPOSE 8501

# Command to run the Streamlit application
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]