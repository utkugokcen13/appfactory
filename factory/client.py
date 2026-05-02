"""Bedrock client wrapper for Claude API access."""

import os
from anthropic import AnthropicBedrock
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "global.anthropic.claude-opus-4-7"


def get_client() -> AnthropicBedrock:
    """Create and return a Bedrock client using .env credentials.

    Supports two auth methods:
      1. AWS_BEARER_TOKEN_BEDROCK (Bedrock API key) — picked up automatically
         by the underlying boto3 client when the env var is set.
      2. AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (IAM long-term creds).
    """
    region = os.getenv("AWS_REGION", "us-west-2")
    bearer = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "").strip()
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()

    if bearer:
        return AnthropicBedrock(aws_region=region)
    if access_key and secret_key:
        return AnthropicBedrock(
            aws_access_key=access_key,
            aws_secret_key=secret_key,
            aws_region=region,
        )
    raise RuntimeError(
        "No AWS credentials found. Set AWS_BEARER_TOKEN_BEDROCK in .env "
        "(recommended), or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY."
    )


def test_connection() -> bool:
    """Test the Bedrock connection with a simple prompt."""
    client = get_client()
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=64,
        messages=[{"role": "user", "content": "Say 'connected' if you can read this."}],
    )
    text = response.content[0].text
    print(f"Model: {DEFAULT_MODEL}")
    print(f"Response: {text}")
    print(f"Input tokens: {response.usage.input_tokens}")
    print(f"Output tokens: {response.usage.output_tokens}")
    return "connected" in text.lower()


if __name__ == "__main__":
    if test_connection():
        print("\nBedrock connection successful!")
    else:
        print("\nConnection failed.")
