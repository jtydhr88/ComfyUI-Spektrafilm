import os
import sys

VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)

from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .nodes_io import NODES as IO_NODES
from .nodes_simulation import NODES as SIMULATION_NODES

WEB_DIRECTORY = "./web"


class SpektrafilmExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [*SIMULATION_NODES, *IO_NODES]


async def comfy_entrypoint() -> SpektrafilmExtension:
    return SpektrafilmExtension()
