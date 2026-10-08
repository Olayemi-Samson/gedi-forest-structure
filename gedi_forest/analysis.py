"""Gridding, temporal summaries, vertical profiles and change detection."""
from __future__ import annotations

import numpy as np
import pandas as pd


def grid_stats(df: pd.DataFrame, resolution: float = 0.01, min_shots: int = 5) -> pd.DataFrame:
    """Aggregate shots to a regular lat/lon grid (default 0.01 deg, about 1.1 km).

    Cell ids are integer indices so results are exactly reproducible. The
    returned lat/lon are cell centres.
    """
    g = df.copy()
    g["ix"] = np.floor(g["lon"] / resolution).astype(int)
    g["iy"] = np.floor(g["lat"] / resolution).astype(int)
    agg = (
        g.groupby(["ix", "iy"])["rh98"]
        .agg(n="count", median="median", mean="mean", p95=lambda s: s.quantile(0.95))
        .reset_index()
    )
    agg = agg[agg["n"] >= min_shots].copy()
    agg["lon"] = (agg["ix"] + 0.5) * resolution
    agg["lat"] = (agg["iy"] + 0.5) * resolution
    return agg.reset_index(drop=True)


def yearly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-year canopy height statistics with shot counts."""
    return (
        df.groupby("year")["rh98"]
        .agg(n="count", mean="mean", median="median",
             p10=lambda s: s.quantile(0.10), p90=lambda s: s.quantile(0.90))
        .reset_index()
    )


def mean_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Mean relative-height profile (rh0..rh100 in 5 % steps) by year."""
    cols = [c for c in df.columns if c.startswith("rh") and c != "rh98"]
    cols = sorted(cols, key=lambda c: int(c[2:]))
    prof = df.groupby("year")[cols].mean()
    prof.columns = [int(c[2:]) for c in cols]
    return prof


def change_map(
    df: pd.DataFrame,
    early_years: tuple[int, ...],
    late_years: tuple[int, ...],
    resolution: float = 0.01,
    min_shots: int = 5,
) -> pd.DataFrame:
    """Per-cell change in median rh98 between two sets of years.

    Cells need at least ``min_shots`` in both periods. GEDI is a sampling
    instrument, so shot positions differ between periods; the result is an
    exploratory indicator of structural change, not a wall-to-wall measurement.
    """
    a = grid_stats(df[df["year"].isin(early_years)], resolution, min_shots)
    b = grid_stats(df[df["year"].isin(late_years)], resolution, min_shots)
    m = a.merge(b, on=["ix", "iy"], suffixes=("_early", "_late"))
    m["lon"] = m["lon_early"]
    m["lat"] = m["lat_early"]
    m["delta_median"] = m["median_late"] - m["median_early"]
    return m[["ix", "iy", "lon", "lat", "n_early", "n_late",
              "median_early", "median_late", "delta_median"]].reset_index(drop=True)


def summarize_change(cm: pd.DataFrame, loss_threshold: float = -5.0) -> dict:
    if cm.empty:
        return {"n_cells": 0}
    return {
        "n_cells": int(len(cm)),
        "mean_delta_m": float(cm["delta_median"].mean()),
        "median_delta_m": float(cm["delta_median"].median()),
        "share_cells_height_loss": float((cm["delta_median"] <= loss_threshold).mean()),
        "loss_threshold_m": loss_threshold,
    }
