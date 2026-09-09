#!/usr/bin/env python3
"""
Verdant Solar — Web Dashboard
===============================
Serves a single-page dashboard (web/index.html) that visualises station-day
data from either source:

  * Live API        — proxied through this server to avoid browser CORS
  * Downloaded JSON — verdant_raw_*.json files in the output directory

Endpoints
  GET /                      dashboard page
  GET /api/health            server defaults (station, base_url, output_dir, today)
  GET /api/data              ?station=&start=&end=[&save=1]  live fetch (save=1 also
                             writes a verdant_raw_*.json snapshot to the output dir)
  GET /api/files             list downloadable JSON files (newest first)
  GET /api/files/<name>      raw contents of one JSON file

Run:
    python verdant_solar_web.py                     # http://127.0.0.1:8765
    python verdant_solar_web.py --port 9000
    python verdant_solar_web.py --station 60BHnnnnnnXnnn --host 0.0.0.0
"""

import argparse
import json
import re
import sys
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import requests

from verdant_solar_fetch_simple import fetch_station_day, load_config

WEB_DIR = Path(__file__).resolve().parent / "web"
# Only these files may be served from the output dir (path-traversal guard).
FILE_RE = re.compile(r"^verdant_raw_[A-Za-z0-9._\-]+\.json$")

# Populated in main() and exposed to the handler via class attributes.
SERVER_CFG: dict = {}


def _snapshot_path(station: str, start: str, end: str, out_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d")
    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", station)
    return out_dir / f"verdant_raw_{safe}_{start}_to_{end}_{ts}.json"


class Handler(BaseHTTPRequestHandler):
    server_version = "VerdantSolarWeb/1.0"

    # ── helpers ──────────────────────────────────────────────
    def _send(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, status: int = 200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    # ── routes ───────────────────────────────────────────────
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            route = parsed.path.rstrip("/") or "/"
            qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

            if route == "/":
                return self._serve_index()
            if route == "/api/health":
                return self._api_health()
            if route == "/api/data":
                return self._api_data(qs)
            if route == "/api/files":
                return self._api_files()
            if route.startswith("/api/files/"):
                return self._api_file_content(unquote(route[len("/api/files/"):]))
            self._send_json({"success": False, "error": "not found"}, 404)
        except BrokenPipeError:
            pass
        except Exception as exc:  # never kill the server on a bad request
            try:
                self._send_json({"success": False, "error": str(exc)}, 500)
            except Exception:
                pass

    def _serve_index(self):
        index = WEB_DIR / "index.html"
        if not index.exists():
            return self._send_json(
                {"success": False, "error": f"missing {index}"}, 500)
        self._send(index.read_bytes(), "text/html; charset=utf-8")

    def _api_health(self):
        out_dir = Path(SERVER_CFG["output_dir"])
        files = sorted(out_dir.glob("verdant_raw_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True) \
            if out_dir.exists() else []
        self._send_json({
            "success": True,
            "station": SERVER_CFG.get("station_id"),
            "base_url": SERVER_CFG.get("base_url"),
            "output_dir": str(out_dir.resolve()),
            "today": date.today().isoformat(),
            "saved_files": len(files),
        })

    def _api_data(self, qs: dict):
        station = qs.get("station") or SERVER_CFG.get("station_id")
        start = qs.get("start") or date.today().isoformat()
        end = qs.get("end") or start
        if not station:
            return self._send_json(
                {"success": False, "error": "no station id configured"}, 400)
        for label, val in (("start", start), ("end", end)):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
                return self._send_json(
                    {"success": False,
                     "error": f"invalid {label} date: {val!r} (want YYYY-MM-DD)"},
                    400)
        try:
            data = fetch_station_day(station, start, end,
                                     SERVER_CFG.get("base_url"))
        except requests.exceptions.RequestException as exc:
            return self._send_json(
                {"success": False, "error": f"upstream request failed: {exc}"},
                502)

        if qs.get("save") == "1":
            out_dir = Path(SERVER_CFG["output_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            path = _snapshot_path(station, start, end, out_dir)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        self._send_json(data)

    def _api_files(self):
        out_dir = Path(SERVER_CFG["output_dir"])
        items = []
        if out_dir.exists():
            for p in out_dir.glob("verdant_raw_*.json"):
                stat = p.stat()
                m = re.match(r"verdant_raw_(?P<station>.+?)_(?P<start>\d{4}-"
                             r"\d{2}-\d{2})_to_(?P<end>\d{4}-\d{2}-\d{2})_", p.name)
                items.append({
                    "name": p.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime).isoformat(timespec="seconds"),
                    "station": m.group("station") if m else None,
                    "start": m.group("start") if m else None,
                    "end": m.group("end") if m else None,
                })
        items.sort(key=lambda it: it["modified"], reverse=True)
        self._send_json({"success": True, "files": items,
                         "output_dir": str(out_dir.resolve())})

    def _api_file_content(self, name: str):
        if not FILE_RE.fullmatch(name):
            return self._send_json(
                {"success": False, "error": "invalid file name"}, 400)
        path = Path(SERVER_CFG["output_dir"]) / name
        if not path.is_file():
            return self._send_json(
                {"success": False, "error": f"no such file: {name}"}, 404)
        self._send(path.read_bytes(), "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{datetime.now():%H:%M:%S}] {self.address_string()} "
                         f"{fmt % args}\n")


def main():
    file_cfg = load_config()
    parser = argparse.ArgumentParser(
        description="Serve the Verdant Solar web dashboard.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765,
                        help="port (default 8765)")
    parser.add_argument("--station", default=file_cfg.get("station_id"),
                        help="default station ID")
    parser.add_argument("--base-url", default=file_cfg.get("base_url"),
                        help="upstream API base URL")
    parser.add_argument("--output-dir", default=file_cfg.get("output_dir"),
                        help="directory containing downloaded JSON files")
    args = parser.parse_args()

    SERVER_CFG.update({
        "station_id": args.station,
        "base_url": args.base_url,
        "output_dir": args.output_dir,
    })

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[*] Verdant Solar dashboard: http://{args.host}:{args.port}/")
    print(f"    Default station: {SERVER_CFG['station_id']}")
    print(f"    Upstream API:    {SERVER_CFG['base_url']}/api/vMongoDevice/station-day")
    print(f"    Downloaded data: {Path(SERVER_CFG['output_dir']).resolve()}")
    print("[*] Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Stopped.")


if __name__ == "__main__":
    main()
