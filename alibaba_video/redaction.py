from __future__ import annotations

import re


_SIGNED_URL_RE = re.compile(
    r"(?i)https?://[^\s\"']+?(?:[?&](?:Expires|Signature|OSSAccessKeyId|security-token)=[^\s\"']*)+"
)
_BEARER_RE = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+")
_SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|token|secret)\s*[=:]\s*([^\s,;]+)"
)


def redact_text(text: str, secrets: list[str] | None = None) -> str:
    if not text:
        return text
    result = text
    for secret in secrets or []:
        if secret and len(secret) >= 4:
            result = result.replace(secret, "[REDACTED]")
    result = _SIGNED_URL_RE.sub("[REDACTED_URL]", result)
    result = _BEARER_RE.sub(r"\1[REDACTED]", result)
    result = _SECRET_VALUE_RE.sub(r"\1=[REDACTED]", result)
    return result
