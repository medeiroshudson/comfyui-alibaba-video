from __future__ import annotations

import io
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from .client import AlibabaVideoClient
from .node_logic import build_request, load_runtime_config


async def generate_video_output(
    *,
    model: str,
    prompt: str,
    duration: int,
    resolution: str,
    ratio: str,
    watermark: bool,
    output_dir: Path,
    client_factory: Callable[..., Any] = AlibabaVideoClient,
    video_factory: Callable[[io.BytesIO], Any] | None = None,
) -> Any:
    """Generate one video and convert its temporary MP4 through ``video_factory``."""
    config = load_runtime_config()
    request = build_request(
        model=model,
        prompt=prompt,
        duration=duration,
        resolution=resolution,
        ratio=ratio,
        watermark=watermark,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    job_dir = Path(tempfile.mkdtemp(prefix="alibaba-video-", dir=str(output_dir)))
    try:
        client = client_factory(endpoint=config.endpoint, api_key=config.api_key)
        result = await client.generate(request, job_dir)
        data = result.video_path.read_bytes()
        if not data:
            raise ValueError("Alibaba returned an empty video artifact")
        stream = io.BytesIO(data)
        if video_factory is None:
            return stream
        return video_factory(stream)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


try:
    from comfy_api.latest import IO, Input, InputImpl
except ImportError:  # Allows unit tests to run outside a ComfyUI process.
    IO = None
    Input = None
    InputImpl = None
else:

    class AlibabaTextToVideo(IO.ComfyNode):
        @classmethod
        def define_schema(cls) -> IO.Schema:
            return IO.Schema(
                node_id="AlibabaTextToVideo",
                display_name="Alibaba Text to Video",
                category="alibaba/video",
                description="Generates a hosted video through the Alibaba Token Plan.",
                inputs=[
                    IO.Combo.Input("model", options=["happyhorse-1.1-t2v"]),
                    IO.String.Input("prompt", multiline=True, default=""),
                    IO.Int.Input("duration", default=3, min=3, max=15, step=1),
                    IO.Combo.Input("resolution", options=["720P", "1080P"], default="720P"),
                    IO.Combo.Input(
                        "ratio",
                        options=["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21", "5:4", "4:5"],
                        default="16:9",
                    ),
                    IO.Boolean.Input("watermark", default=False, advanced=True),
                ],
                outputs=[IO.Video.Output()],
            )

        @classmethod
        async def execute(
            cls,
            model: str,
            prompt: str,
            duration: int,
            resolution: str,
            ratio: str,
            watermark: bool = False,
        ) -> IO.NodeOutput:
            output = await generate_video_output(
                model=model,
                prompt=prompt,
                duration=duration,
                resolution=resolution,
                ratio=ratio,
                watermark=watermark,
                output_dir=Path(os.environ.get("ALIBABA_VIDEO_TEMP_DIR", "/tmp")),
                video_factory=InputImpl.VideoFromFile,
            )
            return IO.NodeOutput(output)


if IO is not None:
    NODE_CLASS_MAPPINGS = {"AlibabaTextToVideo": AlibabaTextToVideo}
    NODE_DISPLAY_NAME_MAPPINGS = {"AlibabaTextToVideo": "Alibaba Text to Video"}
else:
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}


__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "generate_video_output"]
