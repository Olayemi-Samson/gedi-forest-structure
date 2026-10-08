# gedi-forest-structure

Tropical forest canopy structure and change from NASA **GEDI** spaceborne lidar
(Level 2A, *Elevation and Height Metrics*).

The tool downloads GEDI footprints for any bounding box, filters them with
documented quality rules, and produces gridded canopy-height maps, per-year
statistics, mean vertical (relative-height) profiles, and a per-cell
**change map** between two periods. It is a small, transparent starting point
for linking lidar-derived forest structure to disturbance and recovery.

## Status

| Item | State |
|---|---|
| Code, CLI, unit tests | Done (`pytest`: all passing) |
| Unit tests use real GEDI data | **No.** Tests use small synthetic HDF5 files with known properties (see `tests/conftest.py`). They check the code, not the science. |
| Run on real GEDI data | See [Reproduce](#reproduce). Results will be added under `results/` with the exact command and date. |

No figure or number in this repository comes from synthetic data.

## What it does

1. **download**: searches NASA's catalogue (via the `earthaccess` library) for
   `GEDI02_A` granules over a bounding box and date range and downloads them.
2. **process**: reads the per-beam HDF5 groups, keeps shots passing quality
   filters, converts `delta_time` to calendar time, writes one table.
3. **report**: grids shots (default 0.01 degrees, about 1.1 km), summarises by
   year, computes mean relative-height profiles, and maps the change in median
   RH98 between an early and a late period.

### Quality filters (all configurable)

| Rule | Default |
|---|---|
| `quality_flag` | must equal 1 |
| `degrade_flag` | must equal 0 |
| `sensitivity` | at least 0.95 |
| RH98 range | 0 to 120 m |

Every run prints how many shots each rule removed. These defaults are common
analysis choices, not guarantees; report them with any result.

## Reproduce

Requires Python 3.10+ and a free [NASA Earthdata](https://urs.earthdata.nasa.gov)
account.

```bash
pip install -e ".[dev]"
pytest                                   # sanity check the code

# 1. Download (example box in Rondonia, Brazil; use any tropical region)
python -m gedi_forest download --bbox -63.5 -10.5 -62.0 -9.0 \
    --start 2019-04-18 --end 2023-03-01 --max-granules 12

# 2. Filter and tabulate
python -m gedi_forest process --raw data/raw --bbox -63.5 -10.5 -62.0 -9.0

# 3. Summaries, maps, change detection
python -m gedi_forest report
```

Outputs land in `results/`: `summary.json`, `grid_stats.csv`,
`yearly_summary.csv`, `mean_profile_by_year.csv`, `change_map.csv` and the PNG
figures. GEDI granules are large (often hundreds of MB each), so start with a
small `--max-granules`.

## Methods notes and limitations

- **Footprint sampling.** GEDI samples about 25 m footprints along orbit
  tracks; it does not map wall to wall. Shot locations differ between years, so
  per-cell change is an exploratory indicator and depends on `--min-shots`.
- **RH98** is the height (m) below which 98 % of waveform energy is returned,
  used here as a canopy-height metric.
- **Time coverage.** GEDI data begin in April 2019; results span only the
  years actually downloaded.
- **Not included:** forest-cover masks, edge-distance analysis, biomass
  (L4A) and model-data integration.

## Roadmap

- Join Hansen / MapBiomas forest-loss layers to separate edge, degraded and
  intact forest.
- Add GEDI L4A aboveground biomass density.
- Compare GEDI structure with outputs from a process-based ecosystem model.

## Data and citation

GEDI L2A data are distributed by NASA's LP DAAC. Cite the dataset version you
download, as listed on its LP DAAC landing page. This project is MIT licensed.
