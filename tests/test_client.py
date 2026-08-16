from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from alibaba_video.client import AlibabaVideoClient, VideoGenerationRequest
from alibaba_video.errors import (
    AlibabaArtifactError,
    AlibabaJobFailedError,
    AlibabaTimeoutError,
)
from alibaba_video.redaction import redact_text
from alibaba_video.settings import normalize_native_base_url


class FakeAlibabaHandler(BaseHTTPRequestHandler):
    server_version = "FakeAlibaba/1.0"

    def log_message(self, *_args):
        return

    def do_POST(self):
        self.server.post_paths.append(self.path)
        self.server.post_headers.append(dict(self.headers))
        length = int(self.headers.get("Content-Length", "0"))
        self.server.post_bodies.append(json.loads(self.rfile.read(length)))
        if self.server.post_status:
            status, body = self.server.post_status.pop(0)
            self._send_json(status, body)
            return
        self._send_json(
            200,
            {"request_id": "request-1", "output": {"task_id": self.server.task_id, "task_status": "PENDING"}},
        )

    def do_GET(self):
        self.server.get_paths.append(self.path)
        if urlparse(self.path).path == "/artifact.mp4":
            self.send_response(self.server.artifact_status)
            self.send_header("Content-Type", self.server.artifact_content_type)
            self.send_header("Content-Length", str(len(self.server.artifact_bytes)))
            self.end_headers()
            self.wfile.write(self.server.artifact_bytes)
            return

        if self.server.get_status:
            status, body = self.server.get_status.pop(0)
            self._send_json(status, body)
            return

        task_status = self.server.task_statuses.pop(0) if self.server.task_statuses else "SUCCEEDED"
        output = {"task_id": self.server.task_id, "task_status": task_status}
        if task_status == "SUCCEEDED":
            output["video_url"] = self.server.artifact_url
        if task_status == "FAILED":
            output["code"] = "ModelTaskFailed"
            output["message"] = "provider failure"
        self._send_json(200, {"request_id": "request-2", "output": output})

    def _send_json(self, status, body):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class FakeAlibabaServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler_class):
        super().__init__(server_address, handler_class)
        self.post_paths = []
        self.post_headers = []
        self.post_bodies = []
        self.get_paths = []
        self.post_status = []
        self.get_status = []
        self.task_statuses = ["PENDING", "RUNNING", "SUCCEEDED"]
        self.task_id = "task-123"
        self.artifact_url = "http://127.0.0.1:%d/artifact.mp4?Expires=secret-signature" % self.server_port
        self.artifact_status = 200
        self.artifact_content_type = "video/mp4"
        self.artifact_bytes = b"not-a-real-mp4"


class AlibabaClientTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = FakeAlibabaServer(("127.0.0.1", 0), FakeAlibabaHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=2)
        cls.server.server_close()

    def setUp(self):
        self.server.post_paths.clear()
        self.server.post_headers.clear()
        self.server.post_bodies.clear()
        self.server.get_paths.clear()
        self.server.post_status.clear()
        self.server.get_status.clear()
        self.server.task_statuses = ["PENDING", "RUNNING", "SUCCEEDED"]
        self.server.artifact_status = 200
        self.server.artifact_content_type = "video/mp4"
        self.server.artifact_bytes = b"not-a-real-mp4"
        self.server.artifact_url = "http://127.0.0.1:%d/artifact.mp4?Expires=secret-signature" % self.server.server_port

    def make_client(self, **kwargs):
        options = {
            "endpoint": self.base_url + "/compatible-mode/v1",
            "api_key": "test-secret-token",
            "request_timeout": 2,
            "poll_interval": 0.01,
            "total_timeout": 2,
        }
        options.update(kwargs)
        return AlibabaVideoClient(**options)

    async def test_payload_and_polling_follow_native_alibaba_contract(self):
        request = VideoGenerationRequest(
            model="happyhorse-1.1-t2v",
            prompt="A red kite over a quiet beach.",
            duration=3,
            resolution="720P",
            ratio="16:9",
            watermark=False,
        )
        client = self.make_client(validate_artifact=False)
        with tempfile.TemporaryDirectory() as directory:
            result = await client.generate(request, Path(directory))
            self.assertEqual(result.task_id, "task-123")
            self.assertEqual(result.video_path.read_bytes(), b"not-a-real-mp4")

        self.assertEqual(self.server.post_paths, ["/api/v1/services/aigc/video-generation/video-synthesis"])
        self.assertEqual(self.server.get_paths[:3], ["/api/v1/tasks/task-123"] * 3)
        self.assertEqual(self.server.post_bodies[0]["model"], "happyhorse-1.1-t2v")
        self.assertEqual(
            self.server.post_bodies[0]["input"],
            {"prompt": "A red kite over a quiet beach."},
        )
        self.assertEqual(
            self.server.post_bodies[0]["parameters"],
            {"resolution": "720P", "ratio": "16:9", "duration": 3, "watermark": False},
        )
        headers = {key.lower(): value for key, value in self.server.post_headers[0].items()}
        self.assertEqual(headers["authorization"], "Bearer test-secret-token")
        self.assertEqual(headers["x-dashscope-async"], "enable")

    async def test_failed_job_raises_safe_error(self):
        self.server.task_statuses = ["FAILED"]
        client = self.make_client(validate_artifact=False)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AlibabaJobFailedError) as raised:
                await client.generate(
                    VideoGenerationRequest(
                        model="happyhorse-1.1-t2v",
                        prompt="failure case",
                        duration=3,
                        resolution="720P",
                        ratio="16:9",
                    ),
                    Path(directory),
                )
        self.assertNotIn("test-secret-token", str(raised.exception))
        self.assertNotIn("secret-signature", str(raised.exception))

    async def test_total_timeout_stops_polling(self):
        self.server.task_statuses = ["RUNNING"] * 100
        client = self.make_client(total_timeout=0.08, poll_interval=0.02, validate_artifact=False)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AlibabaTimeoutError):
                await client.generate(
                    VideoGenerationRequest(
                        model="happyhorse-1.1-t2v",
                        prompt="timeout case",
                        duration=3,
                        resolution="720P",
                        ratio="16:9",
                    ),
                    Path(directory),
                )

    async def test_invalid_download_content_type_is_rejected(self):
        self.server.artifact_content_type = "text/html"
        client = self.make_client(validate_artifact=False)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AlibabaArtifactError):
                await client.generate(
                    VideoGenerationRequest(
                        model="happyhorse-1.1-t2v",
                        prompt="bad download",
                        duration=3,
                        resolution="720P",
                        ratio="16:9",
                    ),
                    Path(directory),
                )

    async def test_download_from_untrusted_host_is_rejected(self):
        self.server.artifact_url = "http://example.invalid/artifact.mp4?Expires=secret-signature"
        self.server.task_statuses = ["SUCCEEDED"]
        client = self.make_client(validate_artifact=False)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AlibabaArtifactError):
                await client.generate(
                    VideoGenerationRequest(
                        model="happyhorse-1.1-t2v",
                        prompt="untrusted download",
                        duration=3,
                        resolution="720P",
                        ratio="16:9",
                    ),
                    Path(directory),
                )

    async def test_create_5xx_is_not_retried_to_avoid_duplicate_jobs(self):
        self.server.post_status = [(500, {"message": "temporary provider error"})]
        client = self.make_client(max_retries=3, retry_backoff=0.001, validate_artifact=False)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Exception):
                await client.generate(
                    VideoGenerationRequest(
                        model="happyhorse-1.1-t2v",
                        prompt="no duplicate job",
                        duration=3,
                        resolution="720P",
                        ratio="16:9",
                    ),
                    Path(directory),
                )
        self.assertEqual(len(self.server.post_paths), 1)

    async def test_transient_status_is_retried_but_auth_is_not(self):
        self.server.get_status = [
            (503, {"message": "temporarily unavailable"}),
            (200, {"output": {"task_id": "task-123", "task_status": "SUCCEEDED", "video_url": self.server.artifact_url}}),
        ]
        client = self.make_client(validate_artifact=False, retry_backoff=0.001)
        with tempfile.TemporaryDirectory() as directory:
            result = await client.generate(
                VideoGenerationRequest(
                    model="happyhorse-1.1-t2v",
                    prompt="retry case",
                    duration=3,
                    resolution="720P",
                    ratio="16:9",
                ),
                Path(directory),
            )
        self.assertEqual(result.task_id, "task-123")

        self.setUp()
        self.server.get_status = [(401, {"message": "Bearer test-secret-token invalid"})]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Exception) as raised:
                await client.generate(
                    VideoGenerationRequest(
                        model="happyhorse-1.1-t2v",
                        prompt="auth case",
                        duration=3,
                        resolution="720P",
                        ratio="16:9",
                    ),
                    Path(directory),
                )
        self.assertNotIn("test-secret-token", str(raised.exception))


class PureFunctionTests(unittest.TestCase):
    def test_endpoint_normalization_uses_native_api_path(self):
        self.assertEqual(
            normalize_native_base_url("https://token-plan.example/compatible-mode/v1"),
            "https://token-plan.example/api/v1",
        )
        self.assertEqual(
            normalize_native_base_url("https://token-plan.example/api/v1/"),
            "https://token-plan.example/api/v1",
        )

    def test_redaction_removes_tokens_and_signed_urls(self):
        source = (
            "Authorization: Bearer abc123; api_key=abc123; "
            "video_url=https://storage.example/video.mp4?Expires=123&Signature=abc"
        )
        cleaned = redact_text(source, secrets=["abc123"])
        self.assertNotIn("abc123", cleaned)
        self.assertNotIn("Signature=abc", cleaned)
        self.assertIn("[REDACTED]", cleaned)

    def test_mp4_fixture_is_available_for_artifact_validation(self):
        if shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg/ffprobe unavailable")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=64x64:d=0.1",
                    "-pix_fmt",
                    "yuv420p",
                    "-y",
                    str(path),
                ],
                check=True,
            )
            self.assertTrue(path.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
