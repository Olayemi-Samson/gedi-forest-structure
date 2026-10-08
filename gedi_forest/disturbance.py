"""Link GEDI shots to forest-loss history: regrowth age and distance to edge.

Inputs are Hansen et al. Global Forest Change rasters (30 m):
  * ``treecover2000``: percent tree canopy cover in 2000 (0-100)
  * ``lossyear``: 0 = no loss, 1..N = year of stand-replacement loss (2000 + N)

Both layers can be supplied as several tiles. The temporal logic matters: a
shot acquired in 2020 only "sees" loss that happened up to 2020. Pixels cleared
in 2022 are still intact forest from the point of view of that shot.

Distances are approximate (pixel size scaled to metres at the window's centre
latitude) and are censored at ``max_edge_m``. "Non-forest" means tree cover below
``tc_min`` in 2000, which includes water and natural openings, not only clearing.
Areas outside the supplied tiles are treated as unknown: shots whose edge distance
cannot be established because unknown territory is nearer than any known clearing
get NaN.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from scipy import ndimage

from .compare import cluster_bootstrap_median

M_PER_DEG = 111_320.0
HANSEN_BASE_YEAR = 2000

EDGE_BINS = (0, 50, 100, 200, 300, 500, 1000)
AGE_BINS = (0, 3, 6, 11, 16, 26)


def _mosaic(paths, bounds):
    srcs = [rasterio.open(p) for p in paths]
    try:
        arr, tf = merge(srcs, bounds=bounds, nodata=0)
    finally:
        for s in srcs:
            s.close()
    return arr[0], tf


def _covered(paths, lon, lat) -> np.ndarray:
    ok = np.zeros(lon.shape, dtype=bool)
    for p in paths:
        with rasterio.open(p) as s:
            b = s.bounds
            ok |= (lon >= b.left) & (lon < b.right) & (lat > b.bottom) & (lat <= b.top)
    return ok


def _coverage(paths, tf, shape) -> np.ndarray:
    """Boolean grid of the window that is actually covered by the supplied tiles."""
    cov = np.zeros(shape, dtype=bool)
    for p in paths:
        with rasterio.open(p) as s:
            b = s.bounds
        c0 = int(round((b.left - tf.c) / tf.a))
        c1 = int(round((b.right - tf.c) / tf.a))
        r0 = int(round((tf.f - b.top) / (-tf.e)))
        r1 = int(round((tf.f - b.bottom) / (-tf.e)))
        r0, r1 = max(r0, 0), min(r1, shape[0])
        c0, c1 = max(c0, 0), min(c1, shape[1])
        if r1 > r0 and c1 > c0:
            cov[r0:r1, c0:c1] = True
    return cov


def add_disturbance_context(
    df: pd.DataFrame,
    lossyear_paths: list[str],
    treecover_paths: list[str],
    tc_min: float = 30.0,
    max_edge_m: float = 1000.0,
    max_pixels: int = 100_000_000,
) -> pd.DataFrame:
    """Add treecover2000, loss_year, age_since_loss, state and edge_dist_m.

    state is one of: ``intact`` (forest in 2000, no loss yet at acquisition),
    ``recovering`` (loss detected on or before acquisition year),
    ``non_forest_2000`` (tree cover below ``tc_min`` in 2000).
    Shots outside every supplied tile get NaN / None.
    """
    if "year" not in df.columns:
        raise KeyError("Shots need a 'year' column (run `process`, which adds it).")
    out = df.copy()
    lon = out["lon"].to_numpy(float)
    lat = out["lat"].to_numpy(float)

    pad = 1.2 * max_edge_m / M_PER_DEG
    bounds = (lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad)

    loss, tf = _mosaic(lossyear_paths, bounds)
    tc, tf2 = _mosaic(treecover_paths, bounds)
    if loss.shape != tc.shape:
        raise ValueError(f"lossyear {loss.shape} and treecover {tc.shape} grids differ; "
                         "use tiles from the same product version.")
    if loss.size > max_pixels:
        raise ValueError(f"Window has {loss.size:,} pixels (limit {max_pixels:,}). "
                         "Use a smaller bounding box or process tiles separately.")

    res_x, res_y = tf.a, -tf.e
    lat_c = 0.5 * (bounds[1] + bounds[3])
    dy_m = res_y * M_PER_DEG
    dx_m = res_x * M_PER_DEG * math.cos(math.radians(lat_c))

    col = np.floor((lon - tf.c) / tf.a).astype(int)
    row = np.floor((lat - tf.f) / tf.e).astype(int)
    inside = (_covered(lossyear_paths, lon, lat) & _covered(treecover_paths, lon, lat)
              & (row >= 0) & (row < loss.shape[0]) & (col >= 0) & (col < loss.shape[1]))
    r = np.clip(row, 0, loss.shape[0] - 1)
    c = np.clip(col, 0, loss.shape[1] - 1)

    ly = loss[r, c].astype(float)
    tcv = tc[r, c].astype(float)
    y_rel = (out["year"].to_numpy() - HANSEN_BASE_YEAR).astype(float)

    lost_by_then = (ly > 0) & (ly <= y_rel)
    age = np.where(lost_by_then, y_rel - ly, np.nan)
    state = np.where(lost_by_then, "recovering",
                     np.where(tcv < tc_min, "non_forest_2000", "intact")).astype(object)

    # Unknown territory (outside the supplied tiles) must not be mistaken for
    # cleared land. An edge distance is reported only when a known clearing is
    # nearer than the nearest unknown pixel; otherwise it is NaN (not knowable).
    cov = _coverage(lossyear_paths, tf, loss.shape) & _coverage(treecover_paths, tf, loss.shape)
    # The mosaic window is not pixel-aligned to the tiles, so the outermost covered
    # pixels can hold fill values. Shrink coverage by one pixel to stay conservative.
    cov = ndimage.binary_erosion(cov)
    d_unknown = (ndimage.distance_transform_edt(cov, sampling=(dy_m, dx_m))
                 if not cov.all() else None)

    edge = np.full(len(out), np.nan)
    for yr in np.unique(y_rel):
        sel = inside & (y_rel == yr)
        if not sel.any():
            continue
        cleared = (((loss > 0) & (loss <= yr)) | (tc < tc_min)) & cov
        if cleared.any():
            d_clear = ndimage.distance_transform_edt(~cleared, sampling=(dy_m, dx_m))[r[sel], c[sel]]
        else:
            d_clear = np.full(int(sel.sum()), np.inf)
        value = np.minimum(d_clear, max_edge_m)
        if d_unknown is not None:
            unreliable = d_unknown[r[sel], c[sel]] < value
            value = np.where(unreliable, np.nan, value)
        edge[sel] = value

    out["treecover2000"] = np.where(inside, tcv, np.nan)
    out["loss_year"] = np.where(inside & (ly > 0), HANSEN_BASE_YEAR + ly, np.nan)
    out["age_since_loss"] = np.where(inside, age, np.nan)
    out["state"] = np.where(inside, state, None)
    out["edge_dist_m"] = edge
    return out


def _binned(df, col, bins, label_fmt, n_boot, seed, min_shots, last_open=False):
    rows = []
    edges = list(bins)
    for lo, hi in zip(edges[:-1], edges[1:]):
        g = df[(df[col] >= lo) & (df[col] < hi)]
        if len(g) < min_shots:
            continue
        med, ci_lo, ci_hi, k = cluster_bootstrap_median(g, n_boot=n_boot, seed=seed)
        rows.append({"bin": label_fmt(lo, hi), "lo": lo, "hi": hi, "n_shots": len(g),
                     "n_clusters": k, "median_rh98": med, "ci_low": ci_lo, "ci_high": ci_hi})
    return pd.DataFrame(rows)


def edge_profile(df: pd.DataFrame, bins=EDGE_BINS, n_boot: int = 300, seed: int = 0,
                 min_shots: int = 50, max_edge_m: float = 1000.0) -> pd.DataFrame:
    """Median RH98 against distance to the nearest cleared / non-forest pixel,
    using intact-forest shots only. The last bin is open-ended (censored)."""
    g = df[df["state"] == "intact"].dropna(subset=["edge_dist_m"])
    edges = list(bins)
    edges[-1] = max_edge_m + 1e-6  # include shots censored at the cap
    return _binned(g, "edge_dist_m", edges,
                   lambda lo, hi: f"{int(lo)}-{int(hi)} m" if hi <= max_edge_m else f">={int(lo)} m",
                   n_boot, seed, min_shots)


def recovery_curve(df: pd.DataFrame, bins=AGE_BINS, n_boot: int = 300, seed: int = 0,
                   min_shots: int = 50) -> pd.DataFrame:
    """Median RH98 by years since loss, with an intact-forest reference row."""
    rec = df[df["state"] == "recovering"].dropna(subset=["age_since_loss"])
    curve = _binned(rec, "age_since_loss", bins,
                    lambda lo, hi: f"{int(lo)}-{int(hi) - 1} yr", n_boot, seed, min_shots)
    ref = df[(df["state"] == "intact") & (df["edge_dist_m"] >= 500)] if "edge_dist_m" in df else df[df["state"] == "intact"]
    if len(ref) >= min_shots:
        med, lo, hi, k = cluster_bootstrap_median(ref, n_boot=n_boot, seed=seed)
        curve = pd.concat([curve, pd.DataFrame([{
            "bin": "intact reference (>=500 m from edge)", "lo": np.nan, "hi": np.nan,
            "n_shots": len(ref), "n_clusters": k, "median_rh98": med,
            "ci_low": lo, "ci_high": hi}])], ignore_index=True)
    return curve
