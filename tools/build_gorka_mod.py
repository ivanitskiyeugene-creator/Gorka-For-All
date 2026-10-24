#!/usr/bin/env python3
"""Build the Gorka 3 replacement for ITR2's standard Explorer outfit.

Inputs are the already extracted original Kerag visual mod and the verified
current-game asset selection.  No mesh is approximated or re-authored: Basic
is retargeted to the actual game SkeletalMesh packages used by the Gorka/ITR1
outfit.  The detector's two audio chunks are deliberately excluded.

Example (from the repository root):
  PYTHONPATH=work/tools/pydeps:. python tools/build_gorka_mod.py \
    --oodle-library work/tools/oodle/liboo2corelinux64.so.9
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
from typing import Iterable
import zipfile

from blake3 import blake3

from tools.iostore_extract import (
    decompress_block,
    normalize_mount,
    parse_toc,
    sha256_file,
)
from tools.iostore_write import (
    BULK_DATA_CHUNK_TYPE,
    EXPORT_BUNDLE_CHUNK_TYPE,
    Chunk,
    OodleCompressor,
    PackageStoreInfo,
    build_container_header,
    container_id_from_name,
    lookup_chunk_index,
    make_chunk_id,
    package_id,
    patch_imported_package_names,
    write_container,
)
from tools.zen_asset import ZenPackage, parse_package


MOUNT_POINT = "../../../ITR2_Gorka3/Content/"
MOD_BASENAME = "Gorka3_For_All_P"
BASIC_PACKAGE = "/Game/ITR2/BPs/Items/Outfits/BP_OutfitExplorerBasic"
DETECTOR_AUDIO_STEM = "Sound/SFX/Detector_MS/Detector_ITR1/A_SFX_Detector_Click_B3"

BODY_OLD = "/Game/ITR2/Art/Characters/Player/Body/Body_01/Male_Body_Test_01"
BODY_NEW = "/Game/ITR2/Art/Characters/Player/Body/Body_Gorka_01/SKM_Player_Body_Gorka_01_a"
RIGHT_OLD = "/Game/ITR2/Art/Characters/Player/Hand/Hand_01/SKM_Player_Gloves_02"
RIGHT_NEW = "/Game/ITR2/Art/Characters/Player/Hand/Hand_ITR1/SKM_Player_Gloves_ITR1_01_Right"
LEFT_OLD = "/Game/ITR2/Art/Characters/Player/Hand/Hand_01/SKM_Player_Gloves_Left_02"
LEFT_NEW = "/Game/ITR2/Art/Characters/Player/Hand/Hand_ITR1/SKM_Player_Gloves_ITR1_01_Left"

# These are also checked against the source Basic package.  They prevent an
# accidental build against a different costume revision with the same path.
EXPECTED_OLD_HASHES = {
    BODY_OLD: 0xB12EDA0D6B2D8A94,
    RIGHT_OLD: 0x50D71AAA4D46E544,
    LEFT_OLD: 0xCACBF55DD2F81186,
}


@dataclass
class SourceFile:
    relative_path: str
    package_name: str
    chunk_type: int
    data: bytes


def game_asset_path(root: Path, package_name: str) -> Path:
    if not package_name.startswith("/Game/"):
        raise ValueError(f"Not a /Game package: {package_name}")
    return root / "IntoTheRadius2" / "Content" / (package_name[6:] + ".uasset")


def package_from_source(path: Path) -> ZenPackage:
    return parse_package(path.read_bytes())


def collect_original_visuals(root: Path) -> tuple[list[SourceFile], list[PackageStoreInfo], dict[str, str]]:
    """Read all original visual chunks, explicitly dropping detector audio."""
    content_root = root / "ITR2_Gorka3" / "Content"
    if not content_root.is_dir():
        raise FileNotFoundError(f"Original extracted Content directory not found: {content_root}")
    packages: dict[str, ZenPackage] = {}
    for path in sorted(content_root.rglob("*.uasset")):
        z = package_from_source(path)
        relative = path.relative_to(content_root).as_posix()
        packages[relative] = z

    files: list[SourceFile] = []
    store: list[PackageStoreInfo] = []
    source_hashes: dict[str, str] = {}
    for path in sorted(content_root.rglob("*")):
        if not path.is_file() or path.suffix not in (".uasset", ".ubulk"):
            continue
        relative = path.relative_to(content_root).as_posix()
        if relative == DETECTOR_AUDIO_STEM + path.suffix:
            continue
        stem = relative[:-len(path.suffix)]
        uasset_relative = stem + ".uasset"
        z = packages.get(uasset_relative)
        if z is None:
            raise ValueError(f"Missing source package for {relative}")
        data = path.read_bytes()
        files.append(SourceFile(relative, z.package_name, EXPORT_BUNDLE_CHUNK_TYPE if path.suffix == ".uasset" else BULK_DATA_CHUNK_TYPE, data))
        source_hashes[relative] = hashlib.sha256(data).hexdigest()
        if path.suffix == ".uasset":
            store.append(PackageStoreInfo(z.package_name, list(z.imported_package_names)))
    if len(files) != 52:
        raise ValueError(f"Expected 52 original visual files after audio exclusion, got {len(files)}")
    if len(store) != 26:
        raise ValueError(f"Expected 26 original visual packages, got {len(store)}")
    return files, store, source_hashes


def make_basic_patch(game_root: Path) -> tuple[SourceFile, PackageStoreInfo, dict]:
    basic_path = game_asset_path(game_root, BASIC_PACKAGE)
    original = basic_path.read_bytes()
    z = parse_package(original)
    if z.package_name != BASIC_PACKAGE:
        raise ValueError(f"Unexpected Basic package name: {z.package_name}")

    targets = {
        BODY_OLD: BODY_NEW,
        RIGHT_OLD: RIGHT_NEW,
        LEFT_OLD: LEFT_NEW,
    }
    target_hashes: dict[str, int] = {}
    target_export_names: dict[str, str] = {}
    for new_name in targets.values():
        target = parse_package(game_asset_path(game_root, new_name).read_bytes())
        if target.package_name != new_name:
            raise ValueError(f"Target package name mismatch: {target.package_name} != {new_name}")
        if len(target.exports) < 2:
            raise ValueError(f"Target has no primary SkeletalMesh export: {new_name}")
        export = target.exports[1]
        target_hashes[new_name] = export["public_export_hash"]
        target_export_names[new_name] = export["object_name"]

    # Cross-check against the game's own SP outfit, which already references
    # these exact meshes.  Basic retains its own face and blueprint logic.
    sp_path = game_root / "IntoTheRadius2" / "Content" / "ITR2" / "BPs" / "Items" / "Outfits" / "BP_OutfitExplorer_SP.uasset"
    sp = parse_package(sp_path.read_bytes())
    sp_hashes = {
        sp.imported_package_for_import(i): sp.imported_public_export_hashes[item["imported_public_export_hash_index"]]
        for i, item in enumerate(sp.imports)
        if item["kind"] == "package_import"
    }
    for new_name, expected_hash in target_hashes.items():
        if sp_hashes.get(new_name) != expected_hash:
            raise ValueError(f"SP does not confirm target {new_name}: {sp_hashes.get(new_name)} != {expected_hash}")

    new_names = list(z.imported_package_names)
    hash_changes: list[dict] = []
    seen: set[str] = set()
    for import_index, item in enumerate(z.imports):
        if item["kind"] != "package_import":
            continue
        old_name = z.imported_package_for_import(import_index)
        if old_name not in targets:
            continue
        new_name = targets[old_name]
        package_index = item["imported_package_index"]
        hash_index = item["imported_public_export_hash_index"]
        old_hash = z.imported_public_export_hashes[hash_index]
        if old_hash != EXPECTED_OLD_HASHES[old_name]:
            raise ValueError(f"Unexpected source hash for {old_name}: {old_hash:x}")
        if new_names[package_index] != old_name:
            raise ValueError(f"Import/name-map mismatch for {old_name}")
        new_names[package_index] = new_name
        hash_changes.append({
            "import_index": import_index,
            "imported_package_index": package_index,
            "public_export_hash_index": hash_index,
            "old_package": old_name,
            "new_package": new_name,
            "old_hash": f"{old_hash:016x}",
            "new_hash": f"{target_hashes[new_name]:016x}",
            "target_export": target_export_names[new_name],
        })
        seen.add(old_name)
    if seen != set(targets):
        raise ValueError(f"Basic did not contain all three expected imports: {seen}")

    patched, new_header_size = patch_imported_package_names(
        original,
        z.summary["imported_package_names_offset"],
        z.summary["header_size"],
        new_names,
        z.imported_package_name_numbers,
    )
    patched = bytearray(patched)
    struct.pack_into("<I", patched, 4, new_header_size)
    for change in hash_changes:
        offset = z.summary["imported_public_export_hashes_offset"] + change["public_export_hash_index"] * 8
        struct.pack_into("<Q", patched, offset, int(change["new_hash"], 16))

    checked = parse_package(bytes(patched))
    if checked.summary["header_size"] != new_header_size:
        raise AssertionError("Patched Basic header size was not updated")
    if bytes(patched)[new_header_size:] != original[z.summary["header_size"]:]:
        raise AssertionError("Basic export bytes changed during import retargeting")
    if checked.names != z.names:
        raise AssertionError("Basic local name map changed")
    for change in hash_changes:
        import_index = change["import_index"]
        item = checked.imports[import_index]
        if checked.imported_package_for_import(import_index) != change["new_package"]:
            raise AssertionError(f"Patched import did not retarget: {change}")
        actual_hash = checked.imported_public_export_hashes[item["imported_public_export_hash_index"]]
        if actual_hash != int(change["new_hash"], 16):
            raise AssertionError(f"Patched hash did not retarget: {change}")
    if len(checked.data) != len(original) + (new_header_size - z.summary["header_size"]):
        raise AssertionError("Unexpected patched Basic size")

    relative = "ITR2/BPs/Items/Outfits/BP_OutfitExplorerBasic.uasset"
    source = SourceFile(relative, BASIC_PACKAGE, EXPORT_BUNDLE_CHUNK_TYPE, bytes(patched))
    store = PackageStoreInfo(BASIC_PACKAGE, new_names)
    details = {
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "patched_sha256": hashlib.sha256(patched).hexdigest(),
        "source_size": len(original),
        "patched_size": len(patched),
        "source_header_size": z.summary["header_size"],
        "patched_header_size": new_header_size,
        "export_bytes_unchanged": True,
        "local_name_map_unchanged": True,
        "changes": hash_changes,
    }
    return source, store, details


def read_chunk_payload(toc: dict, cas, chunk_index: int) -> bytes:
    offset, length = toc["offset_lengths"][chunk_index]
    block_size = toc["header"]["block_size"]
    first = offset // block_size
    end = (offset + length + block_size - 1) // block_size
    parts: list[bytes] = []
    for block_index in range(first, end):
        block = toc["blocks"][block_index]
        cas.seek(block["offset"])
        compressed = cas.read(block["compressed_size"])
        if len(compressed) != block["compressed_size"]:
            raise ValueError(f"Truncated UCAS block {block_index}")
        parts.append(decompress_block(toc["methods"][block["method_index"]], compressed, block["uncompressed_size"]))
    start = offset % block_size
    result = b"".join(parts)[start:start + length]
    if len(result) != length:
        raise ValueError(f"Bad chunk {chunk_index} size: {len(result)} != {length}")
    return result


def validate_package_store_header(
    data: bytes,
    expected_packages: Iterable[PackageStoreInfo],
    expected_container_id: int,
) -> int:
    """Decode the generated header independently of its writer.

    In particular, this checks the relative-array arithmetic for Basic's 13
    imported package IDs instead of merely comparing two writer-generated
    byte strings.
    """
    if len(data) < 16:
        raise ValueError("Truncated container header")
    magic, version, container_id = struct.unpack_from("<IIQ", data, 0)
    if magic != 0x496F436E or version != 4 or container_id != expected_container_id:
        raise ValueError("Unexpected container header signature/version/ID")
    pos = 16

    def u32() -> int:
        nonlocal pos
        if pos + 4 > len(data):
            raise ValueError("Truncated container header array")
        value, = struct.unpack_from("<I", data, pos)
        pos += 4
        return value

    count = u32()
    if pos + count * 8 > len(data):
        raise ValueError("Truncated container package ID array")
    ids = list(struct.unpack_from(f"<{count}Q", data, pos))
    pos += count * 8
    store_size = u32()
    store = data[pos:pos + store_size]
    if len(store) != store_size:
        raise ValueError("Truncated package store buffer")
    pos += store_size

    expected = sorted(expected_packages, key=lambda item: package_id(item.package_name))
    expected_ids = [package_id(item.package_name) for item in expected]
    if ids != expected_ids or len(store) < count * 16:
        raise ValueError("Package store IDs or entry count mismatch")
    for index, item in enumerate(expected):
        imported_count, imported_offset, shader_count, shader_offset = struct.unpack_from("<IIII", store, index * 16)
        imported_start = index * 16 + imported_offset
        imported_end = imported_start + imported_count * 8
        if imported_end > len(store) or (imported_count == 0 and imported_offset != 0):
            raise ValueError(f"Invalid imported-package array for {item.package_name}")
        actual_imports = list(struct.unpack_from(f"<{imported_count}Q", store, imported_start)) if imported_count else []
        expected_imports = [package_id(name) for name in item.imported_package_names]
        if actual_imports != expected_imports:
            raise ValueError(f"Imported-package array mismatch for {item.package_name}")
        shader_start = index * 16 + 8 + shader_offset
        shader_end = shader_start + shader_count * 20
        if shader_end > len(store) or (shader_count == 0 and shader_offset != 0):
            raise ValueError(f"Invalid shader-map array for {item.package_name}")
        actual_shaders = [store[i:i + 20] for i in range(shader_start, shader_end, 20)]
        if actual_shaders != item.shader_map_hashes:
            raise ValueError(f"Shader-map array mismatch for {item.package_name}")

    if u32() != 0:  # optional segment package IDs
        raise ValueError("Unexpected optional package IDs")
    if u32() != 0:  # optional segment store entries
        raise ValueError("Unexpected optional store entries")
    if u32() != 0:  # redirect name map (empty name batch)
        raise ValueError("Unexpected redirect names")
    if u32() != 0:  # localized packages
        raise ValueError("Unexpected localized packages")
    if u32() != 0:  # package redirects
        raise ValueError("Unexpected package redirects")
    if pos >= len(data) or data[pos] != 0:
        raise ValueError("Unexpected soft package references")
    pos += 1
    if any(data[pos:]) or len(data) - pos != (-pos % 4):
        raise ValueError("Invalid container header padding")
    return count


def validate_container(
    utoc: Path,
    ucas: Path,
    expected_files: Iterable[SourceFile],
    expected_packages: Iterable[PackageStoreInfo],
    expected_container_id: int,
) -> dict:
    """Independent read-back validation using the original read-only parser."""
    raw_utoc = utoc.read_bytes()
    toc = parse_toc(raw_utoc)
    expected = list(expected_files)
    expected_packages = list(expected_packages)
    expected_by_path = {
        f"{normalize_mount(MOUNT_POINT)}/{item.relative_path}": item for item in expected
    }
    actual_paths = {entry["path"] for entry in toc["entries"]}
    if actual_paths != set(expected_by_path):
        raise ValueError(f"Directory-index path mismatch: missing={set(expected_by_path)-actual_paths}, extra={actual_paths-set(expected_by_path)}")
    if toc["header"]["container_id"] != expected_container_id:
        raise ValueError("Container ID mismatch")
    if len(toc["trailing"]) != toc["header"]["chunk_count"] * 24:
        raise ValueError("Unexpected UTOC metadata trailer")

    n = toc["header"]["chunk_count"]
    seeds_offset = 144 + n * 22
    seed_count = toc["header"]["perfect_hash_seed_count"]
    seeds = list(struct.unpack_from(f"<{seed_count}i", raw_utoc, seeds_offset))
    overflow_offset = seeds_offset + seed_count * 4
    overflow_count = toc["header"]["chunks_without_perfect_hash_count"]
    overflow = list(struct.unpack_from(f"<{overflow_count}i", raw_utoc, overflow_offset))
    for index, chunk_id in enumerate(toc["chunk_ids"]):
        if lookup_chunk_index(chunk_id, toc["chunk_ids"], seeds, overflow) != index:
            raise ValueError(f"Perfect-hash lookup mismatch at chunk {index}")

    checked_chunks = 0
    checked_bytes = 0
    with ucas.open("rb") as cas:
        for entry in toc["entries"]:
            item = expected_by_path[entry["path"]]
            chunk_index = entry["chunk_index"]
            expected_id = make_chunk_id(item.package_name, item.chunk_type)
            if bytes.fromhex(entry["chunk_id"]) != expected_id:
                raise ValueError(f"Chunk ID mismatch for {entry['path']}")
            payload = read_chunk_payload(toc, cas, chunk_index)
            if payload != item.data:
                raise ValueError(f"Round-trip payload mismatch for {entry['path']}")
        # Validate every chunk, including the container header, against its
        # BLAKE3-derived 20-byte IoHash and compressed flag.
        for chunk_index, chunk_id in enumerate(toc["chunk_ids"]):
            payload = read_chunk_payload(toc, cas, chunk_index)
            meta = toc["trailing"][chunk_index * 24:(chunk_index + 1) * 24]
            if meta[:20] != blake3(payload).digest()[:20]:
                raise ValueError(f"IoHash mismatch at chunk {chunk_index}")
            first, length = toc["offset_lengths"][chunk_index]
            block_size = toc["header"]["block_size"]
            block_indices = range(first // block_size, (first + length + block_size - 1) // block_size)
            compressed = any(toc["blocks"][i]["method_index"] != 0 for i in block_indices)
            if bool(meta[20] & 1) != compressed:
                raise ValueError(f"Compressed flag mismatch at chunk {chunk_index}")
            checked_chunks += 1
            checked_bytes += len(payload)

        header_index = next(i for i, chunk_id in enumerate(toc["chunk_ids"]) if chunk_id[11] == 6)
        actual_header = read_chunk_payload(toc, cas, header_index)
        expected_header = build_container_header(expected_container_id, expected_packages)
        if actual_header != expected_header:
            raise ValueError("Container header round-trip mismatch")

        # Match FFileIoStoreReader::ReadContainerHeader(), not just the
        # general decompression round-trip above.  UE reads this chunk as raw
        # bytes during mount and explicitly assumes it is uncompressed.  A
        # compressed header can therefore pass every payload check while the
        # game never mounts the container at all.
        header_offset, header_length = toc["offset_lengths"][header_index]
        block_size = toc["header"]["block_size"]
        header_block_indices = range(
            header_offset // block_size,
            (header_offset + header_length + block_size - 1) // block_size,
        )
        header_blocks = [toc["blocks"][i] for i in header_block_indices]
        if any(block["method_index"] != 0 for block in header_blocks):
            raise ValueError("Container header must be uncompressed for UE mount")
        if any(block["compressed_size"] != block["uncompressed_size"] for block in header_blocks):
            raise ValueError("Container header has a non-raw compression block")
        cas.seek(header_blocks[0]["offset"])
        ue_direct_header = cas.read(header_length)
        if ue_direct_header != actual_header:
            raise ValueError("UE-style direct container-header read mismatch")
        package_store_count = validate_package_store_header(actual_header, expected_packages, expected_container_id)

    return {
        "utoc_sha256": sha256_file(utoc),
        "ucas_sha256": sha256_file(ucas),
        "utoc_size": utoc.stat().st_size,
        "ucas_size": ucas.stat().st_size,
        "chunk_count": n,
        "file_count": len(toc["entries"]),
        "compression_block_count": toc["header"]["block_count"],
        "perfect_hash_seed_count": seed_count,
        "chunks_without_perfect_hash": overflow_count,
        "roundtrip_chunks_verified": checked_chunks,
        "roundtrip_uncompressed_bytes": checked_bytes,
        "roundtrip_payloads_byte_identical": True,
        "container_header_byte_identical": True,
        "container_header_uncompressed_for_ue_mount": True,
        "container_header_ue_direct_read_verified": True,
        "package_store_entries_verified": package_store_count,
        "soft_package_references_empty": True,
        "package_chunk_ids_verified": True,
        "blake3_iohashes_verified": True,
    }


def write_readme(output_dir: Path, mod_basename: str = MOD_BASENAME) -> Path:
    text = f"""Gorka 3 — стандартный костюм исследователя (ITR2)
====================================================

Заменяет BP_OutfitExplorerBasic (обычный, не DLC Classic Explorer Suit)
на настоящие игровые модели Gorka 3 и перчатки ITR1. Геометрия, скелет,
скиннинг, LOD'ы, материалы и часы используются из реальных пакетов игры;
похожая самодельная модель не подставляется.

В архиве нет изменения звука детектора. Визуальные текстуры исходного
мода Kerag сохранены. DLC Classic Explorer Kit для этой замены не нужен.
BP_OutfitExplorer_SP и лицо стандартного костюма не перезаписываются.

УСТАНОВКА (корень Paks, без ~mods)
1. Закройте игру. Удалите старые Gorka3_P.* и Gorka3_For_All_P.* из
   IntoTheRadius2\\Content\\Paks, чтобы не было двух замен.
2. Скопируйте все три файла {mod_basename}.pak, .utoc и .ucas прямо в:
   IntoTheRadius2\\Content\\Paks\\
   Не создавайте для этой проверки подпапку ~mods.
3. Запустите игру и выберите обычный стандартный костюм исследователя
   (BP_OutfitExplorerBasic), не SP и не DLC Classic Explorer Suit.

Если изменения нет, проверьте, что в Paks лежат именно три новых файла
с одинаковым именем {mod_basename} и что игра была полностью перезапущена.
Этот вариант заменяет только Basic; он не заменяет SP/DLC-костюм.

Проверка сборки: все chunk ID, BLAKE3 IoHash, контейнерный заголовок и
распакованные payloads проверены программно. ContainerHeader специально
оставлен несжатым — это требование раннего mount-кода UE; его прямое
чтение также проверено. Посадку часов на правой руке и режим
BraceletOnLeft=false следует дополнительно проверить в VR.

Источники: визуальный мод Kerag (Gorka 3), реальные cooked-пакеты ITR2.
Сборка: Gorka-For-All, tools/build_gorka_mod.py.
"""
    path = output_dir / "ReadMe_RU.txt"
    path.write_text(text, encoding="utf-8")
    return path


def write_deterministic_zip(output_dir: Path, zip_path: Path, mod_basename: str = MOD_BASENAME) -> None:
    """Create a release ZIP whose hash does not depend on file mtimes."""
    names = [
        f"{mod_basename}.pak",
        f"{mod_basename}.ucas",
        f"{mod_basename}.utoc",
        "ReadMe_RU.txt",
        "build-manifest.json",
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(names):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, (output_dir / name).read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-extracted", type=Path, default=Path("work/extracted_gorka"))
    parser.add_argument("--game-assets", type=Path, default=Path("work/user_assets"))
    parser.add_argument("--pak-stub", type=Path, default=Path("work/original_mod/Gorka3_P.pak"))
    parser.add_argument("--output-dir", type=Path, default=Path("release/gorka-standard"))
    parser.add_argument("--mod-basename", default=MOD_BASENAME, help="Shared .pak/.utoc/.ucas basename; use Gorka3_P for the root-Paks compatibility diagnostic")
    parser.add_argument("--container-id", type=lambda value: int(value, 0), help="Optional explicit IoStore container ID (decimal or 0x-prefixed hex)")
    parser.add_argument("--oodle-library", type=Path)
    parser.add_argument("--no-compression", action="store_true")
    parser.add_argument("--zip", action="store_true", help="Also create a ZIP beside the output directory")
    args = parser.parse_args()

    if not args.no_compression and not args.oodle_library:
        parser.error("--oodle-library is required unless --no-compression is used")
    if args.oodle_library:
        os.environ["OODLE_LIBRARY"] = str(args.oodle_library.resolve())

    original_files, original_store, original_hashes = collect_original_visuals(args.original_extracted)
    basic, basic_store, basic_details = make_basic_patch(args.game_assets)
    files = original_files + [basic]
    packages = original_store + [basic_store]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_base = args.output_dir / args.mod_basename
    container_id = container_id_from_name(args.mod_basename) if args.container_id is None else args.container_id
    oodle = None if args.no_compression else OodleCompressor(args.oodle_library)
    written = write_container(
        output_base,
        [Chunk(make_chunk_id(item.package_name, item.chunk_type), item.data, item.relative_path) for item in files],
        packages,
        mount_point=MOUNT_POINT,
        container_id=container_id,
        oodle=oodle,
    )
    pak_path = args.output_dir / f"{args.mod_basename}.pak"
    shutil.copyfile(args.pak_stub, pak_path)
    readme = write_readme(args.output_dir, args.mod_basename)
    validation = validate_container(written.utoc, written.ucas, files, packages, written.container_id)
    validation.update({
        "mod": args.mod_basename,
        "container_id": f"{written.container_id:016x}",
        "compression": "stored" if args.no_compression else "Oodle Kraken Normal",
        "pak_sha256": sha256_file(pak_path),
        "pak_size": pak_path.stat().st_size,
        "readme": readme.name,
        "detector_audio_excluded": [
            DETECTOR_AUDIO_STEM + ".uasset",
            DETECTOR_AUDIO_STEM + ".ubulk",
        ],
        "original_visual_file_count": len(original_files),
        "original_visual_sha256": original_hashes,
        "basic_patch": basic_details,
    })
    manifest_path = args.output_dir / "build-manifest.json"
    manifest_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in validation.items() if k not in ("original_visual_sha256", "basic_patch")}, ensure_ascii=False, indent=2))
    print(f"Basic: {basic_details['source_size']} -> {basic_details['patched_size']} bytes; three imports retargeted")
    print(f"Wrote {written.utoc}, {written.ucas}, {pak_path}")
    print(f"Manifest: {manifest_path}")
    if args.zip:
        zip_path = args.output_dir.with_suffix(".zip")
        write_deterministic_zip(args.output_dir, zip_path, args.mod_basename)
        print(f"ZIP: {zip_path} ({zip_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
