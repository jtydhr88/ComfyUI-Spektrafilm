import asyncio
import io

import numpy as np
from aiohttp import web
from PIL import Image

from .nodes_simulation import LIVE_INPUTS, PARAM_NODES, render, simulator_for


def render_live(image: np.ndarray, chain: list, main: dict, fast: bool) -> bytes:
    params = None
    for item in chain:
        params = PARAM_NODES[item["type"]].execute(params=params, **item["inputs"]).result[0]
    main = dict(main)
    seed = main.pop("seed")
    main.pop("preview", None)
    result = render(simulator_for(params=params, preview=fast, **main), image, seed)
    buffer = io.BytesIO()
    Image.fromarray(np.round(result * 255).astype(np.uint8)).save(buffer, "JPEG", quality=92)
    return buffer.getvalue()


async def live_preview(request: web.Request) -> web.Response:
    body = await request.json()
    image = LIVE_INPUTS.get(str(body.get("key")))
    if image is None:
        return web.json_response({"error": "no input yet"}, status=404)
    try:
        jpeg = await asyncio.to_thread(render_live, image, body["chain"], body["main"], bool(body.get("fast", True)))
    except (KeyError, TypeError, ValueError) as e:
        return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=400)
    return web.Response(body=jpeg, content_type="image/jpeg")


def register_routes(routes) -> None:
    routes.post("/spektrafilm/live_preview")(live_preview)
