"""Disturbance context tests on small synthetic GeoTIFFs with known geometry.

The rasters are fabricated (the code is real rasterio / scipy). Layout, over a
0.1 x 0.1 degree box at lon -63.0..-62.9, lat -10.0..-9.9, 0.0002 deg pixels:
  * west block   lon < -62.98 : cleared in 2003 (lossyear = 3)
  * south block  lat < -9.98  : cleared in 2021 (lossyear = 21)
  * NE patch                  : tree cover 5 % (non-forest in 2000)
  * everything else           : tree cover 80 %, no loss
"""
import math

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from gedi_forest import disturbance

W, S, E, N, RES = -63.0, -10.0, -62.9, -9.9, 0.0002


def _grid():
    ncols = int(round((E - W) / RES))
    nrows = int(round((N - S) / RES))
    lon = W + (np.arange(ncols) + 0.5) * RES
    lat = N - (np.arange(nrows) + 0.5) * RES
    return np.meshgrid(lon, lat)


def _write(path, arr, left=W, top=N):
    h, w = arr.shape
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=1, dtype="uint8",
                       crs="EPSG:4326", transform=from_origin(left, top, RES, RES)) as dst:
        dst.write(arr, 1)


@pytest.fixture
def tiles(tmp_path):
    LON, LAT = _grid()
    loss = np.zeros(LON.shape, "uint8")
    loss[LON < -62.98] = 3
    loss[(LAT < -9.98) & (LON >= -62.98)] = 21
    tc = np.full(LON.shape, 80, "uint8")
    tc[(LON > -62.92) & (LAT > -9.92)] = 5
    # Write each layer as two side-by-side tiles to exercise mosaicking.
    half = LON.shape[1] // 2
    left_edge = W + half * RES
    paths = {}
    for name, arr in (("loss", loss), ("tc", tc)):
        a, b = tmp_path / f"{name}_w.tif", tmp_path / f"{name}_e.tif"
        _write(a, arr[:, :half], left=W)
        _write(b, arr[:, half:], left=left_edge)
        paths[name] = [str(a), str(b)]
    return paths


def shots(rows):
    return pd.DataFrame(rows, columns=["lon", "lat", "year", "rh98"]).assign(
        granule="g", beam="BEAM0101")


def run(tiles, rows, **kw):
    return disturbance.add_disturbance_context(shots(rows), tiles["loss"], tiles["tc"], **kw)


def test_states_and_age(tiles):
    out = run(tiles, [
        (-62.99, -9.95, 2020, 10.0),   # inside west block, cleared 2003 -> age 17
        (-62.94, -9.95, 2020, 30.0),   # intact forest
        (-62.90 - 0.005, -9.905, 2020, 5.0),  # NE patch -> non-forest
    ])
    assert list(out["state"]) == ["recovering", "intact", "non_forest_2000"]
    assert out.loc[0, "age_since_loss"] == 17
    assert out.loc[0, "loss_year"] == 2003
    assert np.isnan(out.loc[1, "age_since_loss"])


def test_loss_after_acquisition_is_not_seen_yet(tiles):
    """Pixel cleared in 2021 is intact for a 2020 shot but recovering for a 2022 shot."""
    pt = (-62.95, -9.99)
    out = run(tiles, [(*pt, 2020, 25.0), (*pt, 2022, 25.0)])
    assert out.loc[0, "state"] == "intact"
    assert out.loc[1, "state"] == "recovering"
    assert out.loc[1, "age_since_loss"] == 1


def test_edge_distance_matches_geometry(tiles):
    lat = -9.95
    lon = -62.975  # 0.005 deg east of the west block edge (-62.98)
    expected = 0.005 * 111_320 * math.cos(math.radians(lat))
    out = run(tiles, [(lon, lat, 2020, 30.0)])
    assert out.loc[0, "edge_dist_m"] == pytest.approx(expected, abs=60)


def test_edge_distance_is_censored_at_cap(tiles):
    out = run(tiles, [(-62.94, -9.95, 2020, 30.0)], max_edge_m=300)
    assert out.loc[0, "edge_dist_m"] == 300


def test_tile_boundary_is_not_mistaken_for_an_edge(tiles):
    """10 m from the raster boundary, far from any real clearing: distance unknowable."""
    out = run(tiles, [(-62.9005, -9.95, 2020, 30.0)], max_edge_m=1000)
    assert out.loc[0, "state"] == "intact"
    assert np.isnan(out.loc[0, "edge_dist_m"])


def test_known_clearing_nearer_than_boundary_is_kept(tiles):
    """Close to both the raster boundary and a real clearing: the clearing is nearer."""
    # west block edge at -62.98; shot 0.0005 deg east of it, 0.0005 deg from nothing else
    out = run(tiles, [(-62.9795, -9.95, 2020, 30.0)], max_edge_m=1000)
    assert out.loc[0, "edge_dist_m"] == pytest.approx(0.0005 * 111_320 * math.cos(math.radians(9.95)), abs=45)


def test_edge_distance_zero_inside_cleared_pixel(tiles):
    out = run(tiles, [(-62.99, -9.95, 2020, 10.0)])
    assert out.loc[0, "edge_dist_m"] == 0


def test_shot_outside_tiles_is_unassigned(tiles):
    out = run(tiles, [(-62.95, -9.95, 2020, 30.0), (-62.5, -9.5, 2020, 30.0)],
              max_edge_m=300)
    assert pd.isna(out.loc[1, "state"])
    assert np.isnan(out.loc[1, "edge_dist_m"])


def test_missing_year_column_raises(tiles):
    df = pd.DataFrame({"lon": [-62.95], "lat": [-9.95], "rh98": [30.0]})
    with pytest.raises(KeyError, match="year"):
        disturbance.add_disturbance_context(df, tiles["loss"], tiles["tc"])


def test_mismatched_grids_raise(tiles, tmp_path):
    LON, LAT = _grid()
    odd = tmp_path / "odd.tif"
    arr = np.zeros((LON.shape[0] // 2, LON.shape[1] // 2), "uint8")
    with rasterio.open(odd, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype="uint8", crs="EPSG:4326",
                       transform=from_origin(W, N, RES * 2, RES * 2)) as dst:
        dst.write(arr, 1)
    with pytest.raises(ValueError, match="grids differ"):
        disturbance.add_disturbance_context(
            shots([(-62.95, -9.95, 2020, 30.0)]), tiles["loss"], [str(odd)])


def test_profiles_show_edge_effect_and_recovery():
    rng = np.random.default_rng(0)
    rows = []
    for k in range(40):  # 40 tracks
        edge = rng.uniform(0, 1000, 60)
        h = 18 + 12 * np.minimum(edge, 400) / 400 + rng.normal(0, 1, 60)  # shorter near edges
        rows.append(pd.DataFrame({"rh98": h, "edge_dist_m": edge, "state": "intact",
                                  "age_since_loss": np.nan, "granule": f"g{k}", "beam": "b"}))
        age = rng.integers(0, 25, 60)
        h2 = 5 + 1.0 * age + rng.normal(0, 1, 60)  # recovering stands grow
        rows.append(pd.DataFrame({"rh98": h2, "edge_dist_m": 0.0, "state": "recovering",
                                  "age_since_loss": age.astype(float), "granule": f"r{k}", "beam": "b"}))
    df = pd.concat(rows, ignore_index=True)
    edge = disturbance.edge_profile(df, n_boot=100)
    assert edge["median_rh98"].iloc[0] < edge["median_rh98"].iloc[-1] - 5
    rec = disturbance.recovery_curve(df, n_boot=100)
    young, old = rec.iloc[0], rec[rec["bin"].str.startswith("16")].iloc[0]
    assert old["median_rh98"] > young["median_rh98"] + 8
    assert rec["bin"].iloc[-1].startswith("intact reference")
