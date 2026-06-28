"""Integration tests for the live LiteLLM endpoint.

These tests require LITELLM_TEST_KEY env var (or auto-fetched from k8s).
Run with: pytest tests/test_litellm_integration.py -v -m integration

They are skipped in CI unless the key is present.
"""
from __future__ import annotations

import os
import subprocess
import pytest
import requests

LITELLM_BASE = "https://litellm.amer.dev/v1"
THINK_MODEL = "qwen3-35b-think"
BASE_MODEL = "qwen3-35b"
TIMEOUT = 90  # seconds — model is slow on first token


def _get_key() -> str | None:
    key = os.environ.get("LITELLM_TEST_KEY") or os.environ.get("LITELLM_MASTER_KEY")
    if key:
        return key
    try:
        result = subprocess.run(
            ["kubectl", "get", "secret", "-n", "litellm", "litellm-secrets",
             "-o", "jsonpath={.data.master-key}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            import base64
            return base64.b64decode(result.stdout.strip()).decode()
    except Exception:
        pass
    return None


KEY = _get_key()
skip_no_key = pytest.mark.skipif(not KEY, reason="LITELLM_TEST_KEY not available")


def _chat(model: str, messages: list, tools: list | None = None, max_tokens: int = 200) -> dict:
    payload: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
    resp = requests.post(
        f"{LITELLM_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=TIMEOUT,
    )
    return resp.json()


SEARCH_TOOL = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}]


# ── Regression: the exact failure mode from 2026-06-28 ──────────────────────

@pytest.mark.integration
@skip_no_key
def test_null_content_assistant_message_does_not_400():
    """Regression: assistant message with content=null causes 400 from llama.cpp.

    When qwen3-35b-think produces only thinking (no text, no tool calls),
    the response has content=null. OWU stores this verbatim. The next request
    includes that assistant message → llama.cpp returns 400:
    'Assistant message must contain either content or tool_calls'.

    The tool_strip_hook must normalise null → '' before the request reaches llama.cpp.
    """
    messages = [
        {"role": "user", "content": "Hello"},
        # Simulates what OWU sends back: thinking-only assistant turn, content=null
        {"role": "assistant", "content": None, "reasoning_content": "I should say hello back."},
        {"role": "user", "content": "Research home assistant MCP servers"},
    ]
    d = _chat(THINK_MODEL, messages)
    assert "error" not in d, (
        f"Got 400 error — tool_strip_hook did not fix null content: {d.get('error', {}).get('message', '')}"
    )
    assert d.get("choices"), f"No choices in response: {d}"


# ── Tool calling format tests ────────────────────────────────────────────────

@pytest.mark.integration
@skip_no_key
def test_tool_call_returns_proper_openai_format():
    """Model must return tool_calls in OpenAI format, not XML in content.

    If llama.cpp / the Jinja template is broken, the model outputs:
      content: '<tool_call>{"name": "web_search", ...}</tool_call>'
    instead of:
      tool_calls: [{"id": "...", "type": "function", ...}]
    """
    messages = [{"role": "user", "content": "What is the weather in New York?"}]
    d = _chat(BASE_MODEL, messages, tools=SEARCH_TOOL)
    assert "error" not in d, f"Request failed: {d.get('error')}"
    choice = d["choices"][0]
    msg = choice["message"]

    # Must be a tool call, not a text response
    assert choice["finish_reason"] == "tool_calls", (
        f"Expected finish_reason=tool_calls, got {choice['finish_reason']!r}. "
        f"Content: {msg.get('content','')[:200]}"
    )

    # Must have tool_calls in the structured field
    assert msg.get("tool_calls"), "tool_calls field is empty — model did not call the tool"

    # Content must NOT contain raw XML tool calls
    content = msg.get("content") or ""
    assert "<tool_call>" not in content, (
        f"XML tool call leaked into content field — template is broken: {content[:200]}"
    )
    assert "<function_call>" not in content, (
        f"XML function call leaked into content — template is broken: {content[:200]}"
    )

    # Tool call must have valid JSON arguments
    for tc in msg["tool_calls"]:
        import json
        args_str = tc["function"]["arguments"]
        try:
            json.loads(args_str)
        except json.JSONDecodeError:
            pytest.fail(f"Tool call arguments are not valid JSON: {args_str!r}")


@pytest.mark.integration
@skip_no_key
def test_multi_turn_tool_calling_continues_after_result():
    """After receiving a tool result, the model must continue (not loop or 400).

    Failure mode: model gets a tool result but either:
    - Loops and calls the same tool again immediately (should sometimes happen, fine)
    - Returns a 400 due to malformed history
    - Hangs / returns finish_reason=null
    """
    messages = [
        {"role": "user", "content": "Research home assistant MCP servers and give me a brief answer"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "web_search", "arguments": '{"query":"home assistant MCP server"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Found hass-mcp on GitHub by dermotduffy. Also home-assistant-mcp by voska."},
    ]
    d = _chat(BASE_MODEL, messages, tools=SEARCH_TOOL, max_tokens=300)
    assert "error" not in d, f"Got error after tool result: {d.get('error', {}).get('message', '')}"
    choice = d["choices"][0]
    assert choice["finish_reason"] in ("stop", "tool_calls", "length"), (
        f"Unexpected finish_reason: {choice['finish_reason']}"
    )


@pytest.mark.integration
@skip_no_key
def test_think_model_tool_call_format():
    """qwen3-35b-think must also return proper tool_calls (not XML), even with thinking enabled."""
    messages = [{"role": "user", "content": "Search for home assistant MCP servers"}]
    d = _chat(THINK_MODEL, messages, tools=SEARCH_TOOL)
    assert "error" not in d, f"Request failed: {d.get('error')}"
    choice = d["choices"][0]
    msg = choice["message"]

    assert choice["finish_reason"] == "tool_calls", (
        f"Expected tool_calls, got {choice['finish_reason']!r}. Content: {msg.get('content','')[:200]}"
    )
    assert msg.get("tool_calls"), "No tool_calls in response"
    content = msg.get("content") or ""
    assert "<tool_call>" not in content, f"XML in content: {content[:200]}"


@pytest.mark.integration
@skip_no_key
def test_endpoint_reachable():
    """Smoke test: LiteLLM endpoint must respond to a simple request."""
    d = _chat(BASE_MODEL, [{"role": "user", "content": "say hi"}], max_tokens=10)
    assert "error" not in d, f"Endpoint not working: {d.get('error')}"
    assert d.get("choices"), "No choices returned"
