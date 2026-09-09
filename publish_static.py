#!/usr/bin/env python3
"""
Verdant Solar — Static Site Publisher
=======================================
Builds a fully static bundle of the dashboard (web/index.html + downloaded
JSON + manifest) ready for GitHub Pages or Cloudflare Pages.

The page itself works in both worlds:
  * Live mode — the upstream API sends `Access-Control-Allow-Origin: *`, so
    the browser calls it directly; 5-min auto-refresh keeps working without
    any server.
  * Snapshot mode — the dashboard reads data/manifest.json and renders the
    raw JSON copied here by this script.

Run:
    python publish_static.py                    # _site/ from verdant_output/
    python publish_static.py --out _site --max 14
    python -m http.server -d _site 8080         # preview locally
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

NAME_RE = re.compile(
    r"^verdant_raw_(?P<station>.+?)_"
    r"(?P<start>\d{4}-\d{2}-\d{2})_to_(?P<end>\d{4}-\d{2}-\d{2})"
    r"(?:_.*)?\.json$")


def build(out_dir: Path, input_dir: Path, page: Path, max_files: int) -> int:
    if not page.is_file():
        sys.exit(f"[!] dashboard page not found: {page}")
    if not input_dir.is_dir():
        sys.exit(f"[!] no input dir: {input_dir} — run a fetcher first "
                 f"(python verdant_solar_fetch_simple.py --station ...)")

    candidates = sorted(input_dir.glob("verdant_raw_*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        sys.exit(f"[!] no verdant_raw_*.json files in {input_dir}")
    if max_files > 0:
        candidates = candidates[:max_files]

    data_dir = out_dir / "data"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    data_dir.mkdir(parents=True)

    shutil.copy2(page, out_dir / "index.html")

    manifest = {"generated": datetime.now().isoformat(timespec="seconds"),
                "files": []}
    for src in candidates:
        m = NAME_RE.match(src.name)
        stat = src.stat()
        shutil.copy2(src, data_dir / src.name)
        manifest["files"].append({
            "name": src.name,
            "station": m.group("station") if m else None,
            "start": m.group("start") if m else None,
            "end": m.group("end") if m else None,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(
                stat.st_mtime).isoformat(timespec="seconds"),
        })
    with open(data_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return len(candidates)


def main():
    parser = argparse.ArgumentParser(
        description="Publish the dashboard as a static bundle.")
    parser.add_argument("--out", default="_site",
                        help="output directory (default _site)")
    parser.add_argument("--input-dir", default="verdant_output",
                        help="directory holding verdant_raw_*.json files")
    parser.add_argument("--page", default="web/index.html",
                        help="dashboard HTML to bundle")
    parser.add_argument("--max", type=int, default=20,
                        help="max snapshot files to bundle, newest first "
                             "(0 = all, default 20)")
    args = parser.parse_args()

    n = build(Path(args.out), Path(args.input_dir), Path(args.page), args.max)
    total_mb = sum(p.stat().st_size for p in Path(args.out).rglob("*")) / 1e6
    print(f"[*] Static bundle ready in {args.out}/ ({n} snapshot(s), "
          f"{total_mb:.1f} MB)")
    print("    Preview:  python -m http.server -d " + args.out + " 8080")
    print("    GitHub Pages:   publish _site/ (see deploy/verdant-pages.yml.example)")
    print("    Cloudflare Pages: upload _site/ directly, or build command "
          "'python publish_static.py --out _site' with output dir _site")


if __name__ == "__main__":
    main()
