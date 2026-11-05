import numpy as np
import torch

import comfy.model_management
import comfy.utils
from comfy_api.latest import io
from spektrafilm import Simulator
from spektrafilm.model.stocks import FilmStocks, PrintPapers
from spektrafilm_gui import param_manifest as pm
from spektrafilm_gui.options import RGBColorSpaces

from .params import CATEGORY, CHANNEL_SWAPS, SWAP_ORDERS, Params, ParamSpec, build_params, spec_inputs, spec_value

MAIN_SPECS = (
    pm.CAMERA_EXPOSURE_BORROWED_FIELDS
    + pm.SIMULATION_EXPOSURE_PANEL_FIELDS
    + pm.SIMULATION_ENLARGER_PANEL_FIELDS
    + pm.SIMULATION_SPECIAL_BORROWED_FIELDS
    + (ParamSpec("enlarger.lens_blur", name="enlarger_lens_blur", min=0, step=0.05,
                 tooltip="Sigma of gaussian filter in pixel for the enlarger lens blur."),)
    + pm.INPUT_PANEL_FIELDS
    + (pm.SIMULATION_OUTPUT_PANEL_FIELDS[0],
       ParamSpec("io.output_cctf_encoding", label="apply CCTF encoding", tier="basic",
                 tooltip="Apply the transfer function of the output color space. Turn off for linear output."))
)
MAIN_DEFAULTS = {"io.input_color_space": RGBColorSpaces.sRGB.value, "io.input_cctf_decoding": True}


class SpektrafilmFilmSimulation(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        inputs = [
            io.Image.Input("image"),
            io.Combo.Input("film_stock", display_name="film stock", options=[s.value for s in FilmStocks], default=FilmStocks.kodak_portra_400.value),
            io.Combo.Input("print_paper", display_name="print paper", options=[p.value for p in PrintPapers], default=PrintPapers.kodak_portra_endura.value),
            io.Combo.Input("output", options=["auto", "print", "film scan"], default="auto",
                           tooltip="print: enlarge the negative onto paper and scan the print. film scan: scan the film directly. auto: film scan for slide (positive) stocks, print otherwise."),
            io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFF, control_after_generate=True,
                         tooltip="Seed for film grain and print glare. Frame i of a batch uses seed + i."),
            io.Boolean.Input("preview", default=False,
                             tooltip="Skip grain and blurs for a fast look at color and exposure."),
        ]
        for spec in MAIN_SPECS:
            inputs += spec_inputs(spec, MAIN_DEFAULTS.get(spec.path))
        inputs.append(Params.Input("params", optional=True, tooltip="Settings from the other Spektrafilm nodes."))
        return io.Schema(
            node_id="SpektrafilmFilmSimulation",
            display_name="Spektrafilm Film Simulation",
            category=CATEGORY,
            description="Spectral simulation of a film negative, enlarger print and scan (spektrafilm).",
            inputs=inputs,
            outputs=[io.Image.Output()],
        )

    @classmethod
    def execute(cls, image, film_stock, print_paper, output, seed, preview, params=None, **values) -> io.NodeOutput:
        overrides = dict(params or {})
        overrides.update({spec.path: spec_value(spec, values) for spec in MAIN_SPECS})
        overrides["settings.preview_mode"] = preview
        if output != "auto":
            overrides["io.scan_film"] = output == "film scan"
        simulator = Simulator(build_params(film_stock, print_paper, overrides))

        pbar = comfy.utils.ProgressBar(len(image))
        frames = []
        state = np.random.get_state()
        try:
            for i, frame in enumerate(image):
                comfy.model_management.throw_exception_if_processing_interrupted()
                np.random.seed((seed + i) % 2**32)
                result = simulator.process(frame[..., :3].double().cpu().numpy())
                frames.append(torch.from_numpy(np.clip(result, 0.0, 1.0).astype(np.float32)))
                pbar.update(1)
        finally:
            np.random.set_state(state)
        return io.NodeOutput(torch.stack(frames))


def _group_node(node_id: str, display_name: str, description: str, specs: tuple, stock_preset: tuple = ()):
    class GroupNode(io.ComfyNode):
        @classmethod
        def define_schema(cls):
            inputs = [Params.Input("params", optional=True)]
            if stock_preset:
                inputs.append(io.Boolean.Input("override_stock_preset", display_name="override stock preset", default=False, advanced=True,
                                               tooltip=f"Use the values below for {', '.join(stock_preset)} instead of the ones spektrafilm picks for the chosen film stock."))
            for spec in specs:
                inputs += spec_inputs(spec)
            return io.Schema(node_id=node_id, display_name=display_name, category=f"{CATEGORY}/params",
                             description=description, inputs=inputs, outputs=[Params.Output()])

        @classmethod
        def execute(cls, params=None, override_stock_preset=False, **values) -> io.NodeOutput:
            overrides = dict(params or {})
            for spec in specs:
                if spec.leaf in stock_preset and not override_stock_preset:
                    continue
                overrides[spec.path] = spec_value(spec, values)
            return io.NodeOutput(overrides)

    GroupNode.__name__ = GroupNode.__qualname__ = node_id
    return GroupNode


class SpektrafilmFilmTune(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        inputs = [Params.Input("params", optional=True)]
        inputs += spec_inputs(pm.TUNE_PANEL_FIELDS[0])
        inputs += [io.Combo.Input(name, display_name=name.replace("_", " "), options=SWAP_ORDERS, default=SWAP_ORDERS[0], advanced=True,
                                  tooltip="Reorder the CMY density channels of the profile, for creative cross-channel looks.")
                   for name in CHANNEL_SWAPS]
        return io.Schema(node_id="SpektrafilmFilmTune", display_name="Spektrafilm Film Tune", category=f"{CATEGORY}/params",
                         description="Film contrast and channel swap.", inputs=inputs, outputs=[Params.Output()])

    @classmethod
    def execute(cls, film_gamma_factor, film_channel_swap, print_channel_swap, params=None) -> io.NodeOutput:
        overrides = dict(params or {})
        overrides[pm.TUNE_PANEL_FIELDS[0].path] = film_gamma_factor
        for name, order in ((CHANNEL_SWAPS[0], film_channel_swap), (CHANNEL_SWAPS[1], print_channel_swap)):
            if order != SWAP_ORDERS[0]:
                overrides[name] = order
        return io.NodeOutput(overrides)


LUT_SPECS = (
    ParamSpec("settings.use_enlarger_lut", tooltip="Precompute the enlarger stage as a 3D LUT. Much faster, very close to the exact result."),
    ParamSpec("settings.use_scanner_lut", tooltip="Precompute the scanner stage as a 3D LUT. Much faster, very close to the exact result."),
    ParamSpec("settings.lut_resolution", min=5, max=65, step=1, tooltip="Grid size of the enlarger and scanner LUTs."),
)

NODES = [
    SpektrafilmFilmSimulation,
    _group_node("SpektrafilmCamera", "Spektrafilm Camera", "Film format, lens blur and metering of the virtual camera.",
                pm.CAMERA_MANIFEST.panel_fields),
    _group_node("SpektrafilmCameraDiffusion", "Spektrafilm Camera Diffusion Filter", "Pro-Mist style diffusion filter on the camera lens.",
                pm.CAMERA_DIFFUSION_MANIFEST.fields),
    _group_node("SpektrafilmHalation", "Spektrafilm Halation", "In-emulsion scatter, halation and highlight boost.",
                pm.HALATION_MANIFEST.fields, ("halation_strength", "halation_first_sigma_um")),
    _group_node("SpektrafilmCouplers", "Spektrafilm DIR Couplers", "DIR coupler inhibition: saturation, contrast and local sharpness.",
                pm.DIR_COUPLERS_MANIFEST.fields,
                ("gamma_samelayer_rgb", "gamma_interlayer_r_to_gb", "gamma_interlayer_g_to_rb", "gamma_interlayer_b_to_rg")),
    _group_node("SpektrafilmGrain", "Spektrafilm Grain", "Stochastic film grain on the negative.",
                pm.GRAIN_MANIFEST.fields),
    SpektrafilmFilmTune,
    _group_node("SpektrafilmEnlargerDiffusion", "Spektrafilm Enlarger Diffusion Filter", "Diffusion filter on the enlarger lens.",
                pm.ENLARGER_DIFFUSION_MANIFEST.fields),
    _group_node("SpektrafilmPreflash", "Spektrafilm Preflash", "Preflash the print paper to keep highlight detail.",
                pm.PREFLASHING_MANIFEST.fields),
    _group_node("SpektrafilmPrintChemistry", "Spektrafilm Print Chemistry", "Morph the print density curves: contrast per sublayer and channel, developer exhaustion.",
                pm.CHEMISTRY_MANIFEST.fields),
    _group_node("SpektrafilmPrintGlare", "Spektrafilm Print Glare", "Surface glare of the print.",
                pm.GLARE_MANIFEST.fields),
    _group_node("SpektrafilmScanner", "Spektrafilm Scanner", "Scanner blur, sharpening and black/white points.",
                pm.SCANNER_MANIFEST.fields),
    _group_node("SpektrafilmCropUpscale", "Spektrafilm Crop & Upscale", "Crop or upscale before simulating, to see grain at full scale.",
                pm.CROP_PANEL_FIELDS),
    _group_node("SpektrafilmSpectral", "Spektrafilm Spectral Upsampling", "How RGB is turned into spectra, and the enlarger/scanner LUTs.",
                pm.SPECTRAL_PANEL_FIELDS + LUT_SPECS),
    _group_node("SpektrafilmInputGamut", "Spektrafilm Input Gamut Compress", "Compress input colors toward the visible locus before spectral upsampling.",
                pm.INPUT_GAMUT_COMPRESS_MANIFEST.fields),
    _group_node("SpektrafilmOutputGamut", "Spektrafilm Output Gamut Compress", "Compress output colors into the output color space.",
                pm.OUTPUT_GAMUT_COMPRESS_MANIFEST.fields),
]
