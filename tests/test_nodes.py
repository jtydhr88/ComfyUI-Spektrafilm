import asyncio
import os
from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from PIL import Image

from comfy_api.latest import io
from comfyui_spektrafilm import live_preview, nodes_io, nodes_simulation, params
from spektrafilm.utils import raw_file_processor
from spektrafilm.utils.io import load_image_oiio
from spektrafilm_gui import param_manifest as pm

GROUP_NODES = nodes_simulation.PARAM_NODES


@pytest.fixture(autouse=True)
def hidden(monkeypatch):
    monkeypatch.setattr(nodes_simulation.SpektrafilmFilmSimulation, "hidden",
                        io.HiddenHolder(unique_id="7", prompt=None, extra_pnginfo=None, dynprompt=None,
                                        auth_token_comfy_org=None, api_key_comfy_org=None), raising=False)


def _defaults(node):
    return {i.id: getattr(i, "default", None) for i in node.define_schema().inputs if i.id != "params"}


def _simulate(image, **kw):
    node = nodes_simulation.SpektrafilmFilmSimulation
    values = _defaults(node)
    values.pop("image")
    values.update(preview=False, **kw)
    return node.execute(image=image, **values).result[0]


@pytest.fixture(scope="module")
def image():
    rng = np.random.default_rng(1)
    base = np.linspace(0.05, 0.95, 96)[None, :, None] * np.array([1.0, 0.8, 0.6])
    return torch.from_numpy(np.clip(base + rng.normal(0, 0.02, (64, 96, 3)), 0, 1).astype(np.float32))[None]


def test_schemas_have_unique_inputs():
    for node in nodes_simulation.NODES + nodes_io.NODES:
        ids = [i.id for i in node.define_schema().inputs]
        assert len(ids) == len(set(ids)), node


def test_every_gui_parameter_has_a_widget():
    covered = {s.path for s in nodes_simulation.MAIN_SPECS} | {"io.scan_film", "settings.preview_mode"}
    for node in GROUP_NODES.values():
        values = _defaults(node)
        if "override_stock_preset" in values:
            values["override_stock_preset"] = True
        covered |= set(node.execute(**values).result[0])
    gui = (pm.SIMULATION_EXPOSURE_PANEL_FIELDS + pm.SIMULATION_ENLARGER_PANEL_FIELDS + pm.SIMULATION_SPECIAL_BORROWED_FIELDS
           + pm.SIMULATION_FOOTER_FIELDS[1:] + pm.SIMULATION_OUTPUT_PANEL_FIELDS[:1] + pm.INPUT_IMAGE_FIELDS + pm.TUNE_PANEL_FIELDS
           + tuple(s for m in pm.ALL_MANIFESTS for s in m.fields))
    assert {s.path for s in gui} <= covered


def test_group_node_emits_its_paths():
    grain = GROUP_NODES["SpektrafilmGrain"]
    values = _defaults(grain)
    values["particle_area_um2"] = 0.8
    out = grain.execute(params={"camera.film_format_mm": 120.0}, **values).result[0]
    assert out["film_render.grain.particle_area_um2"] == 0.8
    assert out["film_render.grain.particle_scale"] == tuple(params.DEFAULTS.film_render.grain.particle_scale)
    assert out["camera.film_format_mm"] == 120.0


def test_stock_preset_is_kept_unless_overridden():
    couplers = GROUP_NODES["SpektrafilmCouplers"]
    out = couplers.execute(**_defaults(couplers)).result[0]
    assert "film_render.dir_couplers.gamma_samelayer_rgb" not in out
    assert "film_render.dir_couplers.amount" in out
    out = couplers.execute(**{**_defaults(couplers), "override_stock_preset": True}).result[0]
    assert "film_render.dir_couplers.gamma_samelayer_rgb" in out


def test_build_params_applies_stock_and_overrides():
    velvia = params.build_params("fujifilm_velvia_100", "kodak_portra_endura", {})
    assert velvia.io.scan_film
    assert velvia.film_render.dir_couplers.gamma_samelayer_rgb == (0.108, 0.072, 0.054)
    portra = params.build_params("kodak_portra_400", "kodak_portra_endura",
                                 {"film_render.grain.blur": 0.9, "film_channel_swap": "0, 2, 1"})
    reference = params.build_params("kodak_portra_400", "kodak_portra_endura", {})
    assert not portra.io.scan_film
    assert portra.film_render.grain.blur == 0.9
    assert np.array_equal(portra.film.data.channel_density, reference.film.data.channel_density[:, [0, 2, 1]], equal_nan=True)


def test_simulation_is_seeded(image):
    a = _simulate(image, seed=3)
    assert a.shape == image.shape and a.dtype == torch.float32
    assert 0.0 <= a.min() and a.max() <= 1.0
    assert torch.equal(a, _simulate(image, seed=3))
    assert not torch.equal(a, _simulate(image, seed=4))


def test_batch_frames_get_their_own_seed(image):
    out = _simulate(torch.cat([image, image]), seed=7)
    assert not torch.equal(out[0], out[1])
    assert torch.equal(out[1], _simulate(image, seed=8)[0])


def test_film_scan_differs_from_print(image):
    assert not torch.equal(_simulate(image, output="print"), _simulate(image, output="film scan"))


@pytest.mark.parametrize("fmt", ["tiff 16-bit", "tiff 32-bit float", "exr half", "png 8-bit"])
def test_save_then_load(folders, image, fmt):
    nodes_io.SpektrafilmSaveImage.execute(images=image, filename_prefix="t", format=fmt, image_color_space="sRGB",
                                          image_cctf_encoded=True, save_color_space="sRGB", save_cctf_encoding=True)
    (saved,) = os.listdir(folders / "output")
    loaded = load_image_oiio(str(folders / "output" / saved))
    assert np.allclose(loaded, image[0].numpy(), atol=1 / 255)


def test_save_converts_color_space(folders, image):
    nodes_io.SpektrafilmSaveImage.execute(images=image, filename_prefix="t", format="exr float", image_color_space="sRGB",
                                          image_cctf_encoded=True, save_color_space="sRGB", save_cctf_encoding=False)
    (saved,) = os.listdir(folders / "output")
    loaded = load_image_oiio(str(folders / "output" / saved))
    assert np.allclose(loaded, ((image[0].numpy() + 0.055) / 1.055) ** 2.4, atol=1e-3)


def test_load_raw(folders, monkeypatch):
    raw = np.full((4, 6, 3), 20000, dtype=np.uint16)

    class Reader:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def postprocess(self, **kwargs):
            return raw

    rawpy = {k: getattr(raw_file_processor.rawpy, k) for k in dir(raw_file_processor.rawpy) if not k.startswith("_")}
    monkeypatch.setattr(raw_file_processor, "rawpy", SimpleNamespace(**{**rawpy, "imread": lambda path: Reader()}))
    (folders / "input" / "shot.nef").write_bytes(b"raw")
    out = nodes_io.SpektrafilmLoadRaw.execute(raw_file="shot.nef", white_balance="as_shot", temperature=5500.0, tint=1.0,
                                              lens_correction=False, color_space="sRGB", cctf_encoding=True).result[0]
    assert out.shape == (1, 4, 6, 3) and out.dtype == torch.float32
    assert nodes_io.SpektrafilmLoadRaw.validate_inputs(raw_file="shot.nef") is True
    assert nodes_io.SpektrafilmLoadRaw.validate_inputs(raw_file="missing.nef") != True


def test_every_params_node_chains_into_a_run(image):
    chained = None
    for node in GROUP_NODES.values():
        values = _defaults(node)
        if "override_stock_preset" in values:
            values["override_stock_preset"] = True
        for key in ("active", "crop", "white_correction", "black_correction"):
            if key in values:
                values[key] = True
        chained = node.execute(params=chained, **values).result[0]
    node = nodes_simulation.SpektrafilmFilmSimulation
    values = _defaults(node)
    values.pop("image")
    out = node.execute(image=image, params=chained, **values).result[0]
    assert torch.isfinite(out).all() and out.shape[-1] == 3


def _request(body):
    async def json():
        return body
    return SimpleNamespace(json=json)


def test_live_preview_matches_a_real_run(image):
    grain = GROUP_NODES["SpektrafilmGrain"]
    grain_values = {**_defaults(grain), "particle_area_um2": 0.8}
    chain_params = grain.execute(**grain_values).result[0]
    real = _simulate(image, seed=5, params=chain_params)[0].numpy()
    assert nodes_simulation.LIVE_INPUTS["7"].shape == image.shape[1:]

    main = _defaults(nodes_simulation.SpektrafilmFilmSimulation)
    main.pop("image")
    main["seed"] = 5
    jpeg = live_preview.render_live(nodes_simulation.LIVE_INPUTS["7"], [{"type": "SpektrafilmGrain", "inputs": grain_values}], main, fast=False)
    live = np.asarray(Image.open(BytesIO(jpeg)), dtype=np.float32) / 255
    assert np.abs(live - real).mean() < 0.01


def test_live_preview_needs_a_run_first():
    response = asyncio.run(live_preview.live_preview(_request({"key": "missing", "chain": [], "main": {}})))
    assert response.status == 404


def test_live_preview_rejects_bad_requests(image):
    _simulate(image)
    response = asyncio.run(live_preview.live_preview(_request({"key": "7", "chain": [{"type": "Nope", "inputs": {}}], "main": {}})))
    assert response.status == 400
