from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from alibaba_video.errors import AlibabaAuthenticationError
from alibaba_video.node_logic import build_request, load_runtime_config


class NodeLogicTests(unittest.TestCase):
    def test_build_request_maps_workflow_inputs(self):
        request = build_request(
            model="happyhorse-1.1-t2v",
            prompt="A kite over the sea.",
            duration=3,
            resolution="720P",
            ratio="16:9",
            watermark=False,
        )
        self.assertEqual(request.model, "happyhorse-1.1-t2v")
        self.assertEqual(request.prompt, "A kite over the sea.")
        self.assertEqual(request.duration, 3)
        self.assertEqual(request.to_payload()["parameters"]["ratio"], "16:9")

    def test_runtime_config_reads_only_environment(self):
        with patch.dict(
            os.environ,
            {
                "AI_ALIBABA_API_ENDPOINT": "https://token-plan.example/compatible-mode/v1",
                "AI_ALIBABA_API_KEY": "runtime-secret",
            },
            clear=False,
        ):
            config = load_runtime_config()
        self.assertEqual(config.endpoint, "https://token-plan.example/api/v1")
        self.assertEqual(config.api_key, "runtime-secret")

    def test_missing_runtime_key_fails_without_network(self):
        with patch.dict(
            os.environ,
            {
                "AI_ALIBABA_API_ENDPOINT": "https://token-plan.example",
                "AI_ALIBABA_API_KEY": "",
            },
            clear=False,
        ):
            with self.assertRaises(AlibabaAuthenticationError):
                load_runtime_config()


if __name__ == "__main__":
    unittest.main()


def test_node_module_does_not_call_provider_at_import_time():
    # Importing the pure node logic is intentionally side-effect free.
    import alibaba_video.node_logic  # noqa: F401
