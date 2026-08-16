from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


NATIVE_API_PATH = "/api/v1"
SUPPORTED_MODELS = ("happyhorse-1.1-t2v",)
SUPPORTED_RESOLUTIONS = ("720P", "1080P")
SUPPORTED_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21", "5:4", "4:5")


def normalize_native_base_url(endpoint: str) -> str:
    value = endpoint.strip()
    if not value:
        raise ValueError("Alibaba endpoint is required")
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Alibaba endpoint must be an HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Alibaba endpoint must use HTTPS")
    return urlunsplit((parsed.scheme, parsed.netloc, NATIVE_API_PATH, "", ""))
