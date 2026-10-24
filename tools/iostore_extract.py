#!/usr/bin/env python3
"""Inspect and extract an unencrypted Unreal IoStore container."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
import zlib


TOC_MAGIC = b"-==--==--==--==-"
INVALID = 0xFFFFFFFF


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        out = self.data[self.pos:self.pos+n]
        if len(out) != n:
            raise ValueError(f"Truncated data at {self.pos}: wanted {n}, got {len(out)}")
        self.pos += n
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def skip(self, n: int) -> None:
        self.take(n)

    def fstring(self) -> str:
        length = self.i32()
        if length == 0:
            return ""
        if length > 0:
            return self.take(length).rstrip(b"\0").decode("utf-8")
        return self.take(-length * 2).decode("utf-16-le").rstrip("\0")


def uint40_be(data: bytes) -> int:
    return int.from_bytes(data, "big")


def normalize_mount(value: str) -> str:
    value = value.replace("\\", "/").rstrip("/")
    while value.startswith("../"):
        value = value[3:]
    return value.lstrip("/")


def parse_toc(data: bytes) -> dict:
    r = Reader(data)
    if r.take(16) != TOC_MAGIC:
        raise ValueError("Not an IoStore UTOC")
    version = r.u8()
    r.skip(3)
    header = {
        "version": version,
        "header_size": r.u32(),
        "chunk_count": r.u32(),
        "block_count": r.u32(),
        "block_entry_size": r.u32(),
        "method_name_count": r.u32(),
        "method_name_length": r.u32(),
        "block_size": r.u32(),
        "directory_index_size": r.u32(),
        "partition_count": r.u32(),
        "container_id": r.u64(),
        "encryption_key_guid": r.take(16).hex(),
        "flags": r.u32(),
        "perfect_hash_seed_count": r.u32(),
        "partition_size": r.u64(),
        "chunks_without_perfect_hash_count": r.u32(),
    }
    r.skip(4 + 8 * 5)
    if header["header_size"] != r.pos:
        raise ValueError(f"Unexpected header size: {header['header_size']} != {r.pos}")
    if header["flags"] & 2:
        raise ValueError("Encrypted containers are not supported")
    if header["flags"] & 16:
        raise ValueError("On-demand containers are not supported")

    chunk_ids = [r.take(12) for _ in range(header["chunk_count"])]
    offset_lengths = []
    for _ in range(header["chunk_count"]):
        raw = r.take(10)
        offset_lengths.append((uint40_be(raw[:5]), uint40_be(raw[5:])))
    if version >= 5:
        r.skip(4 * header["perfect_hash_seed_count"])
        r.skip(4 * header["chunks_without_perfect_hash_count"])
    elif version >= 4:
        r.skip(4 * header["perfect_hash_seed_count"])

    blocks = []
    for _ in range(header["block_count"]):
        raw = r.take(header["block_entry_size"])
        if len(raw) != 12:
            raise ValueError(f"Unsupported block entry size {len(raw)}")
        blocks.append({
            "offset": int.from_bytes(raw[:5], "little"),
            "compressed_size": int.from_bytes(raw[5:8], "little"),
            "uncompressed_size": int.from_bytes(raw[8:11], "little"),
            "method_index": raw[11],
        })
    methods = ["None"]
    for _ in range(header["method_name_count"]):
        name = r.take(header["method_name_length"]).split(b"\0", 1)[0].decode("ascii")
        if name:
            methods.append(name)
    if header["flags"] & 4:
        hash_size = r.i32()
        r.skip(hash_size * 2)
        r.skip(20 * header["block_count"])

    directory_index = r.take(header["directory_index_size"])
    entries = parse_directory_index(directory_index, chunk_ids, offset_lengths) if header["flags"] & 8 else []
    return {
        "header": header,
        "methods": methods,
        "blocks": blocks,
        "entries": entries,
        "chunk_ids": chunk_ids,
        "offset_lengths": offset_lengths,
        "directory_index": directory_index,
        "trailing": data[r.pos:],
    }


def parse_directory_index(data: bytes, chunk_ids: list[bytes], offset_lengths: list[tuple[int, int]]) -> list[dict]:
    r = Reader(data)
    mount = normalize_mount(r.fstring())
    dir_count = r.u32()
    dirs = []
    for _ in range(dir_count):
        dirs.append(tuple(r.u32() for _ in range(4)))
    file_count = r.u32()
    files = []
    for _ in range(file_count):
        files.append(tuple(r.u32() for _ in range(3)))
    string_count = r.u32()
    strings = [r.fstring() for _ in range(string_count)]
    if r.pos != len(data):
        raise ValueError(f"Unexpected directory-index trailer: {len(data)-r.pos} bytes")

    entries = []
    visited = set()

    def recurse(dir_index: int, parent: str) -> None:
        current = dir_index
        while current != INVALID:
            if current in visited:
                raise ValueError("Directory-index cycle")
            if current >= len(dirs):
                raise ValueError(f"Bad directory index {current}")
            visited.add(current)
            name_index, first_child, next_sibling, first_file = dirs[current]
            path = parent
            if name_index != INVALID and strings[name_index]:
                path = f"{parent}/{strings[name_index]}" if parent else strings[name_index]
            file_index = first_file
            file_visited = set()
            while file_index != INVALID:
                if file_index in file_visited:
                    raise ValueError("File-index cycle")
                file_visited.add(file_index)
                name, next_file, chunk_index = files[file_index]
                if chunk_index >= len(offset_lengths):
                    raise ValueError(f"Bad chunk index {chunk_index}")
                offset, length = offset_lengths[chunk_index]
                entries.append({
                    "path": f"{path}/{strings[name]}" if path else strings[name],
                    "chunk_index": chunk_index,
                    "chunk_id": chunk_ids[chunk_index].hex(),
                    "offset": offset,
                    "length": length,
                })
                file_index = next_file
            recurse(first_child, path)
            current = next_sibling

    if dirs:
        recurse(0, mount)
    return entries


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_output_path(root: Path, logical_path: str) -> Path:
    pure = PurePosixPath(logical_path)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Unsafe logical path: {logical_path}")
    out = root.joinpath(*pure.parts)
    if os.path.commonpath((str(root.resolve()), str(out.resolve()))) != str(root.resolve()):
        raise ValueError(f"Unsafe output path: {out}")
    return out


def decompress_block(method: str, compressed: bytes, expected: int) -> bytes:
    if method == "None":
        out = compressed
    elif method == "Oodle":
        try:
            from kraken_decompressor import decompress as oodle_decompress
        except ImportError as exc:
            raise RuntimeError(
                "Oodle extraction requires: python3 -m pip install "
                "kraken-decompressor==0.2.1"
            ) from exc
        out = oodle_decompress(compressed, expected)
    elif method == "Zlib":
        out = zlib.decompress(compressed)
    elif method == "Zstd":
        import zstandard
        out = zstandard.ZstdDecompressor().decompress(compressed, max_output_size=expected)
    elif method == "LZ4":
        import lz4.block
        out = lz4.block.decompress(compressed, uncompressed_size=expected)
    else:
        raise ValueError(f"Unsupported compression method {method}")
    if len(out) != expected:
        raise ValueError(f"Bad {method} block size: expected {expected}, got {len(out)}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("utoc", type=Path)
    parser.add_argument("--ucas", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    utoc = args.utoc
    ucas = args.ucas or utoc.with_suffix(".ucas")
    toc = parse_toc(utoc.read_bytes())
    summary = {
        "utoc": str(utoc),
        "ucas": str(ucas),
        "utoc_sha256": sha256_file(utoc),
        "ucas_sha256": sha256_file(ucas) if ucas.exists() else None,
        "header": toc["header"],
        "methods": toc["methods"],
        "entries": toc["entries"],
        "trailing_size": len(toc["trailing"]),
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "entries"}, indent=2))
    print(f"\nEntries ({len(toc['entries'])}):")
    for entry in toc["entries"]:
        print(f"{entry['length']:12,d}  chunk {entry['chunk_index']:3d}  {entry['path']}")
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if not args.output:
        return
    args.output.mkdir(parents=True, exist_ok=True)
    block_cache: dict[int, bytes] = {}
    with ucas.open("rb") as stream:
        for entry in toc["entries"]:
            block_size = toc["header"]["block_size"]
            first = entry["offset"] // block_size
            end = (entry["offset"] + entry["length"] + block_size - 1) // block_size
            parts = []
            for index in range(first, end):
                if index not in block_cache:
                    block = toc["blocks"][index]
                    stream.seek(block["offset"])
                    compressed = stream.read(block["compressed_size"])
                    if len(compressed) != block["compressed_size"]:
                        raise ValueError(f"Truncated UCAS at block {index}")
                    method = toc["methods"][block["method_index"]]
                    block_cache[index] = decompress_block(method, compressed, block["uncompressed_size"])
                parts.append(block_cache[index])
            start = entry["offset"] % block_size
            payload = b"".join(parts)[start:start + entry["length"]]
            if len(payload) != entry["length"]:
                raise ValueError(f"Bad extracted size for {entry['path']}")
            destination = safe_output_path(args.output, entry["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            print(f"Extracted {entry['path']} ({len(payload):,} bytes)")


if __name__ == "__main__":
    main()
