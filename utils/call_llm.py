# utils/call_llm.py
import os
from openai import OpenAI
import logging
import json  # Ensure json is imported

logger = logging.getLogger(__name__)


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning(
            "OPENAI_API_KEY environment variable not set. LLM calls will likely fail or use mocks."
        )
    return OpenAI(api_key=api_key)


DEFAULT_MODEL = "gpt-4o"


def call_llm(
    messages: list,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    expect_json: bool = True,
) -> str:
    client = get_openai_client()
    request_params = {
        "model": model,
        "messages": messages,  # Pass messages directly
        "temperature": temperature,
    }
    if expect_json:
        request_params["response_format"] = {"type": "json_object"}
        # The prompt itself MUST now contain the instruction for JSON output.
        # This function will no longer try to append it.
        # Example: The last user message in `messages` should end with
        # "Please ensure your entire response is a single, valid JSON object."

    try:
        response = client.chat.completions.create(**request_params)  # type: ignore
        content = response.choices[0].message.content
        if content is None:
            logger.error("LLM response content is None.")
            return json.dumps(
                {"error": "LLM returned no content"}
            )  # Ensure valid JSON string
        return content
    except Exception as e:
        logger.error(f"Error calling LLM API: {e}", exc_info=True)
        # Ensure valid JSON string for errors
        error_payload = {"error": f"LLM API call failed: {str(e)}"}
        # Attempt to include more details if it's an API specific error with a body
        if hasattr(e, "response") and hasattr(e.response, "text"):  # type: ignore
            try:
                error_payload["api_response"] = json.loads(e.response.text)  # type: ignore
            except:
                error_payload["api_response_raw"] = e.response.text  # type: ignore
        return json.dumps(error_payload)


if __name__ == "__main__":
    # ... (main test remains same)
    logger.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)

    print("Testing call_llm (expecting JSON parsable string by default):")
    test_messages_json = [
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },  # Removed "Respond in JSON" here
        {
            "role": "user",
            "content": "What is the meaning of life? Respond with a key 'answer'. Please ensure your entire response is a single, valid JSON object.",
        },  # Added JSON instruction here
    ]
    if os.getenv("OPENAI_API_KEY"):
        response_str_json = call_llm(test_messages_json)
        print(f"Raw LLM JSON Response: {response_str_json}")
        try:
            response_json_parsed = json.loads(response_str_json)
            print(f"Parsed JSON Response: {response_json_parsed}")
            if "error" in response_json_parsed:
                print("LLM call resulted in an error.")
        except json.JSONDecodeError as e:
            print(f"Failed to parse LLM JSON response: {e}")

        print("\nTesting call_llm (expecting raw text for code):")
        test_messages_code = [
            {
                "role": "system",
                "content": "You are a Python coding assistant. Output only code.",
            },
            {"role": "user", "content": "Write a python function to add two numbers."},
        ]
        response_str_code = call_llm(test_messages_code, expect_json=False)
        print(f"Raw LLM Code Response:\n{response_str_code}")
        if response_str_code.startswith(
            '{"error"'
        ):  # Check if it's our JSON error format
            try:
                parsed_error = json.loads(response_str_code)
                if "error" in parsed_error:
                    print(
                        f"LLM call for code resulted in an error: {parsed_error['error']}"
                    )
            except:
                pass  # Not a JSON error, actual code (or other non-JSON error from LLM)
    else:
        print("OPENAI_API_KEY not set. Skipping live API call test.")
