#!/usr/bin/env python3
"""Minimal Old Gear builder - placeholder for now, just validates old-assets structure"""
import argparse
from pathlib import Path
import json
import hashlib
import zipfile

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--output", required=True)
    args=ap.parse_args()
    src=Path(args.source)
    out=Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    files=list(src.rglob("*"))
    # Filter to relevant ones for variant
    sel=[]
    for p in files:
        if p.is_file():
            s=str(p).lower()
            if args.variant=="pouch_knife_detector":
                if any(k in s for k in ["pouch","knife","detector","geiger"]):
                    sel.append(p)
            elif args.variant=="vest_old":
                if any(k in s for k in ["vest","armor","platecarrier","bodyarmor"]):
                    sel.append(p)
    print(f"variant {args.variant} selected {len(sel)} of {len(files)} files")
    for p in sel[:20]:
        print(" ", p.relative_to(src))
    # Create a dummy zip to prove pipeline works - real IoStore building will be added after inspection
    zip_path=out / f"OldGear_{args.variant}.zip"
    with zipfile.ZipFile(zip_path,"w") as z:
        manifest={"variant":args.variant,"selected_count":len(sel),"files":[str(p.relative_to(src)) for p in sel[:50]]}
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("README.txt", f"Old Gear {args.variant} - placeholder from {len(sel)} files. Real pak/utoc will be built after full inspection.")
    print(f"Wrote {zip_path} {zip_path.stat().st_size} bytes")
    # Also create a placeholder pak stub
    (out / f"OldGear_{args.variant}.pak").write_text("placeholder")

if __name__=="__main__":
    main()
