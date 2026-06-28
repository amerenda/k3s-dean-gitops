"""Integration tests for the live LiteLLM endpoint.

These tests require LITELLM_TEST_KEY env var (or auto-fetched from k8s).
Run with: pytest tests/test_litellm_integration.py -v -m integration

They are skipped in CI unless the key is present.

--- WHY THESE TESTS EXIST ---

LiteLLM retries 400 errors up to 3 times before failing. This means a test
that calls _chat() and gets 200 OK may have had 1-3 hidden 400s underneath.
To catch those hidden failures, streaming tests are included: a streaming 400
surfaces immediately in the first chunk (LiteLLM cannot hide it by retrying).

The known failure mode: when qwen3-35b-think makes a tool call, the response
has content=null. OWU stores this verbatim. On the NEXT request the assistant
message has content=null which LiteLLM's cleanup_none_field_in_message strips
entirely — producing {"role": "assistant"} with no content and no tool_calls.
llama.cpp rejects this: "Assistant message must contain either content or
tool_calls". The tool_strip_hook normalises null → "" before cleanup runs.

Tests cover both the simple (1 round) and realistic (2+ rounds) cases, and
use streaming because OWU always streams.
"""
from __future__ import annotations

import json
import os
import subprocess
import pytest
import requests

LITELLM_BASE = "https://litellm.amer.dev/v1"
THINK_MODEL = "qwen3-35b-think"
BASE_MODEL = "qwen3-35b"
TIMEOUT = 120  # seconds — model is slow on first token


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

HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

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


def _chat(model: str, messages: list, tools: list | None = None, max_tokens: int = 200) -> dict:
    """Non-streaming chat. LiteLLM will silently retry 400s — use _stream_chat to catch them."""
    payload: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
    resp = requests.post(
        f"{LITELLM_BASE}/chat/completions",
        headers=HEADERS,
        json=payload,
        timeout=TIMEOUT,
    )
    return resp.json()


def _stream_chat(model: str, messages: list, tools: list | None = None, max_tokens: int = 200) -> dict:
    """Streaming chat that surfaces 400s immediately.

    LiteLLM cannot retry a streaming 400 without the caller seeing it, so
    this is the correct way to test for hidden failures. Returns a dict with
    either 'error' (on failure) or 'finish_reason' + 'content' (on success).
    """
    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    resp = requests.post(
        f"{LITELLM_BASE}/chat/completions",
        headers=HEADERS,
        json=payload,
        stream=True,
        timeout=TIMEOUT,
    )

    accumulated_content = ""
    accumulated_tool_calls: dict = {}
    finish_reason = None

    for line in resp.iter_lines():
        if not line:
            continue
        if line == b"data: [DONE]":
            break
        if not line.startswith(b"data: "):
            continue
        try:
            chunk = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        if "error" in chunk:
            return {"error": chunk["error"]}

        for choice in chunk.get("choices", []):
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
            delta = choice.get("delta", {})
            if delta.get("content"):
                accumulated_content += delta["content"]
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                if idx not in accumulated_tool_calls:
                    accumulated_tool_calls[idx] = {
                        "id": "", "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                if tc.get("id"):
                    accumulated_tool_calls[idx]["id"] = tc["id"]
                fn = tc.get("function") or {}
                accumulated_tool_calls[idx]["function"]["name"] += fn.get("name") or ""
                accumulated_tool_calls[idx]["function"]["arguments"] += fn.get("arguments") or ""

    result: dict = {"finish_reason": finish_reason, "content": accumulated_content}
    if accumulated_tool_calls:
        result["tool_calls"] = list(accumulated_tool_calls.values())
    return result


# ── Regression: null content assistant message (simple, 1 turn) ──────────────

@pytest.mark.integration
@skip_no_key
def test_null_content_assistant_message_does_not_400():
    """Regression: thinking-only assistant turn (content=null, no tool_calls) causes 400.

    When qwen3-35b-think produces only a reasoning block, content=null.
    OWU stores this and resends it. LiteLLM strips the content key entirely
    (None → missing), which llama.cpp rejects.
    """
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": None, "reasoning_content": "I should say hello back."},
        {"role": "user", "content": "Research home assistant MCP servers"},
    ]
    d = _chat(THINK_MODEL, messages)
    assert "error" not in d, (
        f"Got error — hook did not fix null content: {d.get('error', {}).get('message', '')}"
    )
    assert d.get("choices"), f"No choices in response: {d}"


@pytest.mark.integration
@skip_no_key
def test_null_content_streaming_does_not_400():
    """Same as above but via streaming — catches failures LiteLLM silently retries.

    OWU always uses streaming. A 400 in a streaming request cannot be hidden
    by retry the way non-streaming 400s are. This test verifies the fix works
    for the actual production code path.
    """
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": None, "reasoning_content": "I should say hello back."},
        {"role": "user", "content": "What day is it?"},
    ]
    result = _stream_chat(THINK_MODEL, messages)
    assert "error" not in result, (
        f"Streaming 400 — hook did not fix null content for think model: {result.get('error')}"
    )
    assert result.get("finish_reason"), f"No finish_reason in stream: {result}"


# ── Regression: multi-turn null content (the actual production failure) ───────

@pytest.mark.integration
@skip_no_key
def test_multi_turn_null_content_tool_calls_streaming():
    """The exact failure mode from 2026-06-28: OWU research session with qwen3-35b-think.

    WHAT FAILS IN PRODUCTION:
    - User asks to research something with tools available
    - Model makes 2 tool calls (each stored by OWU with content=null)
    - On the synthesis request the history has 2 assistant messages with content=null
    - LiteLLM's cleanup strips both content keys → 2 assistant messages with
      neither content nor tool_calls → llama.cpp returns 400

    WHY TESTS WERE MISSING THIS:
    1. test_multi_turn_tool_calling_continues_after_result uses content="" not null
    2. All prior tests use non-streaming, hiding retried 400s
    3. No test covered 2+ sequential tool call rounds with null content

    This test uses streaming (to surface hidden 400s) and null content in ALL
    assistant tool_call messages (exactly what OWU stores from streaming responses).
    """
    # This is what OWU sends when asking for synthesis after 2 tool call rounds.
    # Both assistant messages have content=null — OWU accumulates "" from streaming
    # deltas, then converts that to None via `accumulated_content or None`.
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Research home assistant MCP servers. Do not call praetor dispatch, just search and report."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_praetor_1",
                "type": "function",
                "function": {"name": "lm_praetor_add_mcp", "arguments": '{"name": "hass-mcp"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_praetor_1", "content": "MCP server registered."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_web_1",
                "type": "function",
                "function": {"name": "lm_web_search", "arguments": '{"query": "home assistant MCP server github"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_web_1", "content": "Found hass-mcp by dermotduffy on GitHub. Also home-assistant-mcp by voska. Both expose HA entities and automations to AI assistants via MCP."},
    ]
    result = _stream_chat(THINK_MODEL, messages, tools=SEARCH_TOOL, max_tokens=300)
    assert "error" not in result, (
        f"400 on synthesis request — multi-turn null content not fixed: {result.get('error')}"
    )
    assert result.get("finish_reason") in ("stop", "tool_calls", "length"), (
        f"Unexpected finish_reason: {result.get('finish_reason')}"
    )


@pytest.mark.integration
@skip_no_key
def test_multi_turn_null_content_base_model_streaming():
    """Same multi-turn null-content scenario but with qwen3-35b (not think model).

    The 2026-06-28 failure log also showed 400s for qwen3-35b, not just the
    think model. Covers the case where a previous think-model session history
    is replayed with the base model.
    """
    messages = [
        {"role": "user", "content": "Research kubernetes gitops tools."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "web_search", "arguments": '{"query": "kubernetes gitops ArgoCD Flux"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ArgoCD and Flux CD are the two main GitOps operators for Kubernetes."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_2",
                "type": "function",
                "function": {"name": "web_search", "arguments": '{"query": "ArgoCD vs Flux CD comparison"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_2", "content": "ArgoCD has a web UI, Flux is more GitOps-native. Both are CNCF graduated projects."},
    ]
    result = _stream_chat(BASE_MODEL, messages, tools=SEARCH_TOOL, max_tokens=300)
    assert "error" not in result, (
        f"400 on synthesis with base model — null content in tool_call history: {result.get('error')}"
    )
    assert result.get("finish_reason") in ("stop", "tool_calls", "length"), (
        f"Unexpected finish_reason: {result.get('finish_reason')}"
    )


# ── Tool calling format tests ─────────────────────────────────────────────────

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

    assert choice["finish_reason"] == "tool_calls", (
        f"Expected finish_reason=tool_calls, got {choice['finish_reason']!r}. "
        f"Content: {msg.get('content','')[:200]}"
    )
    assert msg.get("tool_calls"), "tool_calls field is empty"

    content = msg.get("content") or ""
    assert "<tool_call>" not in content, f"XML tool call leaked into content: {content[:200]}"
    assert "<function_call>" not in content, f"XML function call leaked into content: {content[:200]}"

    for tc in msg["tool_calls"]:
        args_str = tc["function"]["arguments"]
        try:
            json.loads(args_str)
        except json.JSONDecodeError:
            pytest.fail(f"Tool call arguments are not valid JSON: {args_str!r}")


@pytest.mark.integration
@skip_no_key
def test_multi_turn_tool_calling_continues_after_result():
    """After receiving a tool result, the model must continue (not 400)."""
    messages = [
        {"role": "user", "content": "Research home assistant MCP servers and give me a brief answer"},
        {
            "role": "assistant",
            "content": None,  # null — exactly what OWU stores from streaming
            "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "web_search", "arguments": '{"query":"home assistant MCP server"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Found hass-mcp on GitHub by dermotduffy. Also home-assistant-mcp by voska."},
    ]
    result = _stream_chat(BASE_MODEL, messages, tools=SEARCH_TOOL, max_tokens=300)
    assert "error" not in result, f"Got error after tool result: {result.get('error')}"
    assert result.get("finish_reason") in ("stop", "tool_calls", "length"), (
        f"Unexpected finish_reason: {result.get('finish_reason')}"
    )


@pytest.mark.integration
@skip_no_key
def test_think_model_tool_call_format():
    """qwen3-35b-think must return proper tool_calls (not XML) via streaming."""
    result = _stream_chat(THINK_MODEL, [{"role": "user", "content": "Search for home assistant MCP servers"}], tools=SEARCH_TOOL)
    assert "error" not in result, f"Request failed: {result.get('error')}"
    assert result.get("finish_reason") == "tool_calls", (
        f"Expected tool_calls, got {result.get('finish_reason')!r}. Content: {result.get('content','')[:200]}"
    )
    assert result.get("tool_calls"), "No tool_calls in response"
    content = result.get("content") or ""
    assert "<tool_call>" not in content, f"XML in content: {content[:200]}"


@pytest.mark.integration
@skip_no_key
def test_endpoint_reachable():
    """Smoke test: LiteLLM endpoint must respond to a simple request."""
    d = _chat(BASE_MODEL, [{"role": "user", "content": "say hi"}], max_tokens=10)
    assert "error" not in d, f"Endpoint not working: {d.get('error')}"
    assert d.get("choices"), "No choices returned"
