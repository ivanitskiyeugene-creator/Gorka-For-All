#!/usr/bin/env python3
import argparse, json, zipfile
from pathlib import Path
from tools.build_gorka_mod import SourceFile, validate_container, write_deterministic_zip, MOUNT_POINT
from tools.iostore_write import Chunk, PackageStoreInfo, make_chunk_id, write_container, container_id_from_name
from tools.zen_asset import parse_package
from tools.iostore_write import BULK_DATA_CHUNK_TYPE, EXPORT_BUNDLE_CHUNK_TYPE

def find_content_root(src: Path):
    # brute force: find any Content with ITR2
    cands = list(src.rglob("Content"))
    print(f"candidates for Content: {cands[:5]}")
    if not cands:
        # list src
        print(f"src list: {list(src.iterdir())[:10]}")
        for p in src.rglob("*"):
            if p.is_dir() and p.name=="Content":
                cands.append(p)
                break
        if not cands:
            raise FileNotFoundError(f"No Content in {src}, tree: {list(src.rglob('*'))[:20]}")
    for c in cands:
        if (c / "ITR2").exists():
            return c
    return cands[0]

def collect(content_root: Path):
    pkgs={}
    store=[]
    for p in sorted(content_root.rglob("*.uasset")):
        try:
            pkg=parse_package(p.read_bytes())
        except Exception as e:
            print(f"skip {p} {e}")
            continue
        rel=p.relative_to(content_root).as_posix()
        pkgs[rel[:-7]]=pkg
        store.append(PackageStoreInfo(pkg.package_name, list(pkg.imported_package_names)))
    files=[]
    for p in sorted(content_root.rglob("*")):
        if not p.is_file() or p.suffix not in (".uasset",".ubulk"):
            continue
        rel=p.relative_to(content_root).as_posix()
        stem=rel[:-len(p.suffix)]
        pkg=pkgs.get(stem)
        if not pkg:
            continue
        files.append(SourceFile(relative_path=rel, package_name=pkg.package_name, chunk_type=EXPORT_BUNDLE_CHUNK_TYPE if p.suffix==".uasset" else BULK_DATA_CHUNK_TYPE, data=p.read_bytes()))
    return files, store

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--output", required=True)
    args=ap.parse_args()
    src=Path(args.source)
    out=Path(args.output); out.mkdir(parents=True, exist_ok=True)
    print(f"START {args.variant} src={src} exists={src.exists()}")
    if src.is_dir():
        print(f"src top: {list(src.iterdir())[:10]}")
    cr=find_content_root(src)
    print(f"Content root {cr}")
    files, pkgs = collect(cr)
    print(f"collected {len(files)} files {len(pkgs)} pkgs")
    # filter
    def keep(f):
        s=f.relative_path.lower()
        if args.variant=="pouch_knife_detector":
            return any(k in s for k in ["pouch","knife","detector","geiger","ammunition","probe_sack","holster","closablepouch","drop_pouch","ammopouch","magpouch"])
        if args.variant=="vest_old":
            return any(k in s for k in ["vest","armor","platecarrier","bodyarmor","vest_base","vest_module"])
        return True
    filt=[f for f in files if keep(f)]
    keep_names=set(f.package_name for f in filt)
    filt_pkgs=[p for p in pkgs if p.package_name in keep_names]
    print(f"filtered {len(filt)} files {len(filt_pkgs)} pkgs")
    for f in filt[:15]:
        print(f" keep {f.relative_path}")
    if not filt:
        print("NO FILES - dumping all relative paths for debug")
        for f in files[:50]:
            print(f.relative_path)
        raise SystemExit("no files matched filter")
    mod="OldGear_P" if args.variant=="pouch_knife_detector" else "OldVest_P"
    cid=container_id_from_name(mod)
    base=out/mod
    chunks=[Chunk(make_chunk_id(f.package_name,f.chunk_type), f.data, f.relative_path) for f in filt]
    written=write_container(base, chunks, filt_pkgs, mount_point=MOUNT_POINT, container_id=cid, oodle=None)
    gopak=Path("release/gorka-khaki-A/Gorka3_For_All_P.pak")
    pak=gopak.read_bytes() if gopak.exists() else b"PK\x05\x06"+b"\x00"*20
    (out/f"{mod}.pak").write_bytes(pak)
    v=validate_container(written.utoc, written.ucas, filt, filt_pkgs, cid)
    print(f"validate {v['utoc_sha256'][:8]} {v['ucas_sha256'][:8]}")
    (out/"build-manifest.json").write_text(json.dumps({**v,"variant":args.variant,"mod":mod}, ensure_ascii=False, indent=2))
    zipname="OldGear_Pouch_Knife_Detector.zip" if args.variant=="pouch_knife_detector" else "OldVest_P.zip"
    zpath=Path("release")/zipname
    write_deterministic_zip(out, zpath, mod)
    from tools.iostore_extract import sha256_file
    print(f"ZIP {zpath} {zpath.stat().st_size} {sha256_file(zpath)}")

if __name__=="__main__":
    main()
