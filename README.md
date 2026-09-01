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
```

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
| `verdant_config.yaml` | Config template |
| `.gitignore` | Git ignore rules |
