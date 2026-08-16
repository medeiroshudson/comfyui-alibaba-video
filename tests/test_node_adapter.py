from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alibaba_video.client import VideoGenerationResult
from alibaba_video.node import generate_video_output


class FakeClient:
    def __init__(self, endpoint, api_key, **kwargs):
        self.endpoint = endpoint
        self.api_key = api_key
        self.kwargs = kwargs
        self.request = None

    async def generate(self, request, output_dir):
        self.request = request
        path = Path(output_dir) / "fake.mp4"
        path.write_bytes(b"fake-mp4")
        return VideoGenerationResult(task_id="task-test", video_path=path)


class NodeAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_returns_video_factory_value_without_provider_call(self):
        clients = []
        outputs = []

        def client_factory(endpoint, api_key, **kwargs):
            client = FakeClient(endpoint, api_key, **kwargs)
            clients.append(client)
            return client

        def video_factory(stream):
            outputs.append(stream.read())
            return {"type": "VIDEO", "bytes": outputs[-1]}

        with patch.dict(
            os.environ,
            {
                "AI_ALIBABA_API_ENDPOINT": "https://token-plan.example/compatible-mode/v1",
                "AI_ALIBABA_API_KEY": "runtime-secret",
            },
            clear=False,
        ), tempfile.TemporaryDirectory() as directory:
            result = await generate_video_output(
                model="happyhorse-1.1-t2v",
                prompt="A kite over the sea.",
                duration=3,
                resolution="720P",
                ratio="16:9",
                watermark=False,
                output_dir=Path(directory),
                client_factory=client_factory,
                video_factory=video_factory,
            )

        self.assertEqual(result, {"type": "VIDEO", "bytes": b"fake-mp4"})
        self.assertEqual(clients[0].endpoint, "https://token-plan.example/api/v1")
        self.assertEqual(clients[0].api_key, "runtime-secret")
        self.assertEqual(clients[0].request.model, "happyhorse-1.1-t2v")
        self.assertEqual(clients[0].request.duration, 3)
        self.assertEqual(outputs, [b"fake-mp4"])


if __name__ == "__main__":
    unittest.main()
