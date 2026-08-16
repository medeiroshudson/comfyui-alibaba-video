from __future__ import annotations

import os
from dataclasses import dataclass

from .client import VideoGenerationRequest
from .errors import AlibabaAuthenticationError
from .settings import normalize_native_base_url


@dataclass(frozen=True)
class AlibabaRuntimeConfig:
    endpoint: str
    api_key: str


def load_runtime_config(
    *,
    endpoint_var: str = "AI_ALIBABA_API_ENDPOINT",
    key_var: str = "AI_ALIBABA_API_KEY",
) -> AlibabaRuntimeConfig:
    endpoint = os.environ.get(endpoint_var, "").strip()
    api_key = os.environ.get(key_var, "")
    if not api_key:
        raise AlibabaAuthenticationError("Alibaba API key is not configured")
    return AlibabaRuntimeConfig(
        endpoint=normalize_native_base_url(endpoint),
        api_key=api_key,
    )


def build_request(
    *,
    model: str,
    prompt: str,
    duration: int,
    resolution: str,
    ratio: str,
    watermark: bool = False,
) -> VideoGenerationRequest:
    return VideoGenerationRequest(
        model=model,
        prompt=prompt,
        duration=duration,
        resolution=resolution,
        ratio=ratio,
        watermark=watermark,
    )


__all__ = [
    "AlibabaRuntimeConfig",
    "build_request",
    "load_runtime_config",
]
