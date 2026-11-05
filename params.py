import dataclasses
import typing

from comfy_api.latest import io
from spektrafilm import digest_params, init_params
from spektrafilm_gui.param_manifest import ParamSpec

Params = io.Custom("SPEKTRAFILM_PARAMS")

CATEGORY = "image/spektrafilm"

RGB = ("r", "g", "b")
COMPONENTS = {
    "knee": ("threshold", "limit", "power"),
    "unsharp_mask": ("sigma", "amount"),
    "crop_center": ("x", "y"),
    "crop_size": ("x", "y"),
    "micro_structure": ("blur", "clump_nm"),
    "gamma_interlayer_r_to_gb": ("g", "b"),
    "gamma_interlayer_g_to_rb": ("r", "b"),
    "gamma_interlayer_b_to_rg": ("r", "g"),
}

CHANNEL_SWAPS = ("film_channel_swap", "print_channel_swap")
SWAP_ORDERS = ["0, 1, 2", "0, 2, 1", "1, 0, 2", "1, 2, 0", "2, 0, 1", "2, 1, 0"]

DEFAULTS = digest_params(init_params())


def gradient(*colors) -> list[dict]:
    return [{"offset": i / (len(colors) - 1), "color": list(c)} for i, c in enumerate(colors)]


NEUTRAL = (128, 128, 128)
YELLOW_BLUE = gradient((222, 190, 60), NEUTRAL, (70, 110, 230))
MAGENTA_GREEN = gradient((205, 80, 200), NEUTRAL, (80, 190, 90))
FILTER_SHIFTS = {"print_y_filter_shift": YELLOW_BLUE, "preflash_y_filter_shift": YELLOW_BLUE,
                 "print_m_filter_shift": MAGENTA_GREEN, "preflash_m_filter_shift": MAGENTA_GREEN}
GRADIENTS = {**FILTER_SHIFTS, "halo_warmth": gradient((90, 140, 230), NEUTRAL, (235, 150, 70))}
RANGES = {name: (-200, 200) for name in FILTER_SHIFTS}
NUMBER_FIELDS = {"exposure_compensation_ev"}


def read_path(obj, path: str):
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def write_path(obj, path: str, value):
    head, _, rest = path.partition(".")
    if rest:
        value = write_path(getattr(obj, head), rest, value)
    if obj.__dataclass_params__.frozen:
        return dataclasses.replace(obj, **{head: value})
    setattr(obj, head, value)
    return obj


def _hint(path: str):
    owner, _, leaf = path.rpartition(".")
    return typing.get_type_hints(type(read_path(DEFAULTS, owner)))[leaf]


def _number(kind, name, default, spec: ParamSpec, display_name, **kw):
    lo, hi = RANGES.get(spec.leaf, (spec.min, spec.max))
    if spec.leaf in GRADIENTS:
        kw.update(display_mode=io.NumberDisplay.gradient_slider, gradient_stops=GRADIENTS[spec.leaf])
    elif lo is not None and hi is not None and spec.leaf not in NUMBER_FIELDS:
        kw["display_mode"] = io.NumberDisplay.slider
    if kind is int:
        return io.Int.Input(name, default=default, min=int(lo if lo is not None else -10000),
                            max=int(hi if hi is not None else 10000), step=int(spec.step or 1),
                            display_name=display_name, **kw)
    return io.Float.Input(name, default=default, min=lo if lo is not None else -10000.0,
                          max=hi if hi is not None else 10000.0, step=spec.step or 0.01,
                          round=10 ** -spec.decimals if spec.decimals else None, display_name=display_name, **kw)


def label(spec: ParamSpec) -> str:
    text = spec.label or spec.leaf.replace("_", " ")
    return text[0].lower() + text[1:]


def spec_inputs(spec: ParamSpec, default=None, advanced=None) -> list:
    default = read_path(DEFAULTS, spec.path) if default is None else default
    kw = {"tooltip": spec.tooltip or None, "advanced": spec.tier != "basic" if advanced is None else advanced}
    if spec.enum is not None:
        return [io.Combo.Input(spec.leaf, options=[e.value for e in spec.enum], default=default,
                               display_name=label(spec), **kw)]
    hint = _hint(spec.path)
    if hint is bool:
        return [io.Boolean.Input(spec.leaf, default=default, display_name=label(spec), **kw)]
    if hint in (int, float):
        return [_number(hint, spec.leaf, default, spec, label(spec), **kw)]
    kinds = typing.get_args(hint)
    names = COMPONENTS.get(spec.leaf, RGB)
    if typing.get_origin(hint) is not tuple or len(kinds) != len(names):
        raise TypeError(f"no widget for {spec.path}: {hint}")
    return [_number(kind, f"{spec.leaf}_{name}", value, spec, f"{label(spec)} {name}", **kw)
            for kind, name, value in zip(kinds, names, default)]


def spec_value(spec: ParamSpec, values: dict):
    if spec.leaf in values:
        return values[spec.leaf]
    return tuple(values[f"{spec.leaf}_{name}"] for name in COMPONENTS.get(spec.leaf, RGB))


def build_params(film_stock: str, print_paper: str, overrides: dict):
    params = digest_params(init_params(film_profile=film_stock, print_profile=print_paper))
    params.io.scan_film = params.film.is_positive
    params.settings.use_enlarger_lut = True
    params.settings.use_scanner_lut = True
    for path, value in overrides.items():
        if path in CHANNEL_SWAPS:
            profile = params.film if path == "film_channel_swap" else params.print
            profile.data.channel_density = profile.data.channel_density[:, [int(c) for c in value.split(",")]]
        else:
            write_path(params, path, value)
    params.settings.use_fast_stats = False
    return digest_params(params, apply_stocks_specifics=False)
