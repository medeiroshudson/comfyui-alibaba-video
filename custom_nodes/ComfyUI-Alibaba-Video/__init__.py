"""ComfyUI V3 custom-node entrypoint for Alibaba Token Plan video generation."""

import os
import sys

from typing_extensions import override

from comfy_api.latest import ComfyExtension

sys.path.insert(0, os.path.dirname(__file__))
from alibaba_video.node import AlibabaTextToVideo  # noqa: E402

__version__ = "0.1.0"


class AlibabaVideoExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type]:
        return [AlibabaTextToVideo]


async def comfy_entrypoint() -> AlibabaVideoExtension:
    return AlibabaVideoExtension()


__all__ = ["AlibabaVideoExtension", "comfy_entrypoint"]
