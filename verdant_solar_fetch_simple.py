#!/usr/bin/env python3
"""
Verdant Solar — Station-Day Data Fetcher
==========================================
Fetches daily solar statistics from booking.verdantsolar.my for a given
station ID and date range, and saves the raw JSON.

Configuration (loaded in order; later sources win):
  1. verdant_config.yaml   — config file (copy verdant_config.yaml)
  2. .env                  — environment variables
  3. CLI arguments         — --station / --start / --end etc.

No authentication is required — the /api/vMongoDevice/station-day endpoint
works unauthenticated (same as the PowerShell command).

Requirements:
    pip install requests python-dotenv pyyaml

Usage:
    python verdant_solar_fetch_simple.py                         # use config
    python verdant_solar_fetch_simple.py --start 2026-07-01 --end 2026-07-05
    python verdant_solar_fetch_simple.py --station XXX --start 2026-07-01


"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

# ── CONFIG LOADING ───────────────────────────────────────────

def _find_project_root() -> Path:
    """Walk up from this script's directory to find the project root."""
    root = Path(__file__).resolve().parent
    for _ in range(10):
        if (root / "verdant_config.yaml").exists():
            return root
        parent = root.parent
        if parent == root:
            return root
        root = parent
    return Path(__file__).resolve().parent


def load_config() -> dict:
    """Load config from verdant_config.yaml + .env, return as dict."""
    try:
        import yaml
    except ImportError:
        yaml = None

    cfg = {
        "station_id": "60BHnnnnnnXnnn",
        "start_date": None,
        "end_date": None,
        "base_url": "https://booking.verdantsolar.my",
        "output_dir": "verdant_output",
    }

    root = _find_project_root()

    # 1) YAML config file
    yaml_path = root / "verdant_config.yaml"
    if yaml and yaml_path.exists():
        with open(yaml_path, encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        for k in ("station_id", "id", "start_date", "end_date", "base_url",
                   "output_dir", "use_intraday", "chart_dpi", "chart_width",
                   "chart_height"):
            if k in y:
                cfg[k] = y[k]

    # 2) Environment variables (override YAML)
    env_map = {
        "VERNANT_STATION_ID": "station_id",
        "VERNANT_START_DATE": "start_date",
        "VERNANT_END_DATE": "end_date",
        "VERNANT_BASE_URL": "base_url",
        "VERNANT_OUTPUT_DIR": "output_dir",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            cfg[cfg_key] = val

    return cfg


# ── FETCH ────────────────────────────────────────────────────

def fetch_station_day(station_id: str, start_date: str, end_date: str,
                         base_url: str = None) -> dict:
    """
    POST /api/vMongoDevice/station-day — returns the raw JSON response.
    Both station_id and id are required by the API.
    No auth headers required.
    """
    if base_url is None:
        base_url = "https://booking.verdantsolar.my"
    url = f"{base_url}/api/vMongoDevice/station-day"
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "stationId": station_id,
        
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": base_url,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    }
    resp = requests.post(url, json=body, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


# ── MAIN ─────────────────────────────────────────────────────

def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(
        description="Fetch Verdant Solar station-day data (no auth required)."
    )
    parser.add_argument("--station", default=cfg.get("station_id"),
                        help="Station ID (e.g. 60BHnnnnnnXnnn)")
    parser.add_argument("--start", default=cfg.get("start_date"),
                        help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=cfg.get("end_date"),
                        help="End date YYYY-MM-DD")
    parser.add_argument("--output-dir", default=cfg.get("output_dir"),
                        help="Output directory")
    parser.add_argument("--output", default=None,
                        help="Output JSON filename")
    parser.add_argument("--base-url", default=cfg.get("base_url"),
                        help="API base URL")
    args = parser.parse_args()

    today = date.today().isoformat()
    start = args.start or today
    end = args.end or today
    station = args.station
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Fetching station-day data for {station}")
    print(f"    Date range: {start} → {end}")
    print(f"    Endpoint: {args.base_url}/api/vMongoDevice/station-day")

    try:
        data = fetch_station_day(station, start, end, args.base_url)
    except requests.exceptions.HTTPError as e:
        print(f"[!] HTTP error: {e.response.status_code}")
        print(f"    Response: {e.response.text[:500]}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[!] Request failed: {e}")
        sys.exit(1)

    # Save raw JSON
    ts = date.today().isoformat().replace("-", "")
    filename = args.output or f"verdant_raw_{station}_{start}_to_{end}_{ts}.json"
    out_path = out_dir / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[*] Raw JSON saved to: {out_path}")
    print(f"[*] Response keys: {list(data.keys())}")
    if isinstance(data, dict) and "data" in data:
        print(f"[*] Records: {len(data['data'])}")
        for r in data["data"]:
            print(f"    {r.get('stationId')} / {r.get('day')} "
                  f"(stationData: {len(r.get('stationData', []))} points)")


if __name__ == "__main__":
    main()
