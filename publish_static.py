#!/usr/bin/env python3
"""
Verdant Solar — Static Site Publisher
=======================================
Builds a fully static bundle of the dashboard (web/index.html + optional
downloaded JSON + manifest) ready for GitHub Pages, Cloudflare Pages, or any
static host — no backend, no CI, no user input.

The page itself works in both worlds:
  * Live mode — the upstream API sends `Access-Control-Allow-Origin: *`, so
    the browser calls it directly; 5-min auto-refresh keeps working without
    any server.
  * Snapshot mode (optional) — raw JSON files from verdant_output/ are
    copied here and listed via data/manifest.json.

The station ID is read from verdant_config.yaml (or --station) and baked
into the page as a default, so the deployed site needs no user input.

Run:
    python publish_static.py                    # _site/ (station from config)
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

STATION_RE = re.compile(r"^\s*station_id\s*:\s*['\"]?([^'\"\n#]+?)\s*(?:#.*)?$",
                        re.MULTILINE)


def read_station(root: Path) -> str:
    """Pull station_id out of verdant_config.yaml without needing pyyaml."""
    cfg = root / "verdant_config.yaml"
    if not cfg.is_file():
        return ""
    m = STATION_RE.search(cfg.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def build(out_dir: Path, input_dir: Path, page: Path, max_files: int,
          station: str) -> int:
    if not page.is_file():
        sys.exit(f"[!] dashboard page not found: {page}")

    candidates = []
    if input_dir.is_dir():
        candidates = sorted(input_dir.glob("verdant_raw_*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if max_files > 0:
            candidates = candidates[:max_files]

    data_dir = out_dir / "data"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    data_dir.mkdir(parents=True)

    html = page.read_text(encoding="utf-8")
    if station:
        defaults = ("<script>window.VERNANT_DEFAULTS="
                    + json.dumps({"station": station}) + ";</script>\n</head>")
        html = html.replace("</head>", defaults, 1)
    (out_dir / "index.html").write_text(html, encoding="utf-8")

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
                        help="directory holding verdant_raw_*.json files "
                             "(optional — skipped if missing/empty)")
    parser.add_argument("--page", default="web/index.html",
                        help="dashboard HTML to bundle")
    parser.add_argument("--max", type=int, default=20,
                        help="max snapshot files to bundle, newest first "
                             "(0 = all, default 20)")
    parser.add_argument("--station", default=None,
                        help="station ID baked into the page "
                             "(default: read from verdant_config.yaml)")
    args = parser.parse_args()

    station = args.station or read_station(Path(__file__).resolve().parent)
    n = build(Path(args.out), Path(args.input_dir), Path(args.page),
              args.max, station)
    total_mb = sum(p.stat().st_size for p in Path(args.out).rglob("*")) / 1e6
    print(f"[*] Static bundle ready in {args.out}/ ({n} snapshot(s), "
          f"{total_mb:.1f} MB)")
    if station:
        print(f"[*] Station ID baked in: {station}")
    else:
        print("[!] No station_id found (verdant_config.yaml) — visitors "
              "will need to type it once in the page.")
    print("    Preview:  python -m http.server -d " + args.out + " 8080")
    print("    Deploy:   upload this folder to Cloudflare Pages, or commit "
          "its contents to the branch GitHub Pages serves")


if __name__ == "__main__":
    main()
