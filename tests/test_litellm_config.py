"""Validate the LiteLLM configmap so routing regressions are caught in CI."""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIGMAP = (
    Path(__file__).parent.parent
    / "apps/litellm/server/configmap.yaml"
)

LLAMA_CPP_HOST = "10.100.20.19"
DIRECT_PORT = 8088


def _load_model_list() -> list[dict]:
    raw = yaml.safe_load(CONFIGMAP.read_text())
    config_yaml = yaml.safe_load(raw["data"]["config.yaml"])
    return config_yaml["model_list"]


def test_all_llamacpp_models_use_direct_port():
    """Every model backed by the local llama.cpp server must use port 8088 directly.

    Do NOT route through any intermediate proxy port. The proxy (port 8089)
    is deleted and must not be recreated. Context overflow returns an error
    to the caller — that is the correct behavior.
    """
    offenders = []
    for entry in _load_model_list():
        api_base: str = entry.get("litellm_params", {}).get("api_base", "")
        if LLAMA_CPP_HOST not in api_base:
            continue
        if f":{DIRECT_PORT}/" not in api_base:
            offenders.append(
                f"  {entry['model_name']!r} → {api_base}  "
                f"(must use :{DIRECT_PORT}/v1 directly)"
            )

    assert not offenders, (
        "The following llama.cpp models are NOT using the direct port "
        f"({DIRECT_PORT}). Do not route through any proxy:\n"
        + "\n".join(offenders)
    )


def test_no_proxy_port_referenced():
    """No model must reference the deleted overflow proxy port (8089).

    Port 8089 was the overflow proxy. It is deleted. Any reference to it
    is a mistake and will cause connection failures.
    """
    proxy_port = 8089
    offenders = [
        f"  {entry['model_name']!r} → {entry.get('litellm_params', {}).get('api_base', '')}"
        for entry in _load_model_list()
        if f":{proxy_port}/" in entry.get("litellm_params", {}).get("api_base", "")
    ]
    assert not offenders, (
        f"The following models reference deleted proxy port {proxy_port}:\n"
        + "\n".join(offenders)
    )
