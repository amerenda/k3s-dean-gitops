"""Validate the LiteLLM configmap so routing regressions are caught in CI.

Root cause for this test: qwen3-35b-think was routed directly to llama.cpp on
port 8088 instead of the overflow proxy on port 8089. Long prompts (e.g. an
audiobook research request) overflow the 128k context window, llama.cpp returns
HTTP 400, LiteLLM raises BadRequestError, and OWU shows an error with no
graceful recovery.

The overflow proxy (port 8089) catches those 400s, strips old messages, and
retries — so models routed through it survive context overflow silently.
"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIGMAP = (
    Path(__file__).parent.parent
    / "apps/litellm/server/configmap.yaml"
)

LLAMA_CPP_HOST = "10.100.20.19"
OVERFLOW_PROXY_PORT = 8089
DIRECT_PORT = 8088


def _load_model_list() -> list[dict]:
    raw = yaml.safe_load(CONFIGMAP.read_text())
    config_yaml = yaml.safe_load(raw["data"]["config.yaml"])
    return config_yaml["model_list"]


def test_all_llamacpp_models_use_overflow_proxy():
    """Every model backed by the local llama.cpp server must route through the
    overflow proxy (port 8089), not directly to the llama.cpp port (8088).

    Routing directly to 8088 means a 400 from llama.cpp on context overflow
    propagates unhandled to the caller (OWU, LiteLLM client, etc.).
    The overflow proxy on 8089 catches those 400s and retries with trimmed context.
    """
    offenders = []
    for entry in _load_model_list():
        api_base: str = entry.get("litellm_params", {}).get("api_base", "")
        if LLAMA_CPP_HOST not in api_base:
            continue  # not a local llama.cpp model
        if f":{DIRECT_PORT}/" in api_base:
            offenders.append(
                f"  {entry['model_name']!r} → {api_base}  "
                f"(change :{DIRECT_PORT}/ to :{OVERFLOW_PROXY_PORT}/)"
            )

    assert not offenders, (
        "The following models route directly to llama.cpp (port 8088) instead of "
        "the overflow proxy (port 8089). Long prompts will cause unhandled 400 errors:\n"
        + "\n".join(offenders)
    )


def test_overflow_proxy_port_is_used_by_at_least_one_model():
    """Sanity check: the overflow proxy (port 8089) must be referenced by at least
    one model, confirming the proxy is still wired up and the port constant is correct.
    """
    proxy_users = [
        entry["model_name"]
        for entry in _load_model_list()
        if f":{OVERFLOW_PROXY_PORT}/" in entry.get("litellm_params", {}).get("api_base", "")
    ]
    assert proxy_users, (
        f"No model uses the overflow proxy (port {OVERFLOW_PROXY_PORT}). "
        "Check that the proxy is still configured and the port constant is correct."
    )
