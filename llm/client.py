"""OpenAI API wrapper — single LLM entry point for the entire project."""

import json
import logging
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    """Lazy-init OpenAI client."""
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY not set. "
                "Copy .env.example to .env and add your key."
            )
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def chat(
    system_prompt: str,
    user_prompt: str,
    response_json: bool = True,
    max_tokens: int = 1024,
) -> str:
    """Send a chat completion request. Returns raw response text."""
    client = _get_client()

    kwargs = dict(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    if response_json:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content
        logger.debug("LLM response: %s", content[:300])
        return content
    except Exception as e:
        logger.error("OpenAI API call failed: %s", e)
        raise


def chat_json(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
) -> dict:
    """Send chat and parse the JSON response into a dict."""
    raw = chat(
        system_prompt,
        user_prompt,
        response_json=True,
        max_tokens=max_tokens,
    )
    raw = raw.strip()
    # Strip markdown code fences if the model wraps them
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        raw = "\n".join(lines)
    return json.loads(raw)