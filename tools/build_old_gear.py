#!/usr/bin/env python3
"""Build Old Gear IoStore container from extracted assets (debug/standalone)."""
import argparse, json, shutil, sys
from pathlib import Path
# ensure repo root is on sys.path so `tools.*` imports work regardless of PYTHONPATH
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
# also support case where tools is a package dir itself
_tools_parent = str(_repo_root / "tools")
if _tools_parent not in sys.path:
    sys.path.insert(0, _tools_parent)
from tools.build_gorka_mod import SourceFile, validate_container, write_deterministic_zip, MOUNT_POINT
from tools.iostore_write import Chunk, PackageStoreInfo, make_chunk_id, write_container, container_id_from_name
from tools.zen_asset import parse_package
from tools.iostore_write import BULK_DATA_CHUNK_TYPE, EXPORT_BUNDLE_CHUNK_TYPE

def find_content_root(src: Path):
    print(f"[find_content_root] src={src} exists={src.exists()} is_dir={src.is_dir() if src.exists() else 'N/A'}", flush=True)
    if src.is_file():
        print(f"src is file, parent={src.parent}", flush=True)
        src = src.parent
    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")
    # direct check: src/Content/ITR2
    if (src / "Content" / "ITR2").exists():
        print(f"found direct Content/ITR2 at {src / 'Content'}", flush=True)
        return src / "Content"
    if (src / "ITR2").exists() and src.name == "Content":
        return src
    cands = list(src.rglob("Content"))
    print(f"rglob Content candidates: {cands[:10]}", flush=True)
    if not cands:
        # fallback: list top
        print(f"src top listing:", flush=True)
        for p in src.iterdir():
            print(f"  {p} dir={p.is_dir()}", flush=True)
        # deep search for ITR2
        for p in src.rglob("ITR2"):
            if p.is_dir():
                print(f"found ITR2 at {p}, using parent Content={p.parent}", flush=True)
                if p.parent.name == "Content":
                    return p.parent
        raise FileNotFoundError(f"No Content in {src}")
    # prefer one with ITR2
    for c in cands:
        if (c / "ITR2").exists():
            print(f"selected Content with ITR2: {c}", flush=True)
            return c
    print(f"no ITR2, using first Content: {cands[0]}", flush=True)
    return cands[0]

def collect(content_root: Path, verbose=False):
    pkgs={}
    store=[]
    uassets = list(sorted(content_root.rglob("*.uasset")))
    print(f"collect: found {len(uassets)} .uasset under {content_root}", flush=True)
    for p in uassets:
        try:
            pkg=parse_package(p.read_bytes())
        except Exception as e:
            if verbose:
                print(f" skip {p} {e}", flush=True)
            continue
        rel=p.relative_to(content_root).as_posix()
        # strip .uasset suffix (7 chars)
        key = rel[:-7] if rel.endswith(".uasset") else rel
        pkgs[key]=pkg
        store.append(PackageStoreInfo(pkg.package_name, list(pkg.imported_package_names)))
    files=[]
    all_files = list(sorted(content_root.rglob("*")))
    print(f"collect: total rglob * = {len(all_files)}", flush=True)
    for p in all_files:
        if not p.is_file():
            continue
        if p.suffix not in (".uasset", ".ubulk"):
            continue
        rel=p.relative_to(content_root).as_posix()
        stem=rel[:-len(p.suffix)]
        pkg=pkgs.get(stem)
        if not pkg:
            if verbose and len(files) < 5:
                pass
            continue
        files.append(SourceFile(relative_path=rel, package_name=pkg.package_name, chunk_type=EXPORT_BUNDLE_CHUNK_TYPE if p.suffix==".uasset" else BULK_DATA_CHUNK_TYPE, data=p.read_bytes()))
    return files, store

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--verbose", action="store_true")
    args=ap.parse_args()
    src=Path(args.source)
    out=Path(args.output); out.mkdir(parents=True, exist_ok=True)
    print(f"START variant={args.variant} src={src} out={out} verbose={args.verbose}", flush=True)
    if src.exists() and src.is_dir():
        print(f"src top: {list(src.iterdir())[:20]}", flush=True)
        # also check /tmp/old-assets specifically
        import os
        for root, dirs, files in os.walk(src):
            depth = root.replace(str(src), "").count(os.sep)
            if depth > 3:
                continue
            print(f" walk {root}: dirs={dirs[:10]} files={files[:5]}", flush=True)
            if len(dirs) > 20:
                break
    cr=find_content_root(src)
    print(f"Content root = {cr}", flush=True)
    files, pkgs = collect(cr, verbose=args.verbose)
    print(f"collected {len(files)} files, {len(pkgs)} package store entries", flush=True)
    if args.verbose:
        for f in files[:30]:
            print(f"  file {f.relative_path} pkg={f.package_name}", flush=True)

    def keep(f):
        s=f.relative_path.lower()
        n=f.package_name.lower()
        hay = s + " " + n
        if args.variant=="pouch_knife_detector":
            keys=["pouch","knife","detector","geiger","ammunition","probe_sack","holster","closablepouch","drop_pouch","ammopouch","magpouch","sack","drop_pouch","pouches"]
            return any(k in hay for k in keys)
        if args.variant=="vest_old":
            keys=["vest","armor","platecarrier","bodyarmor","vest_base","vest_module"]
            return any(k in hay for k in keys)
        return True

    filt=[f for f in files if keep(f)]
    keep_names=set(f.package_name for f in filt)
    filt_pkgs=[p for p in pkgs if p.package_name in keep_names]
    print(f"filtered {len(filt)} files, {len(filt_pkgs)} pkgs for variant {args.variant}", flush=True)
    for f in filt[:30]:
        print(f" keep {f.relative_path} pkg={f.package_name}", flush=True)
    if not filt:
        print("NO FILES MATCHED FILTER - dumping all relative paths (first 100):", flush=True)
        for f in files[:100]:
            print(f"  ALL {f.relative_path} pkg={f.package_name}", flush=True)
        # also dump package names
        for p in pkgs[:30]:
            print(f"  PKG {p.package_name}", flush=True)
        print("FILTER FAILED - exiting 1", flush=True)
        sys.exit(1)

    mod="OldGear_P" if args.variant=="pouch_knife_detector" else "OldVest_P"
    cid=container_id_from_name(mod)
    print(f"mod={mod} container_id={cid:016x}", flush=True)
    base=out/mod
    chunks=[Chunk(make_chunk_id(f.package_name,f.chunk_type), f.data, f.relative_path) for f in filt]
    written=write_container(base, chunks, filt_pkgs, mount_point=MOUNT_POINT, container_id=cid, oodle=None)
    print(f"write_container done: utoc={written.utoc} ucas={written.ucas} chunks={written.chunk_count}", flush=True)
    # Pak stub: reuse existing Gorka pak if present, else write minimal stub
    pak_src_candidates=[
        Path("release/gorka-khaki-A/Gorka3_For_All_P.pak"),
        Path("release/gorka-brown-fixed-gloves/Gorka3_For_All_P.pak"),
        Path("work/original_mod/Gorka3_P.pak"),
    ]
    pak_dst = out / f"{mod}.pak"
    copied=False
    for cand in pak_src_candidates:
        if cand.exists():
            shutil.copyfile(cand, pak_dst)
            print(f"copied pak stub from {cand} -> {pak_dst} size={pak_dst.stat().st_size}", flush=True)
            copied=True
            break
    if not copied:
        # minimal IoStore pak is just an empty pak file; game needs .pak alongside .utoc/.ucas
        # write minimal valid pak stub (reuse Gorka logic: empty pak with no entries)
        pak_dst.write_bytes(b"")
        print(f"no pak stub found, wrote empty pak at {pak_dst}", flush=True)
    v=validate_container(written.utoc, written.ucas, filt, filt_pkgs, cid)
    print(f"validate OK utoc={v['utoc_sha256'][:12]} ucas={v['ucas_sha256'][:12]} chunks={v['chunk_count']}", flush=True)
    (out/"build-manifest.json").write_text(json.dumps({**v,"variant":args.variant,"mod":mod}, ensure_ascii=False, indent=2))
    # Ensure ReadMe exists for write_deterministic_zip (expects 5 files)
    readme = out / "ReadMe_RU.txt"
    if not readme.exists():
        readme.write_text(
            f"Old Gear mod {mod} — pouch/knife/detector (IoStore)\n"
            f"Установка: скопируйте {mod}.pak/.utoc/.ucas в IntoTheRadius2/Content/Paks/\n"
            f"Содержит {len(filt)} файлов, {len(filt_pkgs)} пакетов, chunks={v['chunk_count']}.\n"
            f"validate: utoc={v['utoc_sha256'][:16]} ucas={v['ucas_sha256'][:16]}\n",
            encoding="utf-8"
        )
        print(f"wrote {readme}", flush=True)
    # Fix empty pak: if pak is 0 bytes, replace with minimal valid stub from any existing release zip
    if pak_dst.stat().st_size == 0:
        # try to extract pak from any existing Gorka zip in release/
        for z in sorted(Path("release").glob("*.zip")):
            try:
                import zipfile as zf
                with zf.ZipFile(z) as zfobj:
                    for n in zfobj.namelist():
                        if n.endswith(".pak"):
                            data = zfobj.read(n)
                            pak_dst.write_bytes(data)
                            print(f"replaced empty pak with {n} from {z} size={len(data)}", flush=True)
                            copied = True
                            break
                    if copied:
                        break
            except Exception as e:
                print(f"skip zip {z}: {e}", flush=True)
                continue
        if pak_dst.stat().st_size == 0:
            # fallback: write minimal pak header (UE pak magic)
            pak_dst.write_bytes(b"\x50\x41\x4B\x00" + b"\x00"*100)
            print(f"wrote minimal pak stub size={pak_dst.stat().st_size}", flush=True)
    zipname="OldGear_Pouch_Knife_Detector.zip" if args.variant=="pouch_knife_detector" else "OldVest_P.zip"
    zpath=Path("release")/zipname
    zpath.parent.mkdir(parents=True, exist_ok=True)
    write_deterministic_zip(out, zpath, mod)
    from tools.iostore_extract import sha256_file
    print(f"ZIP {zpath} size={zpath.stat().st_size} sha={sha256_file(zpath)}", flush=True)
    print(f"output dir listing:", flush=True)
    for p in sorted(out.iterdir()):
        print(f"  {p.name} {p.stat().st_size} bytes", flush=True)
    print("DONE", flush=True)

if __name__=="__main__":
    main()
