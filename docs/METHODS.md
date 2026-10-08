# Methods

## Canopy height metric
RH98 is the height above the lowest detected ground return below which 98 % of
the waveform energy lies. It is used here as the canopy-height metric. `rh` is
stored for percentiles 0 to 100; the table keeps every 5th percentile plus 98.
If a file declares `rh` units of centimetres the reader converts to metres.

## Quality filtering (configurable)
Keep shots with `quality_flag == 1`, `degrade_flag == 0`, `sensitivity >= 0.95`
and RH98 within 0 to 120 m. NASA's tutorial uses a similar scheme and notes that
the product default is 0.9 over land, with higher sensitivity thresholds
suggested for dense forest. Counts removed by each rule are printed every run.

## Time
`delta_time` is seconds since 2018-01-01 00:00:00 UTC, converted to calendar
time and year.

## Gridding and change
Shots are binned to a regular lat/lon grid (default 0.01 degrees). Change is the
difference in per-cell median RH98 between two sets of years, for cells with at
least `--min-shots` shots in both. Footprints differ between years, so this is
an indicator, not a wall-to-wall measurement.

## Region comparison
Shots are assigned to administrative regions by point-in-polygon tests against
real boundaries. For each region the median RH98 and a 95 % percentile interval
are computed by a **cluster bootstrap** that resamples whole ground-track
segments (one beam of one granule). Neighbouring shots are spatially correlated;
resampling shots would understate uncertainty. A test in the repository shows
the cluster interval is several times wider than the naive one on correlated
data. Differences between two countries use independent cluster resampling in
each group.

## Disturbance context
Using Hansen `treecover2000` and `lossyear`:

- **State at acquisition** (per shot, using the shot's own year): `recovering`
  if loss was detected in or before that year; `non_forest_2000` if tree cover
  in 2000 was below `--tc-min` (default 30 %); otherwise `intact`.
- **Age since loss** = shot year minus loss year (recovering shots only).
- **Edge distance** = Euclidean distance (scipy EDT) from a shot's pixel to the
  nearest pixel that was cleared by the shot's year or non-forest in 2000.
  Pixel size comes from the raster; metres use 111,320 m per degree, scaled by
  cos(latitude) of the window centre for the east-west axis. Distances are capped
  at `--max-edge-m` (default 1000 m) and the window is padded to support this.
- **Edge profile** uses intact shots only. **Recovery curve** shows recovering
  shots by age bin plus an intact reference (at least 500 m from any edge).

## Model
HistGradientBoostingRegressor predicts RH98 from edge distance, age since loss,
elevation and 2000 tree cover (features missing from the data are skipped).
Two cross-validation schemes run side by side: spatial blocks (default 0.25
degrees, grouped k-fold) and random k-fold. The train-mean RMSE is reported as a
baseline. The spatial score is the honest estimate of transfer to unseen areas.

## What is verified
Unit tests cover filters, unit conversion, schema errors, gridding, change
detection, point-in-polygon (real Nigerian and Brazilian cities), cluster
bootstrap behaviour, edge distance against known geometry, the time-aware
loss logic, and the spatial-vs-random cross-validation gap. An end-to-end test
runs process, compare, disturbance and model through the command line. Tests use
fabricated shots and rasters; they establish that the code does what it says,
not what any real forest looks like.
