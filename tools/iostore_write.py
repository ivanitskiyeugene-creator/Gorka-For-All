#!/usr/bin/env python3
"""Write the small, unencrypted UE5.5 IoStore containers used by ITR2 mods.

The implementation follows Unreal's IoStoreWriter and retoc's serialization
code.  It intentionally supports only the features needed by this project:
ExportBundleData/BulkData/ContainerHeader chunks, Oodle or stored blocks, an
indexed directory, package store entries, and the version-8 perfect hash map.

CityHash and BLAKE3 are required.  Oodle compression additionally requires an
official Oodle 2.9.10 shared library; ``--no-compression`` callers can use the
same writer without one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import math
from pathlib import Path
import struct
from typing import Iterable, Sequence

from blake3 import blake3
from cityhash import CityHash64

from tools.iostore_extract import INVALID, TOC_MAGIC


CONTAINER_HEADER_MAGIC = 0x496F436E
CONTAINER_HEADER_VERSION = 4  # SoftPackageReferences, as in the supplied mod
CONTAINER_HEADER_CHUNK_TYPE = 6
EXPORT_BUNDLE_CHUNK_TYPE = 1
BULK_DATA_CHUNK_TYPE = 2
FNAME_HASH_VERSION = 0xC1640000
DEFAULT_BLOCK_SIZE = 65536
DEFAULT_DISK_ALIGNMENT = 4096
MASK64 = (1 << 64) - 1


def package_id(package_name: str) -> int:
    """Return FPackageId::FromName (lowercase UTF-16LE CityHash64)."""
    return CityHash64(package_name.lower().encode("utf-16-le"))


def container_id_from_name(name: str) -> int:
    return package_id(name)


def name_hash(name: str) -> int:
    """Return the FName batch hash used by UE5.5."""
    lower = name.lower()
    data = lower.encode("ascii") if lower.isascii() else lower.encode("utf-16-le")
    return CityHash64(data)


def make_chunk_id(package_name: str, chunk_type: int) -> bytes:
    return struct.pack("<QHBB", package_id(package_name), 0, 0, chunk_type)


def make_container_header_chunk_id(container_id: int) -> bytes:
    return struct.pack("<QHBB", container_id, 0, 0, CONTAINER_HEADER_CHUNK_TYPE)


def write_name_batch(names: Sequence[str], hash_version: int = FNAME_HASH_VERSION) -> bytes:
    """Serialize FNameMap's name batch (not the legacy two-array format)."""
    out = bytearray(struct.pack("<I", len(names)))
    if not names:
        return bytes(out)
    encoded = [name.encode("ascii") if name.isascii() else name.encode("utf-16-le") for name in names]
    out += struct.pack("<IQ", sum(map(len, encoded)), hash_version)
    for name in names:
        out += struct.pack("<Q", name_hash(name))
    for name, data in zip(names, encoded):
        # The on-disk length is a big-endian signed 16-bit value.  UTF-16 uses
        # UE's negative-length bias (unit_count + INT16_MIN).
        if name.isascii():
            header = len(data)
        else:
            header = (len(data) // 2) - 32768
        if not -32768 <= header <= 32767:
            raise ValueError(f"Name is too long for an FName batch: {name!r}")
        out += struct.pack(">h", header)
    for data in encoded:
        out += data
    return bytes(out)


def patch_imported_package_names(
    data: bytes,
    imported_names_offset: int,
    old_header_size: int,
    names: Sequence[str],
    numbers: Sequence[int],
) -> tuple[bytes, int]:
    """Rebuild the trailing Zen imported-package name batch.

    The caller patches the summary header_size and import hashes.  Keeping this
    operation separate makes it explicit that export bytes are only relocated,
    never reserialized.
    """
    if len(names) != len(numbers):
        raise ValueError("Imported package name/number count mismatch")
    if not 0 <= imported_names_offset <= old_header_size <= len(data):
        raise ValueError("Invalid imported package name region")
    batch = write_name_batch(names)
    batch += struct.pack(f"<{len(numbers)}i", *numbers)
    new_header_size = imported_names_offset + len(batch)
    return data[:imported_names_offset] + batch + data[old_header_size:], new_header_size


@dataclass
class PackageStoreInfo:
    package_name: str
    imported_package_names: list[str] = field(default_factory=list)
    shader_map_hashes: list[bytes] = field(default_factory=list)


def build_container_header(container_id: int, packages: Iterable[PackageStoreInfo]) -> bytes:
    """Build an EIoContainerHeaderVersion::SoftPackageReferences header.

    Version 4 store entries contain relative arrays of imported package IDs and
    shader-map hashes.  This is the exact version found in Gorka3_P.utoc.
    """
    ordered = sorted(packages, key=lambda item: package_id(item.package_name))
    ids = [package_id(item.package_name) for item in ordered]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate package ID in container header")

    count = len(ordered)
    entry_size = 16
    entries = bytearray()
    arrays = bytearray()
    for item in ordered:
        entry_offset = len(entries)
        imported_ids = [package_id(name) for name in item.imported_package_names]
        if len(set(imported_ids)) != len(imported_ids):
            raise ValueError(f"Duplicate imported package ID in {item.package_name}")
        imported_num = len(imported_ids)
        imported_offset = 0
        if imported_ids:
            imported_offset = entry_size * count + len(arrays) - entry_offset
            for imported_id in imported_ids:
                arrays += struct.pack("<Q", imported_id)
        shader_num = len(item.shader_map_hashes)
        shader_offset = 0
        if shader_num:
            # The shader array view is eight bytes into the 16-byte entry.
            shader_offset = entry_size * count + len(arrays) - entry_offset - 8
            for digest in item.shader_map_hashes:
                if len(digest) != 20:
                    raise ValueError("Shader map hashes must be 20-byte SHA-1 digests")
                arrays += digest
        entries += struct.pack("<IIII", imported_num, imported_offset, shader_num, shader_offset)
    if len(entries) != count * entry_size:
        raise AssertionError("Internal package store size error")
    store_buffer = bytes(entries + arrays)

    out = bytearray()
    out += struct.pack("<IIQ", CONTAINER_HEADER_MAGIC, CONTAINER_HEADER_VERSION, container_id)
    out += struct.pack("<I", count)
    for value in ids:
        out += struct.pack("<Q", value)
    out += struct.pack("<I", len(store_buffer))
    out += store_buffer
    out += struct.pack("<I", 0)  # optional segment package IDs
    out += struct.pack("<I", 0)  # optional segment store entries
    out += write_name_batch([])  # redirect/container name map
    out += struct.pack("<I", 0)  # localized packages
    out += struct.pack("<I", 0)  # package redirects
    out += b"\0"  # no soft package-reference side table
    # UE's supplied UE5.5 containers align this chunk to four bytes.  (retoc's
    # optional sixteen-byte padding is also readable, but is not byte-exact.)
    out += b"\0" * (-len(out) % 4)
    return bytes(out)


def hash_chunk_id_with_seed(seed: int, chunk_id: bytes) -> int:
    if len(chunk_id) != 12:
        raise ValueError("An IoStore chunk ID is exactly 12 bytes")
    value = (seed & MASK64) if seed else 0xCBF29CE484222325
    for byte in chunk_id:
        value = ((value * 0x00000100000001B3) & MASK64) ^ byte
    return value


@lru_cache(maxsize=1)
def perfect_hash_primes() -> tuple[int, ...]:
    """The 1,000 primes used by Unreal's GeneratePerfectHashes (2..7919)."""
    primes: list[int] = []
    candidate = 2
    while len(primes) < 1000:
        if all(candidate % prime for prime in primes if prime * prime <= candidate):
            primes.append(candidate)
        candidate += 1
    if primes[-1] != 7919:
        raise AssertionError("Unexpected prime table")
    return tuple(primes)


@dataclass
class Chunk:
    chunk_id: bytes
    data: bytes
    relative_path: str | None = None
    offset: int = 0
    meta_hash: bytes = b""
    meta_flags: int = 0

    @property
    def length(self) -> int:
        return len(self.data)


def generate_perfect_hashes(chunks: Sequence[Chunk]) -> tuple[list[Chunk], list[int], list[int]]:
    """Port of FIoStoreWriterContextImpl::GeneratePerfectHashes."""
    count = len(chunks)
    if not count:
        return [], [], []
    seed_count = max(1, math.floor(count / 2.0 + 0.5))
    buckets: list[list[int]] = [[] for _ in range(seed_count)]
    for index, chunk in enumerate(chunks):
        buckets[hash_chunk_id_with_seed(0, chunk.chunk_id) % seed_count].append(index)
    buckets.sort(key=len, reverse=True)

    free_slots = [True] * count
    output: list[Chunk | None] = [None] * count
    seeds = [0] * seed_count
    overflow: list[int] = []
    primes = perfect_hash_primes()

    for bucket in buckets:
        if len(bucket) <= 1:
            break
        bucket_hash = hash_chunk_id_with_seed(0, chunks[bucket[0]].chunk_id)
        prime_index = 0
        index_in_bucket = 0
        bucket_slots: set[int] = set()
        found = True
        while index_in_bucket < len(bucket):
            seed = primes[prime_index]
            chunk = chunks[bucket[index_in_bucket]]
            slot = hash_chunk_id_with_seed(seed, chunk.chunk_id) % count
            if not free_slots[slot] or slot in bucket_slots:
                prime_index += 1
                if prime_index == len(primes):
                    found = False
                    seeds[bucket_hash % seed_count] = -len(overflow) - count - 1
                    overflow.extend(bucket)
                    break
                index_in_bucket = 0
                bucket_slots.clear()
            else:
                bucket_slots.add(slot)
                index_in_bucket += 1
        if found:
            seed = primes[prime_index]
            seeds[bucket_hash % seed_count] = seed
            for chunk_index in bucket:
                chunk = chunks[chunk_index]
                slot = hash_chunk_id_with_seed(seed, chunk.chunk_id) % count
                if not free_slots[slot]:
                    raise AssertionError("Perfect-hash slot collision")
                free_slots[slot] = False
                output[slot] = chunk

    free_iter = (index for index, free in enumerate(free_slots) if free)
    for bucket in buckets:
        if len(bucket) != 1:
            continue
        slot = next(free_iter)
        chunk_index = bucket[0]
        chunk = chunks[chunk_index]
        bucket_hash = hash_chunk_id_with_seed(0, chunk.chunk_id)
        seeds[bucket_hash % seed_count] = -slot - 1
        free_slots[slot] = False
        output[slot] = chunk

    for overflow_position, chunk_index in enumerate(overflow):
        slot = next(free_iter)
        free_slots[slot] = False
        output[slot] = chunks[chunk_index]
        overflow[overflow_position] = slot

    if any(chunk is None for chunk in output):
        raise AssertionError("Perfect-hash generation left an empty chunk")
    return [chunk for chunk in output if chunk is not None], seeds, overflow


def lookup_chunk_index(
    chunk_id: bytes,
    chunk_ids: Sequence[bytes],
    seeds: Sequence[int],
    overflow: Sequence[int],
) -> int:
    """Resolve and verify a chunk through the serialized perfect-hash map."""
    count = len(chunk_ids)
    if not count:
        raise KeyError(chunk_id.hex())
    if not seeds:
        # Current Unreal readers also build a direct map, but accepting this
        # fallback makes validation useful for retoc's seedless containers.
        for index, candidate in enumerate(chunk_ids):
            if candidate == chunk_id:
                return index
        raise KeyError(chunk_id.hex())
    bucket = hash_chunk_id_with_seed(0, chunk_id) % len(seeds)
    seed = seeds[bucket]
    if seed < -count:
        # Overflow buckets are uncommon for these tiny containers.  A full
        # overflow scan is sufficient for independent validation.
        for index in overflow:
            if chunk_ids[index] == chunk_id:
                return index
        raise KeyError(chunk_id.hex())
    index = -seed - 1 if seed < 0 else hash_chunk_id_with_seed(seed, chunk_id) % count
    if not 0 <= index < count or chunk_ids[index] != chunk_id:
        raise KeyError(chunk_id.hex())
    return index


def _fstring(value: str) -> bytes:
    if value.isascii():
        raw = value.encode("ascii") + b"\0"
        return struct.pack("<i", len(raw)) + raw
    raw = value.encode("utf-16-le") + b"\0\0"
    return struct.pack("<i", -(len(raw) // 2)) + raw


def build_directory_index(mount_point: str, chunks: Sequence[Chunk]) -> bytes:
    """Serialize FIoDirectoryIndexResource and link files to final chunk slots."""
    directories: list[list[int]] = []
    files: list[list[int]] = []
    strings: list[str] = []

    def name_index(value: str) -> int:
        try:
            return strings.index(value)
        except ValueError:
            strings.append(value)
            return len(strings) - 1

    def ensure_root() -> int:
        if not directories:
            directories.append([INVALID, INVALID, INVALID, INVALID])
        return 0

    def ensure_dir(parent: int, value: str) -> int:
        current = directories[parent][1]
        last = INVALID
        while current != INVALID:
            if strings[directories[current][0]] == value:
                return current
            last = current
            current = directories[current][2]
        directories.append([name_index(value), INVALID, INVALID, INVALID])
        new = len(directories) - 1
        if last == INVALID:
            directories[parent][1] = new
        else:
            directories[last][2] = new
        return new

    def add_file(parent: int, value: str, chunk_index: int) -> None:
        current = directories[parent][3]
        last = INVALID
        while current != INVALID:
            if strings[files[current][0]] == value:
                raise ValueError(f"Duplicate directory-index file: {value}")
            last = current
            current = files[current][1]
        files.append([name_index(value), INVALID, chunk_index])
        new = len(files) - 1
        if last == INVALID:
            directories[parent][3] = new
        else:
            files[last][1] = new

    for chunk_index, chunk in enumerate(chunks):
        if chunk.relative_path is None:
            continue
        normalized = chunk.relative_path.replace("\\", "/").strip("/")
        parts = normalized.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"Unsafe directory-index path: {chunk.relative_path}")
        parent = ensure_root()
        for part in parts[:-1]:
            parent = ensure_dir(parent, part)
        add_file(parent, parts[-1], chunk_index)

    out = bytearray(_fstring(mount_point))
    out += struct.pack("<I", len(directories))
    for entry in directories:
        out += struct.pack("<IIII", *entry)
    out += struct.pack("<I", len(files))
    for entry in files:
        out += struct.pack("<III", *entry)
    out += struct.pack("<I", len(strings))
    for value in strings:
        out += _fstring(value)
    return bytes(out)


class OodleCompressor:
    """Minimal official OodleLZ_Compress binding (Kraken by default)."""

    def __init__(self, library_path: Path):
        import ctypes

        self._ctypes = ctypes
        self.library = ctypes.CDLL(str(library_path.expanduser().resolve()))
        self._compress = self.library.OodleLZ_Compress
        self._compress.restype = ctypes.c_ssize_t
        # Keep the complete prototype to avoid 64-bit argument truncation.
        self._compress.argtypes = [
            ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_size_t,
        ]
        self._size_needed = self.library.OodleLZ_GetCompressedBufferSizeNeeded
        self._size_needed.restype = ctypes.c_size_t
        self._size_needed.argtypes = [ctypes.c_int, ctypes.c_size_t]
        try:
            set_printf = self.library.OodleCore_Plugins_SetPrintf
            set_printf.argtypes = [ctypes.c_void_p]
            set_printf(None)
        except AttributeError:
            pass

    def compress(self, data: bytes, compressor: int = 8, level: int = 4) -> bytes:
        if not data:
            return b""
        ctypes = self._ctypes
        size = self._size_needed(compressor, len(data))
        output = ctypes.create_string_buffer(size)
        result = self._compress(
            compressor, data, len(data), output, level,
            None, None, None, None, 0,
        )
        if result <= 0 or result > size:
            raise ValueError(f"Oodle compression failed: {result} (buffer {size})")
        return output.raw[:result]


@dataclass
class WrittenContainer:
    utoc: Path
    ucas: Path
    container_id: int
    chunk_count: int
    file_count: int
    block_count: int
    compressed_bytes: int
    uncompressed_bytes: int


def write_container(
    output_base: Path,
    chunks: Sequence[Chunk],
    packages: Iterable[PackageStoreInfo],
    *,
    mount_point: str = "../../../ITR2_Gorka3/Content/",
    container_id: int | None = None,
    oodle: OodleCompressor | None = None,
    compressor: int = 8,
    compression_level: int = 4,
    block_size: int = DEFAULT_BLOCK_SIZE,
    disk_alignment: int = DEFAULT_DISK_ALIGNMENT,
) -> WrittenContainer:
    """Write ``output_base.utoc`` and ``output_base.ucas``.

    Input chunks must have ExportBundleData/BulkData IDs.  The container header
    is generated and appended automatically.  Each chunk starts at a fresh
    logical compression-block boundary, as in Unreal's writer.
    """
    if block_size <= 0 or block_size > 0xFFFFFF:
        raise ValueError("Invalid compression block size")
    output_base.parent.mkdir(parents=True, exist_ok=True)
    utoc = output_base.with_suffix(".utoc")
    ucas = output_base.with_suffix(".ucas")
    container_id = container_id_from_name(output_base.name) if container_id is None else container_id

    work = [
        Chunk(
            chunk_id=item.chunk_id,
            data=item.data,
            relative_path=item.relative_path,
        )
        for item in chunks
    ]
    ids = [item.chunk_id for item in work]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate input chunk ID")
    for item in work:
        if item.chunk_id[11] not in (EXPORT_BUNDLE_CHUNK_TYPE, BULK_DATA_CHUNK_TYPE):
            raise ValueError("write_container expects only package data chunks as input")

    header_data = build_container_header(container_id, packages)
    work.append(Chunk(make_container_header_chunk_id(container_id), header_data))

    blocks: list[tuple[int, int, int, int]] = []
    uncompressed_bytes = 0
    logical_offset = 0
    with ucas.open("wb") as cas:
        for item in work:
            item.offset = logical_offset
            item.meta_hash = blake3(item.data).digest()[:20]
            item.meta_flags = 0
            encoded_blocks: list[tuple[bytes, int, int]] = []
            # FFileIoStoreReader::ReadContainerHeader() reads this chunk
            # directly, before the normal compressed-chunk decode path.  UE
            # therefore requires the container header to be uncompressed (and
            # in its own compression blocks).  Compressing every other chunk
            # is fine, but compressing this one makes the container fail at
            # mount time even though a generic IoStore round-trip succeeds.
            allow_compression = (
                oodle is not None
                and item.chunk_id[11] != CONTAINER_HEADER_CHUNK_TYPE
            )
            for start in range(0, len(item.data), block_size):
                raw = item.data[start:start + block_size]
                method = 0
                encoded = raw
                if allow_compression:
                    candidate = oodle.compress(raw, compressor, compression_level)
                    if len(candidate) < len(raw):
                        encoded = candidate
                        method = 1
                        item.meta_flags = 1
                encoded_blocks.append((encoded, len(raw), method))
            if not encoded_blocks:
                encoded_blocks.append((b"", 0, 0))

            disk_size = sum(len(encoded) for encoded, _, _ in encoded_blocks)
            offset = cas.tell()
            if disk_alignment and disk_size:
                # Match Unreal's boundary-avoidance rule without forcing every
                # small chunk onto a fresh 4-KiB page.
                if (offset // disk_alignment) != ((offset + disk_size - 1) // disk_alignment):
                    padding = -offset % disk_alignment
                    cas.write(b"\0" * padding)
                    offset += padding
            for encoded, raw_size, method in encoded_blocks:
                block_offset = cas.tell()
                cas.write(encoded)
                blocks.append((block_offset, len(encoded), raw_size, method))
                uncompressed_bytes += raw_size
            logical_offset += (len(item.data) + block_size - 1) // block_size * block_size
        compressed_size_with_padding = cas.tell()

    work, seeds, overflow = generate_perfect_hashes(work)
    chunk_ids = [item.chunk_id for item in work]
    for chunk_id in chunk_ids:
        lookup_chunk_index(chunk_id, chunk_ids, seeds, overflow)
    directory_index = build_directory_index(mount_point, work)

    header = bytearray(144)
    header[:16] = TOC_MAGIC
    struct.pack_into(
        "<B3xIIIIIIIIIQ16sIIQII",
        header,
        16,
        8,  # EIoStoreTocVersion::ReplaceIoChunkHashWithIoHash + later versions
        144,
        len(work),
        len(blocks),
        12,
        1 if oodle is not None else 0,
        32,
        block_size,
        len(directory_index),
        1,
        container_id,
        b"\0" * 16,
        9 if oodle is not None else 8,  # Indexed, plus Compressed when applicable
        len(seeds),
        0xFFFFFFFFFFFFFFFF,
        len(overflow),
        0,
    )
    # The format above covers all fields through reserved7.  Explicit field
    # assertions guard against accidental struct-layout drift.
    if struct.unpack_from("<I", header, 20)[0] != 144:
        raise AssertionError("Bad UTOC header size")
    if struct.unpack_from("<Q", header, 56)[0] != container_id:
        raise AssertionError("Bad UTOC container ID")
    if struct.unpack_from("<I", header, 96)[0] != len(overflow):
        raise AssertionError("Bad UTOC overflow count")

    with utoc.open("wb") as toc:
        toc.write(header)
        for item in work:
            toc.write(item.chunk_id)
        for item in work:
            toc.write(item.offset.to_bytes(5, "big"))
            toc.write(len(item.data).to_bytes(5, "big"))
        for seed in seeds:
            toc.write(struct.pack("<i", seed))
        for index in overflow:
            toc.write(struct.pack("<i", index))
        for offset, compressed_size, raw_size, method in blocks:
            if max(offset, compressed_size, raw_size) >= 1 << 40:
                raise ValueError("IoStore 40-bit block field overflow")
            toc.write(offset.to_bytes(5, "little"))
            toc.write(compressed_size.to_bytes(3, "little"))
            toc.write(raw_size.to_bytes(3, "little"))
            toc.write(bytes((method,)))
        if oodle is not None:
            toc.write(b"Oodle".ljust(32, b"\0"))
        toc.write(directory_index)
        for item in work:
            toc.write(item.meta_hash)
            toc.write(bytes((item.meta_flags, 0, 0, 0)))

    return WrittenContainer(
        utoc=utoc,
        ucas=ucas,
        container_id=container_id,
        chunk_count=len(work),
        file_count=sum(item.relative_path is not None for item in work),
        block_count=len(blocks),
        compressed_bytes=compressed_size_with_padding,
        uncompressed_bytes=uncompressed_bytes,
    )
