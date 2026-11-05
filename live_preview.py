import asyncio
import io

import numpy as np
from aiohttp import web
from PIL import Image
from spektrafilm import Simulator
from spektrafilm.runtime.services.resize import ResizingService
from spektrafilm.utils.autoexposure import measure_autoexposure_ev

from .nodes_simulation import LIVE_INPUTS, PARAM_NODES, LiveInput, params_for, render

LUT_SIZE = 33
LUT_FORCED = {
    "camera.auto_exposure": False,
    "debug.deactivate_spatial_effects": True,
    "debug.deactivate_stochastic_effects": True,
    "io.crop": False,
    "io.upscale_factor": 1.0,
}


def chain_params(chain: list) -> dict | None:
    params = None
    for item in chain:
        params = PARAM_NODES[item["type"]].execute(params=params, **item["inputs"]).result[0]
    return params


def main_values(main: dict) -> tuple[dict, int]:
    main = dict(main)
    seed = main.pop("seed")
    main.pop("preview", None)
    return main, seed


def render_live(image: np.ndarray, chain: list, main: dict, fast: bool) -> bytes:
    main, seed = main_values(main)
    result = render(Simulator(params_for(params=chain_params(chain), preview=fast, **main)), image, seed)
    buffer = io.BytesIO()
    Image.fromarray(np.round(result * 255).astype(np.uint8)).save(buffer, "JPEG", quality=92)
    return buffer.getvalue()


def bake_lut(live: LiveInput, chain: list, main: dict) -> tuple[np.ndarray, float]:
    params = chain_params(chain)
    main, _ = main_values(main)
    exact = params_for(params=params, preview=True, **main)
    ev = 0.0
    if exact.camera.auto_exposure:
        small = ResizingService(exact.io, exact.camera.film_format_mm).small_preview(live.preview)
        ev = measure_autoexposure_ev(small, exact.io.input_color_space, exact.io.input_cctf_decoding,
                                     method=exact.camera.auto_exposure_method)
    gamma = 1.0 if exact.io.input_cctf_decoding else 2.4
    grid = live.max * np.linspace(0.0, 1.0, LUT_SIZE) ** gamma
    b, g, r = np.meshgrid(grid, grid, grid, indexing="ij")
    cube = np.stack([r, g, b], axis=-1).reshape(LUT_SIZE * LUT_SIZE, LUT_SIZE, 3) * 2 ** ev
    lut = render(Simulator(params_for(params=params, preview=True, forced=LUT_FORCED, **main)), cube, 0)
    return lut.reshape(LUT_SIZE, LUT_SIZE, LUT_SIZE, 3), gamma


def _live_input(key) -> LiveInput | None:
    return LIVE_INPUTS.get(str(key))


async def live_preview(request: web.Request) -> web.Response:
    body = await request.json()
    live = _live_input(body.get("key"))
    if live is None:
        return web.json_response({"error": "no input yet"}, status=404)
    try:
        jpeg = await asyncio.to_thread(render_live, live.preview, body["chain"], body["main"], bool(body.get("fast", True)))
    except (KeyError, TypeError, ValueError) as e:
        return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=400)
    return web.Response(body=jpeg, content_type="image/jpeg")


async def live_lut(request: web.Request) -> web.Response:
    body = await request.json()
    live = _live_input(body.get("key"))
    if live is None:
        return web.json_response({"error": "no input yet"}, status=404)
    try:
        lut, gamma = await asyncio.to_thread(bake_lut, live, body["chain"], body["main"])
    except (KeyError, TypeError, ValueError) as e:
        return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=400)
    return web.Response(body=lut.astype(np.float16).tobytes(), content_type="application/octet-stream",
                        headers={"X-Lut-Size": str(LUT_SIZE), "X-Lut-Max": str(live.max), "X-Lut-Gamma": str(gamma)})


async def live_input(request: web.Request) -> web.Response:
    live = _live_input(request.query.get("key"))
    if live is None:
        return web.json_response({"error": "no input yet"}, status=404)
    height, width = live.display.shape[:2]
    return web.Response(body=live.display.tobytes(), content_type="application/octet-stream",
                        headers={"X-Width": str(width), "X-Height": str(height)})


def register_routes(routes) -> None:
    routes.post("/spektrafilm/live_preview")(live_preview)
    routes.post("/spektrafilm/live_lut")(live_lut)
    routes.get("/spektrafilm/live_input")(live_input)
