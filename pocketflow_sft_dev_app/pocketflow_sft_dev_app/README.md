docker build -t pocketflow-sft-dev-app .

docker run -it --rm -p 8501:8501 \
  -e OPENAI_API_KEY="sk-your_actual_openai_api_key" \
  pocketflow-sft-dev-app