#!/usr/bin/env python3
"""
Verdant Solar — Data Visualization
====================================
Reads Verdant Solar station-day data (JSON from verdant_solar_fetch.py or
the API directly) and produces charts.

Two regimes are supported automatically:
  * Multi-day range  → daily bar charts (PV Yield, Peak Power, PV Power)
  * Single day       → intraday line charts (PV / Load / Grid / Battery)
    using the 5-min stationData points from the API response.

Configuration: read from verdant_config.yaml + .env (see docs).

Requirements:
    pip install matplotlib pandas python-dotenv pyyaml

Usage:
    python verdant_solar_viz.py                          # use config
    python verdant_solar_viz.py data/my_file.json        # specify input JSON
    python verdant_solar_viz.py data/my_file.json --out-dir charts/
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


# ── CONFIG LOADING ───────────────────────────────────

def _find_project_root() -> Path:
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
        "use_intraday": True,
        "chart_dpi": 150,
        "chart_width": 14,
        "chart_height": 5.5,
        "output_dir": "verdant_output",
        "palette": {
            "pv": "#FFB800",
            "load": "#4A90D9",
            "grid": "#FF6B35",
            "battery": "#50C878",
            "net": "#9B59B6",
        },
    }

    root = _find_project_root()

    yaml_path = root / "verdant_config.yaml"
    if yaml and yaml_path.exists():
        with open(yaml_path, encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        for k in ("use_intraday", "chart_dpi", "chart_width", "chart_height", "output_dir"):
            if k in y:
                cfg[k] = y[k]
        if "palette" in y:
            cfg["palette"].update(y["palette"])

    # Environment variables override
    env_map = {
        "VERNANT_USE_INTRADAY": "use_intraday",
        "VERNANT_CHART_DPI": "chart_dpi",
        "VERNANT_OUTPUT_DIR": "output_dir",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            cfg[cfg_key] = val

    return cfg


import os


# ── DATA EXTRACTION HELPERS ────────────────────────────

def extract_rows(raw: Any) -> List[Dict[str, Any]]:
    """
    Return a flat list of per-point dicts from the API response.
    Prefers the outer-level stationData points when available.
    """
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, list) and data:
            # Flatten: each record's stationData points become rows
            rows = []
            for rec in data:
                sd = rec.get("stationData")
                if isinstance(sd, list):
                    for pt in sd:
                        rows.append({
                            "stationId": rec.get("stationId"),
                            "day": rec.get("day"),
                            **pt,
                        })
            return rows
        for key in ("dataPoints", "data", "stationData", "rows"):
            val = raw.get(key)
            if isinstance(val, list):
                return list(val)
        for v in raw.values():
            if isinstance(v, list):
                return list(v)
    return []


def extract_daily_summary(raw: Any) -> List[Dict[str, Any]]:
    """Return per-day summary records (pvYield, peakPower etc.)."""
    out = []
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, list):
            out.extend(data)
        else:
            for key in ("dataPoints", "stationData", "rows", "stationDay"):
                val = raw.get(key)
                if isinstance(val, list):
                    out.extend(val)
                    break
    return out


def parse_ts_ms(ts_val) -> datetime:
    """Parse a millisecond-timestamp string or number to a timezone-aware datetime."""
    if ts_val is None:
        return None
    return datetime.fromtimestamp(int(ts_val) / 1000, tz=timezone.utc)


# ── CHART BUILDING ─────────────────────────────────────

def _chart_palette(cfg: dict) -> dict:
    p = cfg.get("palette", {})
    return {
        "pv": p.get("pv", "#FFB800"),
        "load": p.get("load", "#4A90D9"),
        "grid": p.get("grid", "#FF6B35"),
        "battery": p.get("battery", "#50C878"),
        "net": p.get("net", "#9B59B6"),
    }


def build_daily_bar_charts(daily_df: pd.DataFrame, station_id: str,
                            start_date: str, end_date: str,
                            out_dir: Path, cfg: dict) -> List[Path]:
    """Daily bar charts — one bar per day."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    colors = _chart_palette(cfg)
    dpi = cfg.get("chart_dpi", 150)
    w = cfg.get("chart_width", 14)
    h = cfg.get("chart_height", 5.5)

    dates = daily_df.index.tolist()
    pv_yields = daily_df["pvYield"].fillna(0).values
    peak_powers = daily_df["peakPower"].fillna(0).values
    pv_powers = daily_df["pvPower"].fillna(0).values

    # --- Chart 1: Daily PV Yield ---------------------------------------
    fig, ax = plt.subplots(figsize=(w, h))
    ax.bar(dates, pv_yields, color=colors["pv"], edgecolor="#E0A800")
    ax.set_ylabel("PV Yield (kWh)", fontsize=12)
    ax.set_title(f"Verdant Solar – Station {station_id}\nDaily PV Yield ({start_date} → {end_date})",
                 fontsize=14, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    p = out_dir / f"verdant_pv_yield_{ts}.png"
    fig.savefig(p, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)
    print(f"[*] Chart saved: {p}")

    # --- Chart 2: Daily Peak Power -------------------------------------
    fig, ax = plt.subplots(figsize=(w, h))
    ax.bar(dates, peak_powers, color=colors["grid"], edgecolor="#E05520")
    ax.set_ylabel("Peak Power (W)", fontsize=12)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_title(f"Verdant Solar – Station {station_id}\nDaily Peak Power ({start_date} → {end_date})",
                 fontsize=14, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    p = out_dir / f"verdant_peak_power_{ts}.png"
    fig.savefig(p, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)
    print(f"[*] Chart saved: {p}")

    # --- Chart 3: Daily PV Power ---------------------------------------
    fig, ax = plt.subplots(figsize=(w, h))
    ax.bar(dates, pv_powers, color=colors["load"], edgecolor="#3060A0")
    ax.set_ylabel("PV Power (W)", fontsize=12)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_title(f"Verdant Solar – Station {station_id}\nDaily PV Power ({start_date} → {end_date})",
                 fontsize=14, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    p = out_dir / f"verdant_pv_power_{ts}.png"
    fig.savefig(p, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)
    print(f"[*] Chart saved: {p}")

    return paths


def build_intraday_charts(rows: List[Dict], station_id: str,
                           day_date: str, out_dir: Path, cfg: dict) -> List[Path]:
    """
    Intraday line charts from stationData points (every ~5 min).
    One chart per metric: PV, Load, Grid, Battery, Net (Grid - Load).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    colors = _chart_palette(cfg)
    dpi = cfg.get("chart_dpi", 150)
    w = cfg.get("chart_width", 14)
    h = cfg.get("chart_height", 5.5)

    # Build DataFrame of points
    records = []
    for r in rows:
        if str(r.get("stationId") or r.get("day") or "") != day_date and str(r.get("day") or "")[:10] != day_date:
            # accept either "2026-09-01T00:00:00.000Z" or just "2026-09-01"
            if not str(r.get("day") or "").startswith(day_date):
                continue
        records.append(r)

    if not records:
        print(f"[!] No intraday points found for {day_date}")
        return []

    df = pd.DataFrame(records)
    # Convert millisecond timestamps to datetime safely (avoids pandas
    # OutOfBoundsDatetime on some platform builds where pd.to_datetime
    # with unit="ms" overflows for millisecond-scale values).
    df["dt"] = pd.to_numeric(df["time"], errors="coerce").apply(
        lambda ts: datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        if pd.notna(ts) else None
    )
    df = df.sort_values("dt")
    df = df.set_index("dt")

    titles = {
        "pv": ("PV Power (W)", colors["pv"]),
        "load": ("Load Power (W)", colors["load"]),
        "grid": ("Grid Power (W)", colors["grid"]),
        "batteryPercentage": ("Battery Level (%)", colors["battery"]),
        "net": ("Net Power (W)", colors["net"]),
    }

    for col, (ylabel, color) in titles.items():
        if col == "net":
            if "grid" not in df.columns or "load" not in df.columns:
                continue
            vals = df["grid"].fillna(0) - df["load"].fillna(0)
        elif col not in df.columns:
            continue
        else:
            vals = df[col].fillna(0)

        fig, ax = plt.subplots(figsize=(w, h))
        ax.plot(df.index, vals, color=color, linewidth=1.2, marker=".", markersize=3)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_title(f"Verdant Solar – Station {station_id}\n"
                     f"Intraday {ylabel} — {day_date}",
                     fontsize=14, fontweight="bold")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        ax.grid(alpha=0.3)
        ax.axhline(0, color="grey", linewidth=0.8)
        plt.tight_layout()
        safe_col = col.replace("Percentage", "")
        p = out_dir / f"verdant_intraday_{safe_col}_{ts}.png"
        fig.savefig(p, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
        print(f"[*] Chart saved: {p}")

    return paths


# ── MAIN ───────────────────────────────────────────────

def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(
        description="Visualize Verdant Solar station-day data."
    )
    parser.add_argument("input", nargs="?", default=None,
                        help="Path to JSON file (default: latest in verdant_output/)")
    parser.add_argument("--out-dir", default=cfg.get("output_dir"),
                        help="Output chart directory")
    parser.add_argument("--station", default="60BHnnnnnnXnnn",
                        help="Station ID for chart title")
    parser.add_argument("--id", default=None,
                        help="Monday.com item ID (e.g. 11111111111)")
    parser.add_argument("--start", default=None,
                        help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None,
                        help="End date YYYY-MM-DD")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Locate input JSON
    if args.input and Path(args.input).exists():
        with open(args.input, encoding="utf-8") as f:
            raw = json.load(f)
        source = args.input
    else:
        candidates = sorted(out_dir.glob("verdant_raw_*.json"), reverse=True)
        if not candidates:
            print("[!] No input JSON found. Pass a path or run verdant_solar_fetch.py first.")
            sys.exit(1)
        with open(candidates[0], encoding="utf-8") as f:
            raw = json.load(f)
        source = str(candidates[0])
    print(f"[*] Using data source: {source}")

    rows = extract_rows(raw)
    summaries = extract_daily_summary(raw)

    if not rows and not summaries:
        print("[!] Could not extract data from JSON.")
        print(f"    Top-level keys: {list(raw.keys()) if isinstance(raw, dict) else 'list'}")
        sys.exit(1)

    print(f"[*] Extracted {len(rows)} intraday points from {len(summaries)} day(s).")

    # Determine the day range
    if rows:
        days_present = sorted({str(r.get("day") or "")[:10] for r in rows if r.get("day")})
    else:
        days_present = sorted({str(r.get("day") or "")[:10] for r in summaries if r.get("day")})

    start = args.start or (days_present[0] if days_present else "unknown")
    end = args.end or (days_present[-1] if days_present else "unknown")
    num_days = len(days_present)
    print(f"[*] Day range: {start} → {end}  ({num_days} day(s))")

    use_intraday = cfg.get("use_intraday", True)

    if num_days == 1 and use_intraday and rows:
        # Single-day: intraday line charts
        day = days_present[0]
        build_intraday_charts(rows, args.station, day, out_dir, cfg)
    else:
        # Multi-day: daily bar charts from stationData summaries
        # Aggregate by day from the per-point rows
        daily: Dict[str, Dict[str, float]] = {}
        for r in rows:
            d = str(r.get("day") or "")[:10]
            if not d:
                continue
            if d not in daily:
                daily[d] = {"pvYield": 0.0, "peakPower": 0.0, "pvPower": 0.0,
                            "loadPower": 0.0, "gridPower": 0.0}
            for k in ("pvYield", "peakPower", "pvPower", "loadPower", "gridPower"):
                v = r.get(k)
                if v is not None:
                    try:
                        daily[d][k] += float(v)
                    except (TypeError, ValueError):
                        pass
        # Also merge summary-level values
        for s in summaries:
            d = str(s.get("day") or "")[:10]
            if not d or d not in daily:
                continue
            for k in ("pvYield", "peakPower", "pvPower"):
                v = s.get(k)
                if v is not None:
                    try:
                        daily[d][k] += float(v)
                    except (TypeError, ValueError):
                        pass

        if not daily:
            print("[!] Not enough data to generate charts.")
            sys.exit(1)

        daily_df = pd.DataFrame.from_dict(daily, orient="index")
        daily_df.index.name = "date"
        daily_df = daily_df.sort_index()

        build_daily_bar_charts(daily_df, args.station, start, end, out_dir, cfg)

    # Append id to the output filename suffix so downloaded data is identifiable
    id_suffix = f"_{args.id}" if args.id else ""
    print(f"[*] Done. Charts in {out_dir}{' (id=' + args.id + ')' if args.id else ''}")


if __name__ == "__main__":
    main()
