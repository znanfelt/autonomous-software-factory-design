import os
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY environment variable not set. LLM calls will likely fail or use mocks.")
        # Optionally, raise an error or return a mock client
        # raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

DEFAULT_MODEL = "gpt-4o" # Define a default model

def call_llm(messages: list, model: str = DEFAULT_MODEL, temperature: float = 0.2) -> str:
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"} # Assuming you want JSON output for structured prompts
        )
        content = response.choices[0].message.content
        if content is None:
            logger.error("LLM response content is None.")
            return '{"error": "LLM returned no content"}' # Return valid JSON error string
        return content
    except Exception as e:
        logger.error(f"Error calling LLM API: {e}", exc_info=True)
        return f'{{"error": "LLM API call failed: {str(e)}"}}' # Return valid JSON error string


if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)
    
    print("Testing call_llm (expecting JSON parsable string):")
    # Test with a prompt that should ideally produce JSON
    test_messages = [
        {"role": "system", "content": "You are a helpful assistant. Respond in JSON format."},
        {"role": "user", "content": "What is the meaning of life? Respond with a key 'answer'."}
    ]
    # Ensure API key is set in your environment for this test to run properly
    if os.getenv("OPENAI_API_KEY"):
        response_str = call_llm(test_messages)
        print(f"Raw LLM Response: {response_str}")
        try:
            import json
            response_json = json.loads(response_str)
            print(f"Parsed JSON Response: {response_json}")
            if "error" in response_json:
                print("LLM call resulted in an error or could not produce valid JSON as requested.")
        except json.JSONDecodeError as e:
            print(f"Failed to parse LLM response as JSON: {e}")
            print("This might indicate the LLM did not adhere to the JSON output format request, or an API error occurred.")
    else:
        print("OPENAI_API_KEY not set. Skipping live API call test.")