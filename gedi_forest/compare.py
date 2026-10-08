"""Region comparison with cluster-aware uncertainty.

GEDI shots are spaced about 60 m along orbit tracks, so neighbouring shots are
strongly correlated. A naive bootstrap over shots would give confidence
intervals that are far too narrow. Here the resampling unit is the *cluster*
(one beam of one granule, i.e. one ground track segment), which respects that
dependence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _clusters(df: pd.DataFrame, cluster_cols: tuple[str, ...]) -> list[np.ndarray]:
    keys = df[list(cluster_cols)].astype(str).agg("|".join, axis=1)
    return [g.to_numpy() for _, g in df.groupby(keys, sort=False)["rh98"]]


def cluster_bootstrap_median(
    df: pd.DataFrame,
    cluster_cols: tuple[str, ...] = ("granule", "beam"),
    n_boot: int = 500,
    seed: int = 0,
    ci: float = 95.0,
) -> tuple[float, float, float, int]:
    """Median RH98 with a percentile CI from resampling whole clusters."""
    groups = _clusters(df, cluster_cols)
    point = float(np.median(np.concatenate(groups)))
    if len(groups) < 2:
        return point, np.nan, np.nan, len(groups)
    rng = np.random.default_rng(seed)
    meds = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        meds[i] = np.median(np.concatenate([groups[j] for j in pick]))
    lo, hi = np.percentile(meds, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return point, float(lo), float(hi), len(groups)


def compare_regions(
    df: pd.DataFrame,
    region_col: str = "region",
    min_shots: int = 100,
    n_boot: int = 500,
    seed: int = 0,
    cluster_cols: tuple[str, ...] = ("granule", "beam"),
) -> pd.DataFrame:
    """Per-region RH98 summary. Regions with fewer than ``min_shots`` are dropped."""
    rows = []
    for name, g in df.dropna(subset=[region_col]).groupby(region_col):
        if len(g) < min_shots:
            continue
        med, lo, hi, k = cluster_bootstrap_median(g, cluster_cols, n_boot, seed)
        rows.append({
            region_col: name, "n_shots": int(len(g)), "n_clusters": k,
            "median_rh98": med, "ci_low": lo, "ci_high": hi,
            "p10": float(g["rh98"].quantile(0.10)), "p90": float(g["rh98"].quantile(0.90)),
        })
    out = pd.DataFrame(rows)
    return out.sort_values("median_rh98", ascending=False).reset_index(drop=True) if len(out) else out


def difference_in_medians(
    a: pd.DataFrame,
    b: pd.DataFrame,
    cluster_cols: tuple[str, ...] = ("granule", "beam"),
    n_boot: int = 500,
    seed: int = 0,
    ci: float = 95.0,
) -> dict:
    """Median(a) - median(b) with a cluster bootstrap CI (clusters resampled
    independently within each group)."""
    ga, gb = _clusters(a, cluster_cols), _clusters(b, cluster_cols)
    point = float(np.median(np.concatenate(ga)) - np.median(np.concatenate(gb)))
    if len(ga) < 2 or len(gb) < 2:
        return {"difference_m": point, "ci_low": np.nan, "ci_high": np.nan,
                "clusters_a": len(ga), "clusters_b": len(gb)}
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        pa = rng.integers(0, len(ga), len(ga))
        pb = rng.integers(0, len(gb), len(gb))
        diffs[i] = (np.median(np.concatenate([ga[j] for j in pa]))
                    - np.median(np.concatenate([gb[j] for j in pb])))
    lo, hi = np.percentile(diffs, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return {"difference_m": point, "ci_low": float(lo), "ci_high": float(hi),
            "clusters_a": len(ga), "clusters_b": len(gb)}
