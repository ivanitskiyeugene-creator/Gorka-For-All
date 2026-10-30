#!/usr/bin/env python3
"""Proper old->vanilla replacement: patch package headers, not just paths."""
import struct, json
from pathlib import Path
import sys
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
from tools.zen_asset import parse_package
from tools.iostore_write import write_name_batch, container_id_from_name, Chunk, PackageStoreInfo, write_container
from tools.build_gorka_mod import SourceFile, validate_container, write_deterministic_zip
from tools.iostore_write import EXPORT_BUNDLE_CHUNK_TYPE, BULK_DATA_CHUNK_TYPE
MOUNT_POINT = "../../../IntoTheRadius2/Content/"

def patch_package_to_new_name(data: bytes, new_package_name: str, remap_imports: dict) -> bytes:
    """Patch Zen package to have new package_name and remapped imports. Returns new bytes."""
    pkg = parse_package(data)
    # Build new names for own package + imports
    # Own name is pkg.package_name -> new_package_name
    # We need to rebuild name batch for the header
    # Steps: 1) rebuild imported_package_names batch
    # 2) rebuild main name batch if own name not in it
    
    # For now, we do minimal: keep own name batch, just patch imported names via existing helper
    # and patch package_name via adding new name to name batch and updating summary name index
    # This is simplified but matches what Unreal expects for IoStore override
    from tools.iostore_write import patch_imported_package_names
    # First handle imports
    old_imports = list(pkg.imported_package_names)
    new_imports = [remap_imports.get(n, n) for n in old_imports]
    if old_imports != new_imports:
        data, new_header_size = patch_imported_package_names(data, pkg.summary["imported_package_names_offset"], pkg.summary["header_size"], new_imports, pkg.imported_package_name_numbers)
        # Update header_size in data
        data = bytearray(data)
        struct.pack_into("<I", data, 4, new_header_size)
        data = bytes(data)
        pkg = parse_package(data)  # re-parse after import patch
    
    # Now patch own package name if needed
    if pkg.package_name != new_package_name:
        # Need to add new_package_name to name batch
        # Name batch is at offset after summary (cooked_header_size)
        # We have pkg.names list - add new name
        new_names = list(pkg.names)
        if new_package_name not in new_names:
            new_names.append(new_package_name)
            new_name_idx = len(new_names) - 1
        else:
            new_name_idx = new_names.index(new_package_name)
        # Rebuild name batch
        # We need hash_version from original batch
        # Re-parse original batch to get hash_version
        from tools.zen_asset import read_name_batch, Reader
        r = Reader(data)
        r.seek(28)  # after summary (has_versioning_info 4 + header_size 4 + name 4 + name_number 4 + flags 4 + cooked_header_size 4 + 3 offsets 12 = 32? Adjust)
        # Simpler: use write_name_batch with current names
        # But we need exact layout: after summary header (variable)
        # Instead, rebuild entire header prefix up to bulk_data
        # For now, just patch summary name index
        old_name_idx = pkg.summary["name"]
        if old_name_idx != new_name_idx:
            data = bytearray(data)
            struct.pack_into("<I", data, 8, new_name_idx)  # summary name at offset 8
            struct.pack_into("<I", data, 12, 0)  # name_number 0
            # Also need to update export's outer? Not needed for top-level
            data = bytes(data)
    return data

def find_content_root(src: Path):
    cands = list(src.rglob("Content"))
    for c in cands:
        if (c / "ITR2").exists():
            return c
    return cands[0] if cands else src

def collect(content_root: Path):
    pkgs={}
    store=[]
    for p in sorted(content_root.rglob("*.uasset")):
        try:
            pkg=parse_package(p.read_bytes())
        except: continue
        rel=p.relative_to(content_root).as_posix()
        key=rel[:-7] if rel.endswith(".uasset") else rel
        pkgs[key]=pkg
        store.append(PackageStoreInfo(pkg.package_name, list(pkg.imported_package_names)))
    files=[]
    for p in sorted(content_root.rglob("*")):
        if not p.is_file() or p.suffix not in (".uasset",".ubulk",".uexp"): continue
        rel=p.relative_to(content_root).as_posix()
        stem=rel[:-len(p.suffix)]
        pkg=pkgs.get(stem)
        if not pkg: continue
        files.append(SourceFile(relative_path=rel, package_name=pkg.package_name, chunk_type=EXPORT_BUNDLE_CHUNK_TYPE if p.suffix==".uasset" else BULK_DATA_CHUNK_TYPE, data=p.read_bytes()))
    return files, store

REMAPPINGS = {
    "Detector_ITR1": "Detector",
    "Probe_Sack_ITR1": "Probe_Sack",
    "Probe_Sack": "Probe_Sack",
    "Probes_Missle_ITR1": "Probes_Missle2",
    "Probes_Missle_ITR1": "Probes_Missle2",
    "ShellSack_ITR1": "ShellSack",
    "ProbesBag_ITR1": "ProbesBag",
    "Vest_ITR1": "Vest",
}

def remap_name(name: str) -> str:
    # specific first - longest first
    for old, new in [
        ("Probes_Missle_ITR1","Probes_Missle2"),
        ("T_ProbesMissle_ITR1","T_ProbesMissle"),
        ("Probes_ITR1","Probes"),
        ("Detector_ITR1","Detector"),
        ("Probe_Sack_ITR1","Probe_Sack"),
        ("ShellSack_ITR1","ShellSack"),
        ("ProbesBag_ITR1","ProbesBag"),
        ("Vest_ITR1","Vest"),
    ]:
        if old in name:
            return name.replace(old, new)
    # generic fallback: strip _ITR1 -> "" (covers any missed ITR1)
    if "_ITR1" in name:
        return name.replace("_ITR1","")
    if "_itr1" in name.lower():
        # case-insensitive strip
        import re
        return re.sub(r"_ITR1","", name, flags=re.IGNORECASE)
    return name

if __name__ == "__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--verbose", action="store_true")
    args=ap.parse_args()
    src=Path(args.source); out=Path(args.output); out.mkdir(parents=True, exist_ok=True)
    cr=find_content_root(src)
    print(f"Content root {cr}")
    files, pkgs = collect(cr)
    print(f"collected {len(files)}")
    # Filter to old sources: any _ITR1 + specific old bags/probes/vest
    filt=[]
    for f in files:
        hay=(f.relative_path+" "+f.package_name).lower()
        # generic _itr1 catch-all: detector, probes missile, shellsack, vest, etc.
        if "_itr1" in hay or "itr1" in hay:
            filt.append(f)
        elif "shellsack" in hay and "itr1" in hay:
            filt.append(f)
        elif "probesbag" in hay and "itr1" in hay:
            filt.append(f)
    # dedup
    filt = list({id(x):x for x in filt}.values())
    print(f"old files filtered {len(filt)} (generic _ITR1)")
    # Knife: old knife is ITR2/BPs/Items/Melee/BP_knife.uasset (no ITR1 suffix, but old version in dump)
    # Include any knife asset from old dump – it will override vanilla directly (no remap needed)
    knife_added=0
    for f in files:
        low=f.package_name.lower()
        low_rel=f.relative_path.lower()
        if "knife" in low:
            if f not in filt:
                filt.append(f); knife_added+=1
        # Probes / shellsack explicit extra (in case _itr1 filter missed due to naming)
        if any(k in low for k in ["probes_missle","probes_missile","shellsack","probesbag","probes_01","vest_itr1"]):
            if "itr1" in low and f not in filt:
                filt.append(f); knife_added+=1
        # Old vest Gorka etc – include if ITR1
        if "vest" in low and "itr1" in low and f not in filt:
            filt.append(f); knife_added+=1
    print(f"with knife+probes+vest {len(filt)} (+{knife_added})")
    # Now remap each to vanilla path and patch data
    remapped_files=[]
    remap_imports={}
    for f in filt:
        # build preview of remap via remap_name on path/pkg
        new_rel = remap_name(f.relative_path)
        new_pkg_name = remap_name(f.package_name)
        pass
    # Collect all imports to build remap (skip versioned packages gracefully)
    all_imports=set()
    for f in filt:
        try:
            pkg=parse_package(f.data)
        except Exception as e:
            print(f" skip import collect {f.relative_path}: {e}")
            continue
        for n in pkg.imported_package_names:
            all_imports.add(n)
    remap_dict={}
    for n in all_imports:
        rn=remap_name(n)
        if rn!=n:
            remap_dict[n]=rn
            print(f" import remap {n} -> {rn}")
    print(f"remap dict {len(remap_dict)}")
    # Now create remapped files with patched data
    out_files=[]
    out_pkgs=[]
    seen_pkgs=set()
    for f in filt:
        is_bulk = f.relative_path.lower().endswith((".ubulk",".uexp"))
        new_rel = remap_name(f.relative_path)
        new_pkg_name = remap_name(f.package_name)
        if is_bulk:
            # bulk has no header – just rename, keep data verbatim, don't store as package
            out_files.append(SourceFile(relative_path=new_rel, package_name=new_pkg_name, chunk_type=f.chunk_type, data=f.data))
            continue
        # uasset – try patch
        try:
            parse_package(f.data)
            can_patch = True
        except:
            can_patch = False
        if can_patch:
            try:
                new_data = patch_package_to_new_name(f.data, new_pkg_name, remap_dict)
            except Exception as e:
                print(f"patch fail {f.relative_path}: {e}")
                new_data=f.data
        else:
            print(f" versioned, copy raw {f.relative_path} -> {new_rel}")
            new_data=f.data
        out_files.append(SourceFile(relative_path=new_rel, package_name=new_pkg_name, chunk_type=f.chunk_type, data=new_data))
        if new_pkg_name not in seen_pkgs:
            try:
                pkg2=parse_package(new_data)
                out_pkgs.append(PackageStoreInfo(new_pkg_name, [remap_dict.get(n,n) for n in pkg2.imported_package_names]))
            except:
                try:
                    orig=parse_package(f.data)
                    out_pkgs.append(PackageStoreInfo(new_pkg_name, [remap_dict.get(n,n) for n in orig.imported_package_names]))
                except:
                    out_pkgs.append(PackageStoreInfo(new_pkg_name, []))
            seen_pkgs.add(new_pkg_name)
    print(f"remapped {len(out_files)} files {len(out_pkgs)} pkgs")
    for f in out_files[:20]:
        print(f"  {f.relative_path} -> {f.package_name}")
    # Write container - DLC-Black pirate mod (private)
    mod="DLC-Black_P"
    cid=container_id_from_name(mod)
    base=out/mod
    chunks=[Chunk(__import__('tools.iostore_write', fromlist=['make_chunk_id']).make_chunk_id(f.package_name,f.chunk_type), f.data, f.relative_path) for f in out_files]
    from tools.iostore_write import make_chunk_id
    chunks=[Chunk(make_chunk_id(f.package_name,f.chunk_type), f.data, f.relative_path) for f in out_files]
    written=write_container(base, chunks, out_pkgs, mount_point=MOUNT_POINT, container_id=cid, oodle=None)
    print(f"written {written.utoc} {written.ucas} chunks={written.chunk_count} mount={MOUNT_POINT}")
    # patch validator mount for IntoTheRadius2 override
    import tools.build_gorka_mod as _bgm
    _orig_mount=_bgm.MOUNT_POINT
    _bgm.MOUNT_POINT=MOUNT_POINT
    try:
        v=validate_container(written.utoc, written.ucas, out_files, out_pkgs, cid)
    finally:
        _bgm.MOUNT_POINT=_orig_mount
    print(f"validate OK utoc={v['utoc_sha256'][:12]}")
    (out/"build-manifest.json").write_text(json.dumps({**v,"mod":mod}, ensure_ascii=False, indent=2))
    # Pak stub
    import shutil
    pak_dst=out/f"{mod}.pak"
    for cand in [Path("release/gorka-khaki-A/Gorka3_For_All_P.pak"), Path("release/Gorka3_For_All_Brown_A_NO_GLOVES.zip")]:
        if cand.exists():
            if cand.suffix==".zip":
                import zipfile
                with zipfile.ZipFile(cand) as zf:
                    for n in zf.namelist():
                        if n.endswith(".pak"):
                            pak_dst.write_bytes(zf.read(n)); break
                    break
            else:
                shutil.copyfile(cand, pak_dst); break
    if not pak_dst.exists() or pak_dst.stat().st_size==0:
        pak_dst.write_bytes(b"")
    readme=out/"ReadMe_RU.txt"
    readme.write_text(f"DLC-Black (private): vanilla Detector/Probes/ShellSack/Vest replaced with ITR1 originals (patched headers) - IntoTheRadius2/Content override\nНе для публикации\n", encoding="utf-8")
    zipname="DLC-Black.zip"
    zpath=Path("release")/zipname
    write_deterministic_zip(out, zpath, mod)
    import shutil as _sh
    _sh.copyfile(zpath, Path("release")/"OldGear_Pouch_Knife_Detector.zip")
    _sh.copyfile(zpath, Path("release")/"OldProbe_Detector_Patched.zip")
    print(f"ZIP {zpath} {zpath.stat().st_size}")
