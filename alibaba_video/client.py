from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from urllib.parse import urlsplit

from .errors import (
    AlibabaArtifactError,
    AlibabaAuthenticationError,
    AlibabaJobFailedError,
    AlibabaQuotaError,
    AlibabaTimeoutError,
    AlibabaTransientError,
    AlibabaValidationError,
)
from .redaction import redact_text
from .settings import SUPPORTED_MODELS, SUPPORTED_RATIOS, SUPPORTED_RESOLUTIONS, normalize_native_base_url


@dataclass(frozen=True)
class VideoGenerationRequest:
    model: str
    prompt: str
    duration: int
    resolution: str
    ratio: str
    watermark: bool = False

    def __post_init__(self) -> None:
        if self.model not in SUPPORTED_MODELS:
            raise AlibabaValidationError(f"Unsupported Alibaba video model: {self.model}")
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise AlibabaValidationError("Alibaba video prompt is required")
        if len(self.prompt) > 5000:
            raise AlibabaValidationError("Alibaba video prompt exceeds 5000 characters")
        if self.duration < 3 or self.duration > 15:
            raise AlibabaValidationError("Alibaba video duration must be between 3 and 15 seconds")
        if self.resolution not in SUPPORTED_RESOLUTIONS:
            raise AlibabaValidationError(f"Unsupported Alibaba video resolution: {self.resolution}")
        if self.ratio not in SUPPORTED_RATIOS:
            raise AlibabaValidationError(f"Unsupported Alibaba video ratio: {self.ratio}")

    def to_payload(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "input": {"prompt": self.prompt},
            "parameters": {
                "resolution": self.resolution,
                "ratio": self.ratio,
                "duration": self.duration,
                "watermark": self.watermark,
            },
        }


@dataclass(frozen=True)
class VideoGenerationResult:
    task_id: str
    video_path: Path


class AlibabaVideoClient:
    """Small native Alibaba video client with bounded polling and safe errors."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        *,
        request_timeout: float = 30.0,
        poll_interval: float = 5.0,
        total_timeout: float = 1200.0,
        max_retries: int = 2,
        retry_backoff: float = 1.0,
        max_artifact_bytes: int = 512 * 1024 * 1024,
        validate_artifact: bool = True,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not api_key:
            raise AlibabaAuthenticationError("Alibaba API key is not configured")
        self.base_url = normalize_native_base_url(endpoint)
        self.api_key = api_key
        self.request_timeout = request_timeout
        self.poll_interval = poll_interval
        self.total_timeout = total_timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self.max_artifact_bytes = max_artifact_bytes
        self.validate_artifact = validate_artifact
        self._opener = opener

    async def generate(self, request: VideoGenerationRequest, output_dir: Path) -> VideoGenerationResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        created = await asyncio.to_thread(self._create_task, request)
        task_id = self._task_id(created)
        deadline = time.monotonic() + self.total_timeout

        while True:
            if time.monotonic() >= deadline:
                raise AlibabaTimeoutError(f"Alibaba video generation timed out after {self.total_timeout:g} seconds")
            status = await asyncio.to_thread(self._query_task, task_id)
            task_status = self._task_status(status)
            if task_status == "SUCCEEDED":
                video_url = self._video_url(status)
                path = await asyncio.to_thread(self._download_artifact, video_url, task_id, output_dir)
                return VideoGenerationResult(task_id=task_id, video_path=path)
            if task_status in {"FAILED", "CANCELED", "CANCELLED"}:
                raise AlibabaJobFailedError(f"Alibaba video generation failed: {self._safe_provider_message(status)}")
            if task_status not in {"PENDING", "RUNNING"}:
                raise AlibabaJobFailedError(f"Alibaba video generation returned unexpected status: {task_status}")
            await asyncio.sleep(min(self.poll_interval, max(0.0, deadline - time.monotonic())))

    def _create_task(self, request: VideoGenerationRequest) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/services/aigc/video-generation/video-synthesis",
            body=request.to_payload(),
        )

    def _query_task(self, task_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/tasks/{task_id}")

    def _request_json(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.base_url + path
        payload = json.dumps(body).encode() if body is not None else None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
            headers["X-DashScope-Async"] = "enable"

        for attempt in range(self.max_retries + 1):
            request = UrlRequest(url, data=payload, headers=headers, method=method)
            try:
                with self._opener(request, timeout=self.request_timeout) as response:
                    raw = response.read(self.max_artifact_bytes + 1)
                if len(raw) > self.max_artifact_bytes:
                    raise AlibabaArtifactError("Alibaba response exceeded the configured size limit")
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise AlibabaTransientError("Alibaba returned an invalid JSON response") from exc
                if not isinstance(parsed, dict):
                    raise AlibabaTransientError("Alibaba returned an invalid response object")
                return parsed
            except HTTPError as exc:
                error_body = self._read_http_error(exc)
                if exc.code in {401, 403}:
                    raise AlibabaAuthenticationError("Alibaba authentication failed") from exc
                if exc.code == 429:
                    raise AlibabaQuotaError("Alibaba quota or rate limit exceeded") from exc
                if exc.code in {400, 422}:
                    raise AlibabaValidationError(self._safe_error_body(error_body)) from exc
                if method == "GET" and 500 <= exc.code < 600 and attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                if 500 <= exc.code < 600:
                    raise AlibabaTransientError("Alibaba service temporarily unavailable") from exc
                raise AlibabaTransientError(f"Alibaba request failed with HTTP {exc.code}") from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise AlibabaTransientError("Alibaba request could not be completed") from exc

        raise AlibabaTransientError("Alibaba request could not be completed")

    def _download_artifact(self, video_url: str, task_id: str, output_dir: Path) -> Path:
        parsed = urlsplit(video_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AlibabaArtifactError("Alibaba returned an invalid video URL")
        endpoint_host = urlsplit(self.base_url).hostname or ""
        artifact_host = parsed.hostname or ""
        if not self._is_allowed_artifact_host(artifact_host, endpoint_host):
            raise AlibabaArtifactError("Alibaba returned a video URL outside the provider domain")
        target = output_dir / f"alibaba_{re.sub(r'[^A-Za-z0-9_.-]', '_', task_id)}.mp4"
        request = UrlRequest(video_url, headers={"Accept": "video/mp4"}, method="GET")
        try:
            with self._opener(request, timeout=self.request_timeout) as response:
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type != "video/mp4":
                    raise AlibabaArtifactError("Alibaba video download did not return video/mp4")
                with target.open("wb") as handle:
                    total = 0
                    while True:
                        chunk = response.read(min(1024 * 1024, self.max_artifact_bytes - total + 1))
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.max_artifact_bytes:
                            raise AlibabaArtifactError("Alibaba video exceeded the configured size limit")
                        handle.write(chunk)
        except HTTPError as exc:
            raise AlibabaArtifactError(f"Alibaba video download failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise AlibabaArtifactError("Alibaba video download could not be completed") from exc

        if target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise AlibabaArtifactError("Alibaba returned an empty video")
        if self.validate_artifact:
            self._validate_mp4(target)
        return target

    def _validate_mp4(self, path: Path) -> None:
        try:
            completed = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=format_name", "-of", "default=nw=1:nk=1", str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AlibabaArtifactError("ffprobe could not validate the Alibaba video") from exc
        if completed.returncode != 0 or "mp4" not in completed.stdout.lower():
            raise AlibabaArtifactError("Alibaba returned an invalid MP4 artifact")

    @staticmethod
    def _task_id(response: dict[str, Any]) -> str:
        value = response.get("output", {}).get("task_id")
        if not isinstance(value, str) or not value:
            raise AlibabaValidationError("Alibaba did not return a task ID")
        return value

    @staticmethod
    def _task_status(response: dict[str, Any]) -> str:
        value = response.get("output", {}).get("task_status")
        return value if isinstance(value, str) else "UNKNOWN"

    @staticmethod
    def _video_url(response: dict[str, Any]) -> str:
        value = response.get("output", {}).get("video_url")
        if not isinstance(value, str) or not value:
            raise AlibabaArtifactError("Alibaba did not return a video URL")
        return value

    def _safe_provider_message(self, response: dict[str, Any]) -> str:
        output = response.get("output", {})
        message = output.get("message") or response.get("message") or "provider task failure"
        return redact_text(str(message), secrets=[self.api_key])[:300]

    def _safe_error_body(self, body: str) -> str:
        return redact_text(body, secrets=[self.api_key])[:300] or "Alibaba rejected the request"

    @staticmethod
    def _read_http_error(exc: HTTPError) -> str:
        try:
            return exc.read(4096).decode("utf-8", errors="replace")
        except OSError:
            return ""

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = self.retry_backoff * (2**attempt)
        if delay:
            time.sleep(delay)

    @staticmethod
    def _is_allowed_artifact_host(host: str, endpoint_host: str) -> bool:
        return host == endpoint_host or host.endswith(".aliyuncs.com")
