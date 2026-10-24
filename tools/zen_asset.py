#!/usr/bin/env python3
"""Read UE5.5 Zen package headers (the format used by ITR2 cooked assets).

This is intentionally small and read-only. It resolves the package-local name,
import and export maps without requiring Unreal Engine or a Rust toolchain.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
from typing import Any


INDEX_MASK = (1 << 30) - 1
OBJECT_INDEX_MASK = (1 << 62) - 1
NULL_OBJECT_INDEX = 0xFFFFFFFFFFFFFFFF
EXPORT_MAP_ENTRY_SIZE = 72
BULK_DATA_MAP_ENTRY_SIZE = 32


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, size: int) -> bytes:
        out = self.data[self.pos:self.pos + size]
        if len(out) != size:
            raise ValueError(f"Truncated package at 0x{self.pos:x}: need {size} bytes")
        self.pos += size
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def seek(self, pos: int) -> None:
        if not 0 <= pos <= len(self.data):
            raise ValueError(f"Seek outside package: 0x{pos:x}")
        self.pos = pos


def mapped_name(raw: int, number: int, names: list[str]) -> str:
    kind = raw >> 30
    index = raw & INDEX_MASK
    if kind != 0:
        raise ValueError(f"Expected a package mapped name, got kind {kind}")
    if index >= len(names):
        raise ValueError(f"Name index {index} outside {len(names)}-entry name map")
    name = names[index]
    return f"{name}_{number - 1}" if number else name


def read_name_batch(r: Reader) -> dict[str, Any]:
    count = r.u32()
    if count == 0:
        return {"names": [], "string_bytes": 0, "hash_version": None, "hashes": []}
    string_bytes = r.u32()
    hash_version = r.u64()
    hashes = [r.u64() for _ in range(count)]
    lengths = [struct.unpack(">h", r.take(2))[0] for _ in range(count)]
    names = []
    for length in lengths:
        if length >= 0:
            names.append(r.take(length).decode("utf-8"))
        else:
            units = length + 32768
            if units <= 0:
                raise ValueError(f"Invalid UTF-16 name length {length}")
            names.append(r.take(units * 2).decode("utf-16-le"))
    return {
        "names": names,
        "string_bytes": string_bytes,
        "hash_version": hash_version,
        "hashes": hashes,
    }


def object_index(raw: int) -> dict[str, Any]:
    kind = raw >> 62
    value = raw & OBJECT_INDEX_MASK
    result: dict[str, Any] = {"raw": raw, "kind": ("export", "script_import", "package_import", "null")[kind]}
    if kind == 0:
        result["export_index"] = value
    elif kind == 2:
        result["imported_package_index"] = value >> 32
        result["imported_public_export_hash_index"] = value & 0xFFFFFFFF
    return result


@dataclass
class ZenPackage:
    data: bytes
    summary: dict[str, int]
    names: list[str]
    name_hashes: list[int]
    bulk_data: list[dict[str, int]]
    imported_public_export_hashes: list[int]
    imports: list[dict[str, Any]]
    exports: list[dict[str, Any]]
    imported_package_names: list[str]
    imported_package_name_numbers: list[int]
    imported_names_end: int

    @property
    def package_name(self) -> str:
        return mapped_name(self.summary["name"], self.summary["name_number"], self.names)

    def imported_package_for_import(self, import_index: int) -> str | None:
        item = self.imports[import_index]
        if item["kind"] != "package_import":
            return None
        package_index = item["imported_package_index"]
        if package_index >= len(self.imported_package_names):
            raise ValueError(f"Import {import_index} references missing package {package_index}")
        number = self.imported_package_name_numbers[package_index]
        name = self.imported_package_names[package_index]
        return f"{name}_{number - 1}" if number else name

    def as_dict(self, include_data: bool = False) -> dict[str, Any]:
        result = {
            "package_name": self.package_name,
            "file_size": len(self.data),
            "summary": self.summary,
            "names": self.names,
            "bulk_data": self.bulk_data,
            "imported_public_export_hashes": self.imported_public_export_hashes,
            "imports": [
                {**item, "imported_package": self.imported_package_for_import(i)}
                for i, item in enumerate(self.imports)
            ],
            "exports": self.exports,
            "imported_package_names": self.imported_package_names,
            "imported_package_name_numbers": self.imported_package_name_numbers,
            "imported_names_end": self.imported_names_end,
        }
        if include_data:
            result["export_data"] = {
                str(i): self.data[
                    self.summary["header_size"] + e["cooked_serial_offset"]:
                    self.summary["header_size"] + e["cooked_serial_offset"] + e["cooked_serial_size"]
                ].hex()
                for i, e in enumerate(self.exports)
            }
        return result


def parse_package(data: bytes) -> ZenPackage:
    r = Reader(data)
    # ITR2 uses EIoContainerHeaderVersion::SoftPackageReferences (UE5.5).
    summary = {
        "has_versioning_info": r.u32(),
        "header_size": r.u32(),
        "name": r.u32(),
        "name_number": r.u32(),
        "package_flags": r.u32(),
        "cooked_header_size": r.u32(),
        "imported_public_export_hashes_offset": r.i32(),
        "import_map_offset": r.i32(),
        "export_map_offset": r.i32(),
        "export_bundle_entries_offset": r.i32(),
        "dependency_bundle_headers_offset": r.i32(),
        "dependency_bundle_entries_offset": r.i32(),
        "imported_package_names_offset": r.i32(),
    }
    if summary["has_versioning_info"]:
        raise ValueError("Versioned Zen packages are outside this reader's ITR2 scope")
    batch = read_name_batch(r)
    names = batch["names"]

    # UE5.4+ aligns the bulk-data map size to eight bytes using a padding array.
    padding_size = r.u64()
    if padding_size > 7:
        raise ValueError(f"Implausible bulk-data padding: {padding_size}")
    r.take(padding_size)
    bulk_data_size = r.i64()
    if bulk_data_size < 0 or bulk_data_size % BULK_DATA_MAP_ENTRY_SIZE:
        raise ValueError(f"Invalid bulk-data map size: {bulk_data_size}")
    bulk_data = []
    for _ in range(bulk_data_size // BULK_DATA_MAP_ENTRY_SIZE):
        bulk_data.append({
            "serial_offset": r.i64(),
            "duplicate_serial_offset": r.i64(),
            "serial_size": r.i64(),
            "flags": r.u32(),
            "cooked_index": r.u8(),
            "pad": int.from_bytes(r.take(3), "little"),
        })

    def region(start: int, end: int) -> tuple[int, int]:
        if not 0 <= start <= end <= len(data):
            raise ValueError(f"Invalid header region {start}..{end} for {len(data)}-byte package")
        return start, end

    region(summary["imported_public_export_hashes_offset"], summary["import_map_offset"])
    r.seek(summary["imported_public_export_hashes_offset"])
    hash_count = (summary["import_map_offset"] - summary["imported_public_export_hashes_offset"]) // 8
    imported_hashes = [r.u64() for _ in range(hash_count)]

    region(summary["import_map_offset"], summary["export_map_offset"])
    r.seek(summary["import_map_offset"])
    import_count = (summary["export_map_offset"] - summary["import_map_offset"]) // 8
    imports = [object_index(r.u64()) for _ in range(import_count)]

    region(summary["export_map_offset"], summary["export_bundle_entries_offset"])
    export_bytes = summary["export_bundle_entries_offset"] - summary["export_map_offset"]
    if export_bytes % EXPORT_MAP_ENTRY_SIZE:
        raise ValueError(f"Export map has unexpected size {export_bytes}")
    r.seek(summary["export_map_offset"])
    exports = []
    for _ in range(export_bytes // EXPORT_MAP_ENTRY_SIZE):
        item = {
            "cooked_serial_offset": r.u64(),
            "cooked_serial_size": r.u64(),
            "object_name_raw": r.u32(),
            "object_name_number": r.u32(),
            "outer_index": object_index(r.u64()),
            "class_index": object_index(r.u64()),
            "super_index": object_index(r.u64()),
            "template_index": object_index(r.u64()),
            "public_export_hash": r.u64(),
            "object_flags": r.u32(),
            "filter_flags": r.u8(),
            "padding": int.from_bytes(r.take(3), "little"),
        }
        item["object_name"] = mapped_name(item["object_name_raw"], item["object_name_number"], names)
        serial_start = summary["header_size"] + item["cooked_serial_offset"]
        serial_end = serial_start + item["cooked_serial_size"]
        if serial_end > len(data):
            raise ValueError(f"Export {item['object_name']} exceeds package data: {serial_end} > {len(data)}")
        exports.append(item)

    names_offset = summary["imported_package_names_offset"]
    if names_offset <= 0:
        imported_names = []
        imported_numbers = []
        imported_names_end = summary["header_size"]
    else:
        region(names_offset, summary["header_size"])
        r.seek(names_offset)
        imported_batch = read_name_batch(r)
        imported_names = imported_batch["names"]
        imported_numbers = [r.i32() for _ in imported_names]
        imported_names_end = r.pos
        if imported_names_end != summary["header_size"]:
            raise ValueError(
                f"Imported package names end at {imported_names_end}, header size is {summary['header_size']}"
            )

    return ZenPackage(
        data=data,
        summary=summary,
        names=names,
        name_hashes=batch["hashes"],
        bulk_data=bulk_data,
        imported_public_export_hashes=imported_hashes,
        imports=imports,
        exports=exports,
        imported_package_names=imported_names,
        imported_package_name_numbers=imported_numbers,
        imported_names_end=imported_names_end,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-data", action="store_true")
    args = parser.parse_args()
    result = {
        str(path): parse_package(path.read_bytes()).as_dict(args.include_data)
        for path in args.packages
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
