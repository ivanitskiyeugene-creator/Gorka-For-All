#!/usr/bin/env python3
"""Build one private Gorka recolor from the verified full-glove source.

The A variant recolors the Gorka upper and trousers plus the fabric portions of
both glove Base Color textures. Geometry, Normal/ORM maps, gear, the Basic outfit
Blueprint, and all other source payloads remain byte-identical. Broad dark
regions on the upper are brought to its main tone while fine fabric detail stays.

Run from the repository root with the local dependencies installed under
work/tools/pydeps (see requirements.txt):

  PYTHONPATH=work/tools/pydeps:. python tools/recolor_gorka_variants.py --preview-only
  PYTHONPATH=work/tools/pydeps:. python tools/recolor_gorka_variants.py

The input must be the verified Gorka3_For_All_Gloves_Texture_Test.zip and its
IoStore payloads extracted to work/gorka-source/full/ITR2_Gorka3/Content.
Generated release archives are written under the ignored release/ directory.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import ispc_texcomp
import texture2ddecoder

from tools.build_gorka_mod import (
    MOUNT_POINT,
    MOD_BASENAME,
    SourceFile,
    validate_container,
    write_deterministic_zip,
)
from tools.iostore_extract import sha256_file
from tools.iostore_write import (
    BULK_DATA_CHUNK_TYPE,
    EXPORT_BUNDLE_CHUNK_TYPE,
    Chunk,
    PackageStoreInfo,
    container_id_from_name,
    make_chunk_id,
    write_container,
)
from tools.zen_asset import parse_package


SOURCE_ZIP = Path("google_drive/Gorka3_For_All_Gloves_Texture_Test.zip")
SOURCE_ROOT = Path("work/gorka-source")
CONTENT_ROOT = SOURCE_ROOT / "full/ITR2_Gorka3/Content"
PREVIEW_ROOT = SOURCE_ROOT / "previews/recolored"
OUTPUT_ROOT = Path("release/gorka-brown")
ZIP_ROOT = Path("release")
SOURCE_BASENAME = "Gorka3_For_All_P"

# The Gorka body atlas is 2048 square, except the LOD atlas at 1024.
# Keep the recolor list explicit: no boots, balaclava, detector, or Normal/ORM map.
GORKA_TEXTURE_DIR = Path("ITR2/Art/Characters/Player/Body/Body_Gorka_01/Textures")
GORKA_BASECOLOR_TEXTURES: dict[str, dict[str, int | str | bool]] = {
    "T_Gorka_Body_01_C": {"dimension": 2048, "role": "upper", "dark_lift": True},
    "T_Gorka_Arms_01_C": {"dimension": 2048, "role": "upper", "dark_lift": True},
    "T_Gorka_Pants_01_C": {"dimension": 2048, "role": "pants", "dark_lift": True},
    "T_Gorka_Set_01_C": {"dimension": 2048, "role": "upper", "dark_lift": True},
    "T_Gorka_LODX_01_C": {"dimension": 1024, "role": "upper", "dark_lift": True},
}
GLOVE_TEXTURE_DIR = Path("ITR2/Art/Characters/Player/Hand/Hand_ITR1/Textures")
GLOVE_BASECOLOR_TEXTURES: dict[str, int] = {
    "T_Character_Gloves_01_c": 2048,
    "T_Character_Gloves_01_c_right": 2048,
}

TARGET_UPPER_RGB = (0x63, 0x51, 0x3A)  # #63513A from screenshot bright patch (was #634F3C)
TARGET_PANTS_RGB = (0x80, 0x65, 0x46)  # #806546 keep as pants not visible in screenshot
TARGET_GLOVES_RGB = (0x23, 0x29, 0x28)  # #232928 from screenshot glove_palm (was #323831)
GLOVE_REGION_START_FRACTION = 0.5
A_DARK_LIFT_STRENGTH = 1.0
A_DARK_LIFT_CUTOFF = 0.005
A_DARK_LIFT_CAP = 0.50
GAUSSIAN_RADIUS_AT_2048 = 20.0

VARIANTS = {
    "Khaki_A": {
        "title": "Khaki_A — верх #634F3C, штаны #806546, перчатки #323831",
        "zip_name": "Gorka3_For_All_Khaki_A.zip",
    },
    "Khaki_V2": {
        "title": "Khaki_V2 — верх #63513A, штаны #806546, перчатки #232928 (точный оттенок со скрина)",
        "zip_name": "Gorka3_For_All_Khaki_V2.zip",
    },
}


def rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert float RGB (0..1, sRGB-encoded) to HSV arrays."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maximum = np.max(rgb, axis=-1)
    minimum = np.min(rgb, axis=-1)
    delta = maximum - minimum

    hue6 = np.zeros_like(maximum, dtype=np.float32)
    safe_delta = np.where(delta > 1e-8, delta, 1.0)
    is_chromatic = delta > 1e-8

    select = is_chromatic & (maximum == r)
    hue6[select] = ((g[select] - b[select]) / safe_delta[select]) % 6.0
    select = is_chromatic & (maximum == g)
    hue6[select] = (b[select] - r[select]) / safe_delta[select] + 2.0
    select = is_chromatic & (maximum == b)
    hue6[select] = (r[select] - g[select]) / safe_delta[select] + 4.0

    hue = (hue6 * 60.0) % 360.0
    saturation = np.divide(
        delta,
        maximum,
        out=np.zeros_like(maximum, dtype=np.float32),
        where=maximum > 1e-8,
    )
    return hue, saturation, maximum


def target_rgb_to_hsv(color: tuple[int, int, int]) -> tuple[float, float, float]:
    sample = np.asarray(color, dtype=np.float32).reshape(1, 1, 3) / 255.0
    hue, saturation, value = rgb_to_hsv(sample)
    return float(hue[0, 0]), float(saturation[0, 0]), float(value[0, 0])


def rgb_hex(color: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in color)


TARGET_UPPER_HUE, TARGET_UPPER_SATURATION, TARGET_UPPER_VALUE = target_rgb_to_hsv(TARGET_UPPER_RGB)
TARGET_PANTS_HUE, TARGET_PANTS_SATURATION, TARGET_PANTS_VALUE = target_rgb_to_hsv(TARGET_PANTS_RGB)
TARGET_GLOVES_HUE, TARGET_GLOVES_SATURATION, TARGET_GLOVES_VALUE = target_rgb_to_hsv(TARGET_GLOVES_RGB)


def hsv_to_rgb(hue: np.ndarray, saturation: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Convert float HSV arrays to float RGB (0..1, sRGB-encoded)."""
    h6 = (hue % 360.0) / 60.0
    chroma = value * saturation
    x = chroma * (1.0 - np.abs((h6 % 2.0) - 1.0))
    zero = np.zeros_like(value)
    sector = np.empty((*value.shape, 3), dtype=np.float32)
    sector0 = (h6 < 1.0)
    sector1 = (h6 >= 1.0) & (h6 < 2.0)
    sector2 = (h6 >= 2.0) & (h6 < 3.0)
    sector3 = (h6 >= 3.0) & (h6 < 4.0)
    sector4 = (h6 >= 4.0) & (h6 < 5.0)
    sector5 = h6 >= 5.0
    sector[sector0] = np.stack((chroma[sector0], x[sector0], zero[sector0]), axis=-1)
    sector[sector1] = np.stack((x[sector1], chroma[sector1], zero[sector1]), axis=-1)
    sector[sector2] = np.stack((zero[sector2], chroma[sector2], x[sector2]), axis=-1)
    sector[sector3] = np.stack((zero[sector3], x[sector3], chroma[sector3]), axis=-1)
    sector[sector4] = np.stack((x[sector4], zero[sector4], chroma[sector4]), axis=-1)
    sector[sector5] = np.stack((chroma[sector5], zero[sector5], x[sector5]), axis=-1)
    match = value - chroma
    return np.clip(sector + match[..., None], 0.0, 1.0)


def bc1_mip_size(width: int, height: int) -> int:
    """Return the encoded BC1 size, including the minimum 4x4 block for tiny mips."""
    return ((width + 3) // 4) * ((height + 3) // 4) * 8


def decoded_bc1_rgba(data: bytes, width: int, height: int) -> np.ndarray:
    """Decode a BC1/DFXT1 mip to RGBA uint8; decoder returns BGRA."""
    expected = bc1_mip_size(width, height)
    if len(data) != expected:
        raise ValueError(f"BC1 byte count mismatch for {width}x{height}: {len(data)} != {expected}")
    bgra = np.frombuffer(texture2ddecoder.decode_bc1(data, width, height), dtype=np.uint8)
    if bgra.size != width * height * 4:
        raise ValueError(f"BC1 decoder returned {bgra.size} bytes for {width}x{height}")
    bgra = bgra.reshape(height, width, 4)
    return bgra[..., (2, 1, 0, 3)].copy()


def mask_for_olive_fabric(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hue, saturation, value = rgb_to_hsv(rgb)
    # The source Gorka cloth is a low-saturation olive. This deliberately
    # excludes the black background and brown/neutral islands in the LOD atlas.
    mask = (
        (hue >= 35.0)
        & (hue <= 105.0)
        & (saturation >= 0.07)
        & (value >= 0.06)
    )
    return mask, hue, saturation


def masked_gaussian_mean(
    value: np.ndarray,
    mask: np.ndarray,
    radius: float,
) -> np.ndarray:
    """Blur a scalar field without letting non-fabric texels bleed into it."""
    value_u8 = np.zeros(value.shape, dtype=np.uint8)
    value_u8[mask] = np.rint(np.clip(value[mask], 0.0, 1.0) * 255.0).astype(np.uint8)
    mask_u8 = mask.astype(np.uint8) * 255
    blurred_value = np.asarray(
        Image.fromarray(value_u8, mode="L").filter(ImageFilter.GaussianBlur(radius=radius)),
        dtype=np.float32,
    )
    blurred_mask = np.asarray(
        Image.fromarray(mask_u8, mode="L").filter(ImageFilter.GaussianBlur(radius=radius)),
        dtype=np.float32,
    )
    valid_support = blurred_mask >= 8.0
    result = np.divide(
        blurred_value,
        blurred_mask,
        out=value.astype(np.float32, copy=True),
        where=valid_support,
    )
    return np.clip(result, 0.0, 1.0)


def compress_bc1_preserving_unmodified_blocks(
    rgba: np.ndarray,
    original_bc1: bytes,
    mask: np.ndarray,
) -> tuple[bytes, dict[str, float | int]]:
    height, width, channels = rgba.shape
    if channels != 4 or mask.shape != (height, width):
        raise ValueError(f"BC1 input must be matching RGBA/mask arrays: {rgba.shape}, {mask.shape}")
    expected_size = bc1_mip_size(width, height)
    if len(original_bc1) != expected_size:
        raise ValueError(f"Original BC1 size mismatch: {len(original_bc1)} != {expected_size}")

    blocks_w = (width + 3) // 4
    blocks_h = (height + 3) // 4
    padded_width, padded_height = blocks_w * 4, blocks_h * 4
    pad_x, pad_y = padded_width - width, padded_height - height
    padded_rgba = np.pad(rgba, ((0, pad_y), (0, pad_x), (0, 0)), mode="edge")
    padded_mask = np.pad(mask, ((0, pad_y), (0, pad_x)), mode="edge")
    padded_size = padded_width * padded_height // 2

    surface = ispc_texcomp.RGBASurface(padded_rgba.tobytes(), padded_width, padded_height)
    encoded_with_padding = ispc_texcomp.compress_blocks_bc1(surface)
    if len(encoded_with_padding) < padded_size:
        raise ValueError(f"BC1 compressor returned too few bytes: {len(encoded_with_padding)}")
    encoded = np.frombuffer(encoded_with_padding[:padded_size], dtype=np.uint8).copy()
    original = np.frombuffer(original_bc1, dtype=np.uint8)
    encoded_blocks = encoded.reshape(blocks_h, blocks_w, 8)
    original_blocks = original.reshape(blocks_h, blocks_w, 8)
    touched_blocks = padded_mask.reshape(blocks_h, 4, blocks_w, 4).any(axis=(1, 3))
    encoded_blocks[~touched_blocks] = original_blocks[~touched_blocks]
    result = encoded_blocks.tobytes()

    final_rgba = decoded_bc1_rgba(result, width, height)
    final_rgb = final_rgba[..., :3].astype(np.int16)
    intended_rgb = rgba[..., :3].astype(np.int16)
    pixel_error = np.abs(final_rgb - intended_rgb).astype(np.float32)
    untouched_pixels = np.repeat(np.repeat(~touched_blocks, 4, axis=0), 4, axis=1)[:height, :width]
    original_rgba = decoded_bc1_rgba(original_bc1, width, height)
    if not np.array_equal(final_rgba[untouched_pixels], original_rgba[untouched_pixels]):
        raise AssertionError("BC1 blocks outside the recolor mask were not preserved byte-identically")

    non_mask_touched = ~mask & ~untouched_pixels
    target_rms = float(np.sqrt(np.mean(pixel_error[mask] ** 2))) if mask.any() else 0.0
    adjacent_rms = (
        float(np.sqrt(np.mean(pixel_error[non_mask_touched] ** 2)))
        if non_mask_touched.any()
        else 0.0
    )
    return result, {
        "touched_block_count": int(touched_blocks.sum()),
        "untouched_block_count": int((~touched_blocks).sum()),
        "total_block_count": int(blocks_w * blocks_h),
        "target_pixel_encode_rms_8bit": round(target_rms, 4),
        "non_target_pixels_in_touched_blocks_rms_8bit": round(adjacent_rms, 4),
    }


def transform_mip(
    source_bc1: bytes,
    width: int,
    height: int,
    *,
    texture_name: str,
    role: str,
    target_rgb: tuple[int, int, int],
    dark_lift: bool,
) -> tuple[bytes, Image.Image, dict]:
    decoded = decoded_bc1_rgba(source_bc1, width, height)
    original_rgb = decoded[..., :3].astype(np.float32) / 255.0
    mask, source_hue, source_saturation = mask_for_olive_fabric(original_rgb)
    coverage = float(mask.mean())
    if texture_name != "T_Gorka_LODX_01_C" and coverage < 0.90:
        raise ValueError(f"Unexpected fabric mask coverage for {texture_name}: {coverage:.1%}")
    if texture_name == "T_Gorka_LODX_01_C" and coverage < 0.40:
        raise ValueError(f"LOD atlas fabric mask is unexpectedly small: {coverage:.1%}")
    if not mask.any():
        raise ValueError(f"No fabric pixels found in {texture_name}")

    target_hue, target_saturation, target_value = target_rgb_to_hsv(target_rgb)
    value = original_rgb.max(axis=-1)
    reference_value = float(np.percentile(value[mask], 90))
    radius = max(0.75, GAUSSIAN_RADIUS_AT_2048 * width / 2048.0)
    low_frequency = masked_gaussian_mean(value, mask, radius) if dark_lift else value.copy()
    out_hue = np.full(value.shape, target_hue, dtype=np.float32)
    out_saturation = np.full(value.shape, target_saturation, dtype=np.float32)

    if dark_lift:
        # Equalize broad dark fields while retaining fine texture detail.
        delta = np.maximum(reference_value - low_frequency - A_DARK_LIFT_CUTOFF, 0.0)
        delta = np.minimum(delta * A_DARK_LIFT_STRENGTH, A_DARK_LIFT_CAP)
        equalized_value = np.minimum(value + delta, 1.0)
        adjusted_value = np.clip(equalized_value * (target_value / reference_value), 0.0, 1.0)
        lift_summary = {
            "large_dark_regions_equalized": True,
            "mean_value_lift": round(float(delta[mask].mean()), 6),
            "max_value_lift": round(float(delta[mask].max()), 6),
            "gaussian_radius_pixels": round(radius, 3),
            "target_low_frequency_contrast_residual": A_DARK_LIFT_CUTOFF,
        }
    else:
        # The target hue/value is applied across the whole pants fabric while
        # the source luminance detail and folds remain visible.
        adjusted_value = np.clip(value * (target_value / reference_value), 0.0, 1.0)
        lift_summary = {
            "large_dark_regions_equalized": False,
            "mean_value_lift": 0.0,
            "gaussian_radius_pixels": round(radius, 3),
        }

    recolored_rgb = hsv_to_rgb(out_hue, out_saturation, adjusted_value)
    out = decoded.copy()
    recolored_u8 = np.rint(recolored_rgb * 255.0).clip(0, 255).astype(np.uint8)
    out[..., :3][mask] = recolored_u8[mask]

    compressed, block_report = compress_bc1_preserving_unmodified_blocks(out, source_bc1, mask)
    final_rgba = decoded_bc1_rgba(compressed, width, height)
    final_rgb = final_rgba[..., :3].astype(np.float32) / 255.0
    final_hue, final_saturation, final_value = rgb_to_hsv(final_rgb)
    report = {
        "dimensions": [width, height],
        "role": role,
        "fabric_mask_coverage": round(coverage, 6),
        "target_rgb": rgb_hex(target_rgb),
        "source_hue_median_degrees": round(float(np.median(source_hue[mask])), 3),
        "source_hsv_saturation_median": round(float(np.median(source_saturation[mask])), 4),
        "source_value_median": round(float(np.median(value[mask])), 6),
        "result_rgb_median": [
            int(round(float(np.median(final_rgb[..., channel][mask])) * 255.0))
            for channel in range(3)
        ],
        "result_hue_median_degrees": round(float(np.median(final_hue[mask])), 3),
        "result_saturation_median": round(float(np.median(final_saturation[mask])), 4),
        "result_value_median": round(float(np.median(final_value[mask])), 6),
        "reference_value": round(reference_value, 6),
        **lift_summary,
        **block_report,
    }
    image = Image.fromarray(final_rgba, mode="RGBA")
    return compressed, image, report


def glove_fabric_mask(rgb: np.ndarray) -> np.ndarray:
    """Select the dark glove fabric islands in the lower half of its UV atlas.

    The upper half contains a wrist display, leather, and straps and must stay
    untouched. For mip levels below 64 px, the color filter is unstable, so the
    lower UV half is used as the deterministic glove region instead.
    """
    hue, saturation, value = rgb_to_hsv(rgb)
    height, width = value.shape
    y = np.arange(height)[:, None]
    spatial = y >= int(np.ceil(height * GLOVE_REGION_START_FRACTION))
    if height >= 64:
        material = (
            (hue >= 25.0)
            & (hue <= 85.0)
            & (saturation >= 0.04)
            & (saturation <= 0.35)
            & (value >= 0.04)
            & (value <= 0.40)
        )
    else:
        material = value >= 0.02
    return spatial & material


def transform_glove_mip(
    source_bc1: bytes,
    width: int,
    height: int,
) -> tuple[bytes, Image.Image, dict]:
    decoded = decoded_bc1_rgba(source_bc1, width, height)
    original_rgb = decoded[..., :3].astype(np.float32) / 255.0
    source_hue, source_saturation, value = rgb_to_hsv(original_rgb)
    mask = glove_fabric_mask(original_rgb)
    if mask.any():
        reference_value = float(np.median(value[mask]))
        target_hue, target_saturation, target_value = target_rgb_to_hsv(TARGET_GLOVES_RGB)
        adjusted_value = np.clip(value * (target_value / max(reference_value, 1e-6)), 0.0, 1.0)
        recolored_rgb = hsv_to_rgb(
            np.full(value.shape, target_hue, dtype=np.float32),
            np.full(value.shape, target_saturation, dtype=np.float32),
            adjusted_value,
        )
        out = decoded.copy()
        out[..., :3][mask] = np.rint(recolored_rgb[mask] * 255.0).clip(0, 255).astype(np.uint8)
    else:
        reference_value = 0.0
        out = decoded.copy()

    compressed, block_report = compress_bc1_preserving_unmodified_blocks(out, source_bc1, mask)
    final_rgba = decoded_bc1_rgba(compressed, width, height)
    final_rgb = final_rgba[..., :3].astype(np.float32) / 255.0
    final_hue, final_saturation, final_value = rgb_to_hsv(final_rgb)
    report = {
        "dimensions": [width, height],
        "role": "glove_fabric_lower_uv_half",
        "glove_fabric_mask_coverage": round(float(mask.mean()), 6),
        "target_rgb": rgb_hex(TARGET_GLOVES_RGB),
        "source_hue_median_degrees": round(float(np.median(source_hue[mask])), 3) if mask.any() else None,
        "source_saturation_median": round(float(np.median(source_saturation[mask])), 4) if mask.any() else None,
        "source_value_median": round(float(np.median(value[mask])), 6) if mask.any() else None,
        "result_rgb_median": [
            int(round(float(np.median(final_rgb[..., channel][mask])) * 255.0))
            for channel in range(3)
        ] if mask.any() else None,
        "result_hue_median_degrees": round(float(np.median(final_hue[mask])), 3) if mask.any() else None,
        "result_saturation_median": round(float(np.median(final_saturation[mask])), 4) if mask.any() else None,
        "reference_value": round(reference_value, 6),
        **block_report,
    }
    return compressed, Image.fromarray(final_rgba, mode="RGBA"), report


def texture_external_mips(
    content_root: Path,
    texture_name: str,
    base_dimension: int,
    relative_dir: Path = GORKA_TEXTURE_DIR,
) -> tuple[Path, Path, list[int]]:
    uasset_path = content_root / relative_dir / f"{texture_name}.uasset"
    ubulk_path = content_root / relative_dir / f"{texture_name}.ubulk"
    if not uasset_path.is_file() or not ubulk_path.is_file():
        raise FileNotFoundError(f"Missing cooked texture pair for {texture_name}")
    package = parse_package(uasset_path.read_bytes())
    if "PF_DXT1" not in package.names:
        raise ValueError(f"{texture_name} is not the expected PF_DXT1/BC1 texture")
    external = [entry for entry in package.bulk_data if entry["flags"] & 0x10000]
    sizes = [entry["serial_size"] for entry in external]
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError(f"No external mip bulk data found for {texture_name}")
    offsets = [entry["serial_offset"] for entry in external]
    expected_offsets = []
    offset = 0
    for size in sizes:
        expected_offsets.append(offset)
        offset += size
    if offsets != expected_offsets or offset != ubulk_path.stat().st_size:
        raise ValueError(f"Unexpected external mip layout for {texture_name}: offsets={offsets}, sizes={sizes}")

    dimension = base_dimension
    expected_sizes: list[int] = []
    for _ in sizes:
        expected_sizes.append(bc1_mip_size(dimension, dimension))
        dimension //= 2
    if sizes != expected_sizes:
        raise ValueError(f"Unexpected {texture_name} BC1 mip sizes: {sizes} != {expected_sizes}")
    return uasset_path, ubulk_path, sizes


def recolor_texture(
    content_root: Path,
    texture_name: str,
    base_dimension: int,
    *,
    role: str,
    target_rgb: tuple[int, int, int],
    dark_lift: bool,
    preview_path: Path,
) -> tuple[bytes, dict]:
    uasset_path, ubulk_path, mip_sizes = texture_external_mips(content_root, texture_name, base_dimension)
    source_data = ubulk_path.read_bytes()
    output_mips: list[bytes] = []
    mip_reports: list[dict] = []
    preview_image: Image.Image | None = None
    offset = 0
    dimension = base_dimension
    for mip_index, size in enumerate(mip_sizes):
        source_mip = source_data[offset:offset + size]
        output_mip, image, report = transform_mip(
            source_mip,
            dimension,
            dimension,
            texture_name=texture_name,
            role=role,
            target_rgb=target_rgb,
            dark_lift=dark_lift,
        )
        if len(output_mip) != size:
            raise AssertionError(f"Re-encoded mip changed size for {texture_name}, mip {mip_index}")
        output_mips.append(output_mip)
        report["mip_index"] = mip_index
        mip_reports.append(report)
        if mip_index == 0:
            preview_image = image
        offset += size
        dimension //= 2
    if offset != len(source_data):
        raise AssertionError(f"Not all external mip bytes were processed for {texture_name}")
    if preview_image is None:
        raise AssertionError(f"No preview generated for {texture_name}")
    result_data = b"".join(output_mips)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_image.save(preview_path)
    return result_data, {
        "uasset_sha256_unchanged": sha256_file(uasset_path),
        "source_ubulk_sha256": hashlib.sha256(source_data).hexdigest(),
        "result_ubulk_sha256": hashlib.sha256(result_data).hexdigest(),
        "uasset_bytes_unchanged": True,
        "mip_count": len(mip_sizes),
        "mip_reports": mip_reports,
        "preview": str(preview_path),
    }


def recolor_glove_texture(
    content_root: Path,
    texture_name: str,
    base_dimension: int,
    *,
    preview_path: Path,
) -> tuple[bytes, bytes, dict]:
    uasset_path, ubulk_path, external_sizes = texture_external_mips(
        content_root,
        texture_name,
        base_dimension,
        GLOVE_TEXTURE_DIR,
    )
    source_uasset = uasset_path.read_bytes()
    source_ubulk = ubulk_path.read_bytes()
    package = parse_package(source_uasset)
    external_entries = [entry for entry in package.bulk_data if entry["flags"] & 0x10000]
    inline_entries = [
        entry for entry in package.bulk_data
        if not (entry["flags"] & 0x10000) and entry["serial_size"] > 0
    ]
    inline_dimensions = [64, 32, 16, 8, 4, 2, 1]
    expected_inline_sizes = [bc1_mip_size(dim, dim) for dim in inline_dimensions]
    if len(inline_entries) != len(inline_dimensions):
        raise ValueError(f"Unexpected inline mip count for {texture_name}: {len(inline_entries)}")
    if [entry["serial_size"] for entry in inline_entries] != expected_inline_sizes:
        raise ValueError(f"Unexpected inline BC1 mip sizes for {texture_name}")
    header_size = package.summary["header_size"]
    cooked_offset = package.exports[0]["cooked_serial_offset"] if package.exports else 0
    inline_base = header_size + cooked_offset
    for entry in inline_entries:
        start = inline_base + entry["serial_offset"]
        end = start + entry["serial_size"]
        if start < 0 or end > len(source_uasset):
            raise ValueError(f"Inline mip range is outside {texture_name}.uasset: {start}:{end}")

    output_ubulk = bytearray(source_ubulk)
    output_uasset = bytearray(source_uasset)
    mip_reports: list[dict] = []
    preview_image: Image.Image | None = None

    offset = 0
    dimension = base_dimension
    for mip_index, (entry, size) in enumerate(zip(external_entries, external_sizes)):
        source_mip = source_ubulk[offset:offset + size]
        result_mip, image, report = transform_glove_mip(source_mip, dimension, dimension)
        if len(result_mip) != size:
            raise AssertionError(f"Re-encoded external glove mip size changed for {texture_name}, mip {mip_index}")
        output_ubulk[offset:offset + size] = result_mip
        report["mip_index"] = mip_index
        report["storage"] = "ubulk"
        mip_reports.append(report)
        if mip_index == 0:
            preview_image = image
        offset += size
        dimension //= 2
    if offset != len(source_ubulk):
        raise AssertionError(f"Not all external glove mip bytes were processed for {texture_name}")

    for local_index, (entry, dimension) in enumerate(zip(inline_entries, inline_dimensions)):
        start = inline_base + entry["serial_offset"]
        end = start + entry["serial_size"]
        source_mip = bytes(output_uasset[start:end])
        result_mip, image, report = transform_glove_mip(source_mip, dimension, dimension)
        if len(result_mip) != entry["serial_size"]:
            raise AssertionError(f"Re-encoded inline glove mip size changed for {texture_name}, mip {dimension}")
        output_uasset[start:end] = result_mip
        report["mip_index"] = len(external_sizes) + local_index
        report["storage"] = "uasset_inline_bulk"
        mip_reports.append(report)

    if preview_image is None:
        raise AssertionError(f"No external glove preview generated for {texture_name}")
    parsed_result = parse_package(bytes(output_uasset))
    if parsed_result.bulk_data != package.bulk_data or parsed_result.names != package.names:
        raise AssertionError(f"Changing inline mips altered {texture_name} package metadata")
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_image.save(preview_path)
    result_uasset = bytes(output_uasset)
    result_ubulk = bytes(output_ubulk)
    return result_uasset, result_ubulk, {
        "source_uasset_sha256": hashlib.sha256(source_uasset).hexdigest(),
        "result_uasset_sha256": hashlib.sha256(result_uasset).hexdigest(),
        "source_ubulk_sha256": hashlib.sha256(source_ubulk).hexdigest(),
        "result_ubulk_sha256": hashlib.sha256(result_ubulk).hexdigest(),
        "external_mip_count": len(external_sizes),
        "inline_mip_count": len(inline_entries),
        "mip_count": len(mip_reports),
        "mip_reports": mip_reports,
        "preview": str(preview_path),
    }


def collect_source_payloads(content_root: Path, source_manifest: dict) -> tuple[list[SourceFile], list[PackageStoreInfo]]:
    if not content_root.is_dir():
        raise FileNotFoundError(f"Extracted source Content directory does not exist: {content_root}")
    packages_by_stem = {}
    packages_store: list[PackageStoreInfo] = []
    for path in sorted(content_root.rglob("*.uasset")):
        package = parse_package(path.read_bytes())
        rel = path.relative_to(content_root).as_posix()
        stem = rel[:-len(".uasset")]
        packages_by_stem[stem] = package
        packages_store.append(PackageStoreInfo(package.package_name, list(package.imported_package_names)))

    files: list[SourceFile] = []
    hashes: dict[str, str] = {}
    for path in sorted(content_root.rglob("*")):
        if not path.is_file() or path.suffix not in (".uasset", ".ubulk"):
            continue
        rel = path.relative_to(content_root).as_posix()
        stem = rel[:-len(path.suffix)]
        package = packages_by_stem.get(stem)
        if package is None:
            raise ValueError(f"No matching .uasset for {rel}")
        data = path.read_bytes()
        hashes[rel] = hashlib.sha256(data).hexdigest()
        files.append(SourceFile(
            relative_path=rel,
            package_name=package.package_name,
            chunk_type=EXPORT_BUNDLE_CHUNK_TYPE if path.suffix == ".uasset" else BULK_DATA_CHUNK_TYPE,
            data=data,
        ))

    expected = dict(source_manifest.get("original_visual_sha256", {}))
    basic_rel = "ITR2/BPs/Items/Outfits/BP_OutfitExplorerBasic.uasset"
    basic_hash = source_manifest.get("basic_patch", {}).get("patched_sha256")
    if not basic_hash:
        raise ValueError("Source build manifest has no patched Basic hash")
    expected[basic_rel] = basic_hash
    if hashes != expected:
        missing = sorted(set(expected) - set(hashes))
        extra = sorted(set(hashes) - set(expected))
        changed = sorted(path for path in set(hashes) & set(expected) if hashes[path] != expected[path])
        raise ValueError(f"Extracted payloads do not match source manifest: missing={missing}, extra={extra}, changed={changed}")
    if len(files) != 53 or len(packages_store) != 27:
        raise ValueError(f"Unexpected latest source asset counts: files={len(files)}, packages={len(packages_store)}")
    if not any(item.relative_path == basic_rel for item in files):
        raise ValueError("Latest source build has no BP_OutfitExplorerBasic replacement")
    return files, packages_store


def source_metadata(source_zip: Path, source_root: Path) -> tuple[dict, bytes]:
    if not source_zip.is_file():
        raise FileNotFoundError(f"Verified source ZIP not found: {source_zip}")
    source_utoc = source_root / f"{SOURCE_BASENAME}.utoc"
    source_ucas = source_root / f"{SOURCE_BASENAME}.ucas"
    manifest_path = source_root / "build-manifest.json"
    if not source_utoc.is_file() or not source_ucas.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Source .utoc, .ucas, or build-manifest.json is missing from work/gorka-source")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key, path in (("utoc_sha256", source_utoc), ("ucas_sha256", source_ucas)):
        actual = sha256_file(path)
        if actual != manifest.get(key):
            raise ValueError(f"Source container does not match its manifest: {key} {actual}")
    expected_container_id = int(manifest["container_id"], 16)
    if expected_container_id != container_id_from_name(SOURCE_BASENAME):
        raise ValueError("Source container ID does not match its basename")

    with zipfile.ZipFile(source_zip) as archive:
        names = set(archive.namelist())
        for required in (
            f"{SOURCE_BASENAME}.pak",
            f"{SOURCE_BASENAME}.utoc",
            f"{SOURCE_BASENAME}.ucas",
            "build-manifest.json",
        ):
            if required not in names:
                raise ValueError(f"Source ZIP is missing {required}")
        zip_manifest = json.loads(archive.read("build-manifest.json").decode("utf-8"))
        if zip_manifest != manifest:
            raise ValueError("Extracted build-manifest.json differs from the source ZIP")
        for member, key in (
            (f"{SOURCE_BASENAME}.utoc", "utoc_sha256"),
            (f"{SOURCE_BASENAME}.ucas", "ucas_sha256"),
        ):
            digest = hashlib.sha256()
            with archive.open(member, "r") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != manifest.get(key):
                raise ValueError(f"Source ZIP payload does not match manifest: {member}")
        pak_stub = archive.read(f"{SOURCE_BASENAME}.pak")
    if hashlib.sha256(pak_stub).hexdigest() != manifest.get("pak_sha256"):
        raise ValueError("Source PAK stub does not match its build manifest")
    return manifest, pak_stub


def variant_readme(title: str) -> str:
    return f"""Gorka 3 — обновлённая цветовая схема
====================================

{title}

Цветовые ориентиры Base Color:
- верх костюма — {rgb_hex(TARGET_UPPER_RGB)};
- штаны — {rgb_hex(TARGET_PANTS_RGB)};
- перчатки — {rgb_hex(TARGET_GLOVES_RGB)}.

Выпускается только вариант A; варианта B в этом обновлении нет. Крупные
тёмные цветовые поля верха выровнены по основному тону, мелкая фактура и
рельефные карты сохранены. Тон штанов поднят отдельно, без прежней второй
цветовой схемы. Перекрашена тканевая область Base Color-карт обеих перчаток;
экран, ремни и кожаные детали в верхней части атласа не затрагивались.

Основа — последняя сборка Gorka3_For_All_Gloves_Texture_Test с полными
перчатками. Изменены Base Color-карты Gorka: T_Gorka_Body_01_C,
T_Gorka_Arms_01_C, T_Gorka_Pants_01_C, T_Gorka_Set_01_C и LOD-карта
T_Gorka_LODX_01_C, а также T_Character_Gloves_01_c и
T_Character_Gloves_01_c_right. Геометрия/скелет, обувь, балаклава, экипировка,
Blueprint стандартного костюма, а также все Normal- и ORM-карты сохранены.
Остальные файлы и незатронутые блоки текстур совпадают с исходником.

УСТАНОВКА — прямо в Content\\Paks (не в ~mods)
1. Закройте игру.
2. Если в IntoTheRadius2\\Content\\Paks уже есть комплект
   Gorka3_For_All_P.pak/.utoc/.ucas, сохраните его копию вне Paks для отката.
3. Скопируйте три одноимённых файла из этого архива прямо в Content\\Paks,
   заменив старую версию.
4. Перезапустите игру и проверьте обычный стандартный костюм исследователя.

Цвет в игре зависит от освещения, настроек цвета и сжатия текстур и может
немного отличаться от указанных ориентиров. Контейнер и целевые payloads
проверены программно; именно эта новая цветовая версия в игре пока не
проверена.

Для публичного распространения исходных текстур Gorka требуется разрешение
Kerag. Этот архив подготовлен для личной проверки; не публикуйте его без
соответствующего разрешения.
"""


def build_variant(
    variant_key: str,
    title: str,
    zip_name: str,
    source_files: list[SourceFile],
    packages: list[PackageStoreInfo],
    replacements: dict[str, bytes],
    texture_reports: dict,
    source_manifest: dict,
    source_pak_stub: bytes,
    source_zip: Path,
) -> dict:
    variant_dir = OUTPUT_ROOT / variant_key
    variant_dir.mkdir(parents=True, exist_ok=True)
    variant_files: list[SourceFile] = []
    changed_payloads: dict[str, dict[str, str]] = {}
    for item in source_files:
        data = replacements.get(item.relative_path, item.data)
        if data != item.data:
            changed_payloads[item.relative_path] = {
                "source_sha256": hashlib.sha256(item.data).hexdigest(),
                "result_sha256": hashlib.sha256(data).hexdigest(),
            }
        variant_files.append(replace(item, data=data))

    expected_changes = {
        f"{GORKA_TEXTURE_DIR.as_posix()}/{name}.ubulk"
        for name in GORKA_BASECOLOR_TEXTURES
    }
    expected_glove_changes = {
        f"{GLOVE_TEXTURE_DIR.as_posix()}/{name}{suffix}"
        for name in GLOVE_BASECOLOR_TEXTURES
        for suffix in (".uasset", ".ubulk")
    }
    expected_changes |= expected_glove_changes
    if set(changed_payloads) != expected_changes:
        raise AssertionError(f"Unexpected changed payload set: {sorted(changed_payloads)}")

    container_id = int(source_manifest["container_id"], 16)
    output_base = variant_dir / MOD_BASENAME
    written = write_container(
        output_base,
        [Chunk(make_chunk_id(item.package_name, item.chunk_type), item.data, item.relative_path) for item in variant_files],
        packages,
        mount_point=MOUNT_POINT,
        container_id=container_id,
        oodle=None,
    )
    pak_path = variant_dir / f"{MOD_BASENAME}.pak"
    pak_path.write_bytes(source_pak_stub)
    readme = variant_dir / "ReadMe_RU.txt"
    readme.write_text(variant_readme(title), encoding="utf-8")

    validation = validate_container(
        written.utoc,
        written.ucas,
        variant_files,
        packages,
        container_id,
    )
    source_hashes = {item.relative_path: hashlib.sha256(item.data).hexdigest() for item in source_files}
    result_hashes = {item.relative_path: hashlib.sha256(item.data).hexdigest() for item in variant_files}
    unchanged_paths = sorted(path for path in source_hashes if source_hashes[path] == result_hashes[path])
    if len(unchanged_paths) != len(source_files) - len(expected_changes):
        raise AssertionError("Unexpected unchanged/changed payload counts")
    if any(source_hashes[path] != result_hashes[path] for path in unchanged_paths):
        raise AssertionError("A non-target payload changed")
    glove_paths = [path for path in source_hashes if "/Hand/Hand_ITR1/" in path]
    glove_non_color_paths = [path for path in glove_paths if path not in expected_glove_changes]
    if not glove_paths or any(source_hashes[path] != result_hashes[path] for path in glove_non_color_paths):
        raise AssertionError("A non-Base-Color glove asset changed")
    non_color_paths = [path for path in source_hashes if path not in expected_changes]
    if any(source_hashes[path] != result_hashes[path] for path in non_color_paths):
        raise AssertionError("A file outside the requested Base Color payloads changed")

    build_report = {
        **validation,
        "mod": MOD_BASENAME,
        "container_id": f"{container_id:016x}",
        "compression": "stored",
        "pak_sha256": hashlib.sha256(source_pak_stub).hexdigest(),
        "pak_size": len(source_pak_stub),
        "readme": readme.name,
        "base_build": {
            "source_archive": source_zip.name,
            "source_archive_sha256": sha256_file(source_zip),
            "source_utoc_sha256": source_manifest["utoc_sha256"],
            "source_ucas_sha256": source_manifest["ucas_sha256"],
            "source_build_manifest_sha256": hashlib.sha256(
                json.dumps(source_manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "source_mod": source_manifest.get("mod"),
        },
        "variant": {
            "id": variant_key,
            "title": title,
            "target_upper_rgb": rgb_hex(TARGET_UPPER_RGB),
            "target_pants_rgb": rgb_hex(TARGET_PANTS_RGB),
            "target_gloves_rgb": rgb_hex(TARGET_GLOVES_RGB),
            "upper_dark_regions_equalized": True,
            "pants_dark_regions_equalized": True,
            "pants_color_applied": True,
            "glove_color_applied": True,
            "variant_b_included": False,
            "runtime_verified_in_game": False,
        },
        "texture_edits": texture_reports,
        "changed_payloads": changed_payloads,
        "changed_payload_count": len(changed_payloads),
        "non_target_payloads_byte_identical": True,
        "glove_non_basecolor_payloads_byte_identical": True,
        "normal_orm_boots_detector_and_blueprint_byte_identical": True,
        "only_requested_basecolor_payloads_changed": True,
        "license_note": "Public redistribution of original Gorka textures requires permission from Kerag.",
        "release_archive_name": zip_name,
    }
    manifest_path = variant_dir / "build-manifest.json"
    manifest_path.write_text(json.dumps(build_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    zip_path = ZIP_ROOT / zip_name
    write_deterministic_zip(variant_dir, zip_path, MOD_BASENAME)
    build_report["release_zip"] = zip_path.name
    build_report["release_zip_sha256"] = sha256_file(zip_path)
    build_report["release_zip_size"] = zip_path.stat().st_size
    sidecar = ZIP_ROOT / f"{zip_name}.sha256"
    sidecar.write_text(f"{build_report['release_zip_sha256']}  {zip_path.name}\n", encoding="ascii")
    return build_report


def make_preview_overview(preview_paths: list[Path], output: Path) -> None:
    tile_w, tile_h = 520, 560
    sheet = Image.new("RGB", (tile_w * 2, tile_h * ((len(preview_paths) + 1) // 2)), "#202020")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(preview_paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail((500, 510))
        left = (index % 2) * tile_w + (tile_w - image.width) // 2
        top = (index // 2) * tile_h + 40
        sheet.paste(image, (left, top))
        draw.text(((index % 2) * tile_w + 12, (index // 2) * tile_h + 12), path.stem, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)


def main() -> None:
    global SOURCE_ROOT, CONTENT_ROOT, PREVIEW_ROOT, OUTPUT_ROOT, ZIP_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, default=SOURCE_ZIP)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--content-root", type=Path, default=CONTENT_ROOT)
    parser.add_argument("--preview-root", type=Path, default=PREVIEW_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--preview-only", action="store_true", help="Create preview PNGs without rebuilding IoStore packages")
    args = parser.parse_args()

    SOURCE_ROOT = args.source_root
    CONTENT_ROOT = args.content_root
    PREVIEW_ROOT = args.preview_root
    OUTPUT_ROOT = args.output_root

    source_manifest, source_pak_stub = source_metadata(args.source_zip, SOURCE_ROOT)
    source_files, packages = collect_source_payloads(CONTENT_ROOT, source_manifest)
    replacements_by_variant: dict[str, dict[str, bytes]] = {key: {} for key in VARIANTS}
    reports_by_variant: dict[str, dict] = {key: {} for key in VARIANTS}

    for variant_key, info in VARIANTS.items():
        preview_paths: list[Path] = []
        for texture_name, texture_info in GORKA_BASECOLOR_TEXTURES.items():
            role = str(texture_info["role"])
            target_rgb = TARGET_UPPER_RGB if role == "upper" else TARGET_PANTS_RGB
            base_dimension = int(texture_info["dimension"])
            dark_lift = bool(texture_info["dark_lift"])
            relative = (GORKA_TEXTURE_DIR / f"{texture_name}.ubulk").as_posix()
            preview_path = PREVIEW_ROOT / variant_key / f"{texture_name}.png"
            data, report = recolor_texture(
                CONTENT_ROOT,
                texture_name,
                base_dimension,
                role=role,
                target_rgb=target_rgb,
                dark_lift=dark_lift,
                preview_path=preview_path,
            )
            source = next(item for item in source_files if item.relative_path == relative)
            if len(data) != len(source.data):
                raise AssertionError(f"Texture payload size changed: {relative}")
            replacements_by_variant[variant_key][relative] = data
            reports_by_variant[variant_key][texture_name] = report
            preview_paths.append(preview_path)

        for texture_name, base_dimension in GLOVE_BASECOLOR_TEXTURES.items():
            preview_path = PREVIEW_ROOT / variant_key / f"{texture_name}.png"
            uasset_data, ubulk_data, report = recolor_glove_texture(
                CONTENT_ROOT,
                texture_name,
                base_dimension,
                preview_path=preview_path,
            )
            uasset_relative = (GLOVE_TEXTURE_DIR / f"{texture_name}.uasset").as_posix()
            ubulk_relative = (GLOVE_TEXTURE_DIR / f"{texture_name}.ubulk").as_posix()
            source_uasset = next(item for item in source_files if item.relative_path == uasset_relative)
            source_ubulk = next(item for item in source_files if item.relative_path == ubulk_relative)
            if len(uasset_data) != len(source_uasset.data) or len(ubulk_data) != len(source_ubulk.data):
                raise AssertionError(f"Glove texture payload size changed: {texture_name}")
            replacements_by_variant[variant_key][uasset_relative] = uasset_data
            replacements_by_variant[variant_key][ubulk_relative] = ubulk_data
            reports_by_variant[variant_key][texture_name] = report
            preview_paths.append(preview_path)

        make_preview_overview(preview_paths, PREVIEW_ROOT / variant_key / "overview.jpg")

    if args.preview_only:
        print(json.dumps({"preview_only": True, "preview_root": str(PREVIEW_ROOT), "variants": reports_by_variant}, ensure_ascii=False, indent=2))
        return

    ZIP_ROOT = args.output_root.parent
    ZIP_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for variant_key, info in VARIANTS.items():
        build_report = build_variant(
            variant_key,
            info["title"],
            info["zip_name"],
            source_files,
            packages,
            replacements_by_variant[variant_key],
            reports_by_variant[variant_key],
            source_manifest,
            source_pak_stub,
            args.source_zip,
        )
        print(json.dumps({
            "variant": variant_key,
            "title": info["title"],
            "zip": build_report["release_zip"],
            "zip_size": build_report["release_zip_size"],
            "zip_sha256": build_report["release_zip_sha256"],
            "roundtrip_payloads_byte_identical": build_report["roundtrip_payloads_byte_identical"],
            "glove_non_basecolor_payloads_byte_identical": build_report["glove_non_basecolor_payloads_byte_identical"],
            "only_requested_basecolor_payloads_changed": build_report["only_requested_basecolor_payloads_changed"],
            "changed_payload_count": build_report["changed_payload_count"],
            "runtime_verified_in_game": False,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
