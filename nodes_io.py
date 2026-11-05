import hashlib
import os

import colour
import numpy as np
import torch

import folder_paths
from comfy_api.latest import io, ui
from spektrafilm.utils.io import load_image_oiio, save_image_oiio, write_image_metadata
from spektrafilm.utils.raw_file_processor import load_and_process_raw_file
from spektrafilm_gui.options import RawWhiteBalance, RGBColorSpaces

from .params import CATEGORY, NEUTRAL, gradient

RAW_EXTENSIONS = (".3fr", ".ari", ".arw", ".bay", ".cr2", ".cr3", ".crw", ".dcr", ".dng", ".erf", ".fff", ".iiq",
                  ".k25", ".kdc", ".mef", ".mos", ".mrw", ".nef", ".nrw", ".orf", ".pef", ".raf", ".raw", ".rw2",
                  ".rwl", ".sr2", ".srf", ".srw", ".x3f")
IMAGE_EXTENSIONS = (".exr", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".hdr")
COLOR_SPACES = [c.value for c in RGBColorSpaces]
SAVE_FORMATS = {
    "tiff 16-bit": ("tif", 16),
    "tiff 32-bit float": ("tif", 32),
    "exr half": ("exr", 16),
    "exr float": ("exr", 32),
    "png 8-bit": ("png", 8),
    "jpeg": ("jpg", 8),
}


def _input_files(extensions: tuple) -> list[str]:
    input_dir = folder_paths.get_input_directory()
    os.makedirs(input_dir, exist_ok=True)
    return sorted(f for f in os.listdir(input_dir)
                  if f.lower().endswith(extensions) and os.path.isfile(os.path.join(input_dir, f)))


def _file_hash(name: str) -> str:
    m = hashlib.sha256()
    with open(folder_paths.get_annotated_filepath(name), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            m.update(chunk)
    return m.hexdigest()


def _check_file(name: str) -> bool | str:
    if not folder_paths.exists_annotated_filepath(name):
        return f"Invalid file: {name}"
    return True


class SpektrafilmLoadRaw(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SpektrafilmLoadRaw",
            display_name="Spektrafilm Load RAW",
            category=CATEGORY,
            description="Demosaic a camera RAW file into a float image (rawpy / LibRaw), with white balance and lensfun lens correction.",
            inputs=[
                io.Combo.Input("raw_file", display_name="raw file", options=_input_files(RAW_EXTENSIONS),
                               tooltip="RAW files in the ComfyUI input folder. Use the upload button to add one."),
                io.Combo.Input("white_balance", display_name="white balance", options=[w.value for w in RawWhiteBalance], default=RawWhiteBalance.as_shot.value),
                io.Float.Input("temperature", default=5500.0, min=2000.0, max=15000.0, step=50.0,
                               display_mode=io.NumberDisplay.gradient_slider, gradient_stops=gradient((80, 130, 235), (235, 235, 235), (240, 180, 60)),
                               tooltip="Color temperature in kelvin, used when white_balance is custom."),
                io.Float.Input("tint", default=1.0, min=0.5, max=1.5, step=0.01,
                               display_mode=io.NumberDisplay.gradient_slider, gradient_stops=gradient((205, 80, 200), NEUTRAL, (80, 190, 90)),
                               tooltip="Green multiplier, used when white_balance is custom."),
                io.Boolean.Input("lens_correction", display_name="lens correction", default=False,
                                 tooltip="Correct vignetting, chromatic aberration and distortion with lensfun, from the camera and lens in the EXIF data."),
                io.Combo.Input("color_space", display_name="color space", options=COLOR_SPACES, default=RGBColorSpaces.sRGB.value,
                               tooltip="Color space of the output image. Set the same input color space on Spektrafilm Film Simulation."),
                io.Boolean.Input("cctf_encoding", display_name="apply CCTF encoding", default=True,
                                 tooltip="Apply the color space transfer function. Set the same value as apply CCTF decoding on Spektrafilm Film Simulation. Values above 1 are kept."),
            ],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def execute(cls, raw_file, white_balance, temperature, tint, lens_correction, color_space, cctf_encoding) -> io.NodeOutput:
        image = load_and_process_raw_file(
            folder_paths.get_annotated_filepath(raw_file),
            white_balance=white_balance,
            temperature=temperature,
            tint=tint,
            lens_correction=lens_correction,
            output_colorspace=color_space,
            output_cctf_encoding=cctf_encoding,
        )
        return io.NodeOutput(torch.from_numpy(np.ascontiguousarray(image, dtype=np.float32))[None])

    @classmethod
    def fingerprint_inputs(cls, raw_file, **kwargs):
        return _file_hash(raw_file)

    @classmethod
    def validate_inputs(cls, raw_file, **kwargs):
        return _check_file(raw_file)


class SpektrafilmLoadImage(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SpektrafilmLoadImage",
            display_name="Spektrafilm Load Image (16/32-bit)",
            category=CATEGORY,
            description="Load an EXR, 16/32-bit TIFF or 16-bit PNG at full precision (OpenImageIO). Float values are kept as they are.",
            inputs=[
                io.Combo.Input("image", options=_input_files(IMAGE_EXTENSIONS),
                               tooltip="Images in the ComfyUI input folder. Use the upload button to add one."),
            ],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def execute(cls, image) -> io.NodeOutput:
        pixels = np.asarray(load_image_oiio(folder_paths.get_annotated_filepath(image)), dtype=np.float32)
        if pixels.shape[2] < 3:
            pixels = np.repeat(pixels[..., :1], 3, axis=2)
        return io.NodeOutput(torch.from_numpy(np.ascontiguousarray(pixels[..., :3]))[None])

    @classmethod
    def fingerprint_inputs(cls, image):
        return _file_hash(image)

    @classmethod
    def validate_inputs(cls, image):
        return _check_file(image)


class SpektrafilmSaveImage(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SpektrafilmSaveImage",
            display_name="Spektrafilm Save Image (16/32-bit)",
            category=CATEGORY,
            description="Save as 16-bit TIFF, float TIFF/EXR, PNG or JPEG with an embedded ICC profile, converting the color space if asked.",
            inputs=[
                io.Image.Input("images"),
                io.String.Input("filename_prefix", display_name="filename prefix", default="spektrafilm/ComfyUI"),
                io.Combo.Input("format", options=list(SAVE_FORMATS), default="tiff 16-bit"),
                io.Combo.Input("image_color_space", display_name="image color space", options=COLOR_SPACES, default=RGBColorSpaces.sRGB.value,
                               tooltip="Color space of the incoming image (the output color space of the simulation)."),
                io.Boolean.Input("image_cctf_encoded", display_name="image CCTF encoded", default=True,
                                 tooltip="Whether the incoming image carries the transfer function of its color space."),
                io.Combo.Input("save_color_space", display_name="save color space", options=COLOR_SPACES, default=RGBColorSpaces.sRGB.value),
                io.Boolean.Input("save_cctf_encoding", display_name="save CCTF encoding", default=True,
                                 tooltip="Apply the transfer function of the saved color space. Turn off to save linear values."),
            ],
            outputs=[],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, images, filename_prefix, format, image_color_space, image_cctf_encoded, save_color_space, save_cctf_encoding) -> io.NodeOutput:
        ext, bit_depth = SAVE_FORMATS[format]
        folder, filename, counter, _, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), images.shape[2], images.shape[1])
        for i, frame in enumerate(images.cpu().numpy().astype(np.float64)):
            if (image_color_space, image_cctf_encoded) != (save_color_space, save_cctf_encoding):
                frame = colour.RGB_to_RGB(frame, image_color_space, save_color_space,
                                          apply_cctf_decoding=image_cctf_encoded, apply_cctf_encoding=save_cctf_encoding)
            path = os.path.join(folder, f"{filename}_{counter + i:05}_.{ext}")
            save_image_oiio(path, frame, bit_depth=bit_depth, color_space=save_color_space, cctf_encoding=save_cctf_encoding)
            write_image_metadata(path, saving_color_space=save_color_space, saving_cctf_encoding=save_cctf_encoding)
        return io.NodeOutput(ui=ui.PreviewImage(images, cls=cls))


NODES = [SpektrafilmLoadRaw, SpektrafilmLoadImage, SpektrafilmSaveImage]
