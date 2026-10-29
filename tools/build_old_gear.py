#!/usr/bin/env python3
"""Build Old Gear IoStore mods from old-assets-debug extraction."""
import argparse
from pathlib import Path
import hashlib
import json
import zipfile
from tools.build_gorka_mod import SourceFile, validate_container, write_deterministic_zip, MOUNT_POINT
from tools.iostore_write import Chunk, PackageStoreInfo, make_chunk_id, write_container, container_id_from_name
from tools.zen_asset import parse_package
from tools.iostore_write import BULK_DATA_CHUNK_TYPE, EXPORT_BUNDLE_CHUNK_TYPE

def find_content_root(src: Path) -> Path:
    # src may be /tmp/old-assets or /tmp/old-assets/gorka-assets etc
    # Find deepest "Content" folder
    candidates = list(src.rglob("Content"))
    if not candidates:
        raise FileNotFoundError(f"No Content folder under {src}")
    # Prefer the one that has ITR2 subfolder
    for c in candidates:
        if (c / "ITR2").exists():
            return c
    return candidates[0]

def collect_files(content_root: Path):
    packages_by_stem = {}
    packages_store = []
    for p in sorted(content_root.rglob("*.uasset")):
        try:
            pkg = parse_package(p.read_bytes())
        except Exception as e:
            print(f"skip unparsable {p}: {e}")
            continue
        rel = p.relative_to(content_root).as_posix()
        stem = rel[:-7]
        packages_by_stem[stem] = pkg
        packages_store.append(PackageStoreInfo(pkg.package_name, list(pkg.imported_package_names)))
    files=[]
    for p in sorted(content_root.rglob("*")):
        if not p.is_file() or p.suffix not in (".uasset",".ubulk"):
            continue
        rel = p.relative_to(content_root).as_posix()
        stem = rel[:-len(p.suffix)]
        pkg = packages_by_stem.get(stem)
        if pkg is None:
            # ubulk without uasset? skip
            continue
        data = p.read_bytes()
        files.append(SourceFile(relative_path=rel, package_name=pkg.package_name, chunk_type=EXPORT_BUNDLE_CHUNK_TYPE if p.suffix==".uasset" else BULK_DATA_CHUNK_TYPE, data=data))
    return files, packages_store

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    src = Path(args.source)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    # Handle rar extraction weird nesting: if src contains single subdir, descend
    if not (src / "Content").exists() and not list(src.rglob("Content")):
        # maybe src is file? not
        pass
    content_root = find_content_root(src)
    print(f"Content root: {content_root}")
    files, packages = collect_files(content_root)
    print(f"Collected {len(files)} files, {len(packages)} packages from {content_root}")
    # Filter by variant
    def keep(f: SourceFile):
        s=f.relative_path.lower()
        if args.variant=="pouch_knife_detector":
            return any(k in s for k in ["pouch","knife","detector","geiger","ammunition","probe_sack"])
        elif args.variant=="vest_old":
            return any(k in s for k in ["vest","armor","platecarrier","bodyarmor","vest_base","vest_module"])
        return True
    filtered = [f for f in files if keep(f)]
    # Also need to keep packages that correspond to kept files
    keep_packages=set(f.package_name for f in filtered)
    filtered_packages=[p for p in packages if p.package_name in keep_packages]
    print(f"Filtered {len(filtered)} files, {len(filtered_packages)} packages for variant {args.variant}")
    if not filtered:
        raise SystemExit(f"No files for variant {args.variant}")

    mod_basename = "OldGear_P" if args.variant=="pouch_knife_detector" else "OldVest_P"
    if args.variant=="vest_old":
        mod_basename="OldVest_P"
    container_id = container_id_from_name(mod_basename)
    output_base = out / mod_basename
    chunks=[Chunk(make_chunk_id(f.package_name, f.chunk_type), f.data, f.relative_path) for f in filtered]
    # Need to map package store to filtered packages
    written = write_container(output_base, chunks, filtered_packages, mount_point=MOUNT_POINT, container_id=container_id, oodle=None)
    # pak stub - minimal like Gorka
    pak_stub = b""
    # Create a minimal pak: use same as Gorka's pak header? For now create empty valid pak via build_gorka_mod logic?
    # Gorka uses pak_stub from source manifest; we can create a simple one: write empty file with magic
    # For UE to mount, pak needs at least not empty: we write a minimal pak with same structure as Gorka's pak (339 bytes) - reuse if exists
    import pathlib
    # Try to copy pak from previous Gorka if exists, else create dummy
    gorka_pak = Path("release/gorka-khaki-A/Gorka3_For_All_P.pak")
    if gorka_pak.exists():
        pak_stub = gorka_pak.read_bytes()
    else:
        # minimal dummy pak (just write empty, UE will still try to read IoStore)
        pak_stub = b"PK\x05\x06" + b"\x00"*20
    (out / f"{mod_basename}.pak").write_bytes(pak_stub)
    validation = validate_container(written.utoc, written.ucas, filtered, filtered_packages, container_id)
    print(f"Validation {validation['utoc_sha256'][:8]} {validation['ucas_sha256'][:8]} size {validation['utoc_size']}/{validation['ucas_size']}")
    # Write manifest
    manifest_path = out / "build-manifest.json"
    manifest = {**validation, "variant": args.variant, "mod": mod_basename, "container_id": f"{container_id:016x}", "file_count": len(filtered)}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    # Zip
    zip_name = f"{mod_basename}.zip"
    if args.variant=="pouch_knife_detector":
        zip_name="OldGear_Pouch_Knife_Detector.zip"
    elif args.variant=="vest_old":
        zip_name="OldVest_P.zip"
    zip_path = out.parent / zip_name if out.name.startswith("old-") else Path("release") / zip_name
    # For our output structure, out is release/old-gear or release/old-vest
    if out.name=="old-gear":
        zip_path = Path("release") / "OldGear_Pouch_Knife_Detector.zip"
    elif out.name=="old-vest":
        zip_path = Path("release") / "OldVest_P.zip"
    else:
        zip_path = out / zip_name
    write_deterministic_zip(out, zip_path, mod_basename)
    print(f"Wrote {zip_path} {zip_path.stat().st_size}")
    from tools.iostore_extract import sha256_file
    print(f"sha256 {sha256_file(zip_path)}")

if __name__=="__main__":
    main()
