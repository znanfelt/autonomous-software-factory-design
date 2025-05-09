# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# OPENAI_API_KEY will be passed at runtime
ENV OPENAI_API_KEY="TODO" 
# Other configurable env vars (can be overridden at runtime)
ENV LOG_LEVEL="INFO"
ENV MAX_REFINEMENTS="3"
ENV MAX_PLANNER_ITERATIONS="2"

ENV STREAMLIT_SERVER_PORT=8501 
ENV STREAMLIT_SERVER_HEADLESS=true 
ENV STREAMLIT_ENABLE_CORS=false 

# ENV ARCHITECT_LLM_MODEL="gpt-4o-mini"
# ENV PLANNER_LLM_MODEL="gpt-4o-mini"
# ENV DEVELOPER_LLM_MODEL="gpt-3.5-turbo-instruct"
# ENV DATACONTRACT_LLM_MODEL="gpt-3.5-turbo"
# ENV QA_LLM_MODEL="gpt-4o-mini"
# ENV VALIDATION_LLM_MODEL="gpt-3.5-turbo"
# ENV CRITIQUE_LLM_MODEL="gpt-4o-mini"

# Set the working directory in the container
# WORKDIR /app

# # Install dependencies
# COPY requirements.txt .
# RUN mkdir -p /app/output_artifacts_demo
# COPY . .
# RUN pip install --no-cache-dir -r requirements.txt


# # 6. Create the artifacts directory (application also creates it, but good for clarity)
# #    The application runs as root by default in the container, so it will have write permissions.
# # RUN mkdir -p /app/output_artifacts_demo

# # 7. Expose Streamlit port
# EXPOSE 8501

# # Copy the rest of the application code into the container
# # COPY . .
# # If RAG files were separate, they'd be copied here too.
# # e.g. COPY rag_contexts/ /app/rag_contexts/

# # Command to run the application
# # Assuming your main script is named main_pipeline.py
# # CMD ["python", "main_pipeline.py"]
# CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0"]


# 3. Working Directory
WORKDIR /app

# 4. Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy application code
COPY main_pipeline.py .
COPY streamlit_app.py .
COPY ui ./ui
COPY main_pipeline ./main_pipeline
COPY tests ./tests

# 6. Create the artifacts directory (application also creates it, but good for clarity)
#    The application runs as root by default in the container, so it will have write permissions.
RUN mkdir -p /app/output_artifacts_demo

# 7. Expose Streamlit port
EXPOSE 8501

# 8. Command to run the Streamlit app
#    --server.address=0.0.0.0 makes it accessible from outside the container
CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0"]