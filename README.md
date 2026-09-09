# Verdant Solar

Solar statistics fetcher and visualiser for the [Verdant Solar booking portal](https://booking.verdantsolar.my).

> **No authentication required.** The `/api/vMongoDevice/station-day` endpoint accepts requests with only `Content-Type` and `Referer` headers.


The API requires only requires station_id which is your inverter/datalogger serial number

| Parameter | Value | Where it lives | Used for |
|---|---|---|---|
| `station_id` | `60BHnnnnnnXnnn` | inverter station ID | **API calls** (`station-day`, `station-performance`, etc.) |
| `id` | `11111111111` | The device detail URL (`?id=...`) AND passed to the API |

Both values are required by the `/api/vMongoDevice/station-day` endpoint. Passing only `stationId` works but passing only `id` times out — always include both.

## Quick start

```bash
# 1. Install dependencies needed for visualization, skip if only fetching
pip install matplotlib pandas

# 2. Configure
cp verdant_config.yaml verdant_config.yaml       # edit station_id, id, dates, can skip if passed as cli arguments

# 3. Fetch data
python verdant_solar_fetch.py                     # uses verdant_config.yaml
python verdant_solar_fetch.py --start 2026-07-01 --end 2026-07-05   # CLI override
python verdant_solar_fetch_simple.py --station 60BHnnnnnnXnnn #no verdant_config.yaml needed, journey_id also not needed for simple version, just device serial number

# 4. Generate charts
python verdant_solar_viz.py                       # reads the latest JSON

# 5. Or open the interactive web dashboard
python verdant_solar_web.py                       # http://127.0.0.1:8765
```

## Web dashboard

One dependency-free page (`web/index.html`, plain HTML/CSS/JS, no CDN) that
auto-detects where it runs:

- **With the local server** (`python verdant_solar_web.py` →
  `http://127.0.0.1:8765`): live mode goes through the server proxy (which can
  also save snapshots to disk), and snapshots come from the output dir.
- **Static hosting** (GitHub / Cloudflare Pages, or any `python -m
  http.server`): the page calls the API **directly from the browser** — the
  upstream sends `Access-Control-Allow-Origin: *` (verified preflight +
  POST), so live mode and 5-min auto-refresh need no backend at all. Bundled
  JSON files are listed via `data/manifest.json`.
- **Date picker** — From/To range, defaults to today.
- **Auto-refresh** — live mode re-fetches every 5 minutes (toggle + countdown
  in the toolbar); optionally tick *Save snapshot* to persist each refresh
  into `verdant_output/` so it also shows up under "Downloaded JSON".
- **Charts** — daily PV-yield bars with a peak-power line, and intraday
  5-minute line charts (PV / Load / Grid / Net + Battery %) with hover
  tooltips, legend toggles, and time in ascending order.

```bash
python verdant_solar_web.py                       # defaults from verdant_config.yaml
python verdant_solar_web.py --port 9000           # pick a different port
python verdant_solar_web.py --station 60BHn... --host 0.0.0.0   # LAN-accessible
```

## Static deployment (GitHub / Cloudflare Pages)

`publish_static.py` builds a self-contained site in `_site/`: the dashboard
page plus up to `--max` (default 20) newest snapshots from `verdant_output/`
and a generated `data/manifest.json` that the page uses to populate its
"Downloaded JSON" dropdown.

```bash
python publish_static.py                  # builds ./_site
python publish_static.py --out _site --max 5
python -m http.server -d _site 8080       # preview locally
```

Because the upstream API sends `Access-Control-Allow-Origin: *`, the deployed
page keeps full **live mode** (direct browser fetch + 5-min auto-refresh)
without any server — the bundled JSON is just an optional offline/historical
source.

### GitHub Pages (auto-refreshing via Actions)

1. Copy `deploy/verdant-pages.yml.example` to
   `.github/workflows/verdant-pages.yml` (it ships as `.example` so it can't
   activate silently).
2. In repo **Settings → Pages**, set **Source = GitHub Actions**.
3. In **Settings → Secrets and variables → Actions → Variables**, add
   `VERNANT_STATION_ID` with your station serial number.
4. Push. The workflow fetches the last 14 days every 15 minutes (GitHub cron
   floor), publishes `_site/` with the official Pages Actions, and also runs
   on manual dispatch or on pushes to the listed paths.

If you commit JSON files to the repo instead, skip the fetch step and point
`upload-pages-artifact` at a directory built by `publish_static.py`.

### Cloudflare Pages

- **Direct upload:** run `python publish_static.py`, then drag the `_site/`
  folder into the Cloudflare Pages dashboard (or `wrangler pages deploy _site`).
- **Git build:** build command `pip install pyyaml && python publish_static.py
  --out _site`, output directory `_site`. The page's live mode then refreshes
  from the API on every visitor's side; commit new snapshots to update the
  bundled history.

## Configuration

| File | Purpose |
|---|---|
| `verdant_config.yaml` | `station_id`, `id`, dates, API URL, output directory, chart palette |
| CLI args (`--station`, `--start`, `--end`) | Override everything else |

### `verdant_config.yaml` fields

- `station_id` — your Solis inverter station ID (e.g. `60BHnnnnnnXnnn`)
- `id` - your journey id, visible when you select your solar journey after login
- `start_date` / `end_date` — default date range (YYYY-MM-DD)
- `base_url` — API base URL
- `output_dir` — where raw JSON + charts go
- `use_intraday` — when `true` and a single day is requested, draw 5-min line charts; otherwise draw daily bars
- `palette` — chart colours



## API response structure

A successful response looks like:

```json
{
  "success": true,
  "data": [
    {
      "_id": "60BHnnnnnnXnnn_2026-07-01",
      "stationId": "60BHnnnnnnXnnn",
      "day": "2026-07-01T00:00:00.000Z",
      "pvPower": 149.508,
      "pvYield": 12.459,
      "loadPower": 15.222,
      "gridPower": -12.652,
      "stationData": [
        {"time": "1788192008000", "pv": 0, "load": 3.211, "grid": -3.211,
         "batteryPercentage": 10, "batteryCharge": 0, "batteryDischarge": 0, "genLoad": 0},
        ...
      ],
      "updatedAt": "2026-09-01T04:59:07.951Z"
    }
  ]
}
```

- `data[].stationData` — intraday points at ~5-min intervals (millisecond timestamps)
- `pvYield` — cumulative kWh for the day
- `pvPower` / `loadPower` / `gridPower` — kW-level readings

Note: the API may return empty data (`"data": []`) for future dates — the server only stores historical data.

## Output

- `verdant_output/verdant_raw_<station>_<start>_to_<end>_<ts>.json` — raw API response
- `verdant_output/verdant_pv_yield_<ts>.png` — daily PV yield (kWh) bar chart
- `verdant_output/verdant_peak_power_<ts>.png` — daily peak power (W) bar chart
- `verdant_output/verdant_pv_power_<ts>.png` — daily PV power (W) bar chart
- `verdant_output/verdant_intraday_<metric>_<ts>.png` — intraday 5-min line charts (PV, Load, Grid, Battery, Net)


## Files

| File | Description |
|---|---|
| `verdant_solar_fetch.py` | Fetch station-day data |
| `verdant_solar_fetch_simple.py` | Fetch station-day data with just Device Serial Number |
| `verdant_solar_viz.py` | Visualise — daily bars or intraday lines |
| `verdant_solar_web.py` | Interactive web dashboard (live API + saved JSON, 5-min auto-refresh) |
| `web/index.html` | Dashboard page (plain HTML/CSS/JS, works served or static) |
| `publish_static.py` | Build a deployable static site bundle in `_site/` |
| `deploy/verdant-pages.yml.example` | GitHub Actions workflow template for auto-refreshing Pages |
| `verdant_config.yaml` | Config template |
| `.gitignore` | Git ignore rules |
