"""Quality filtering and time handling for GEDI shots."""
from __future__ import annotations

import pandas as pd

# GEDI delta_time is "seconds since 2018-01-01 00:00:00 UTC".
GEDI_EPOCH = pd.Timestamp("2018-01-01", tz="UTC")


def add_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["time"] = GEDI_EPOCH + pd.to_timedelta(out["delta_time"], unit="s")
    out["year"] = out["time"].dt.year
    return out


def apply_quality(
    df: pd.DataFrame,
    min_sensitivity: float = 0.95,
    require_quality_flag: bool = True,
    drop_degraded: bool = True,
    min_height: float = 0.0,
    max_height: float = 120.0,
) -> tuple[pd.DataFrame, dict]:
    """Filter shots and report how many each rule removed.

    All thresholds are configurable. Defaults follow common practice for dense
    forest; they are analysis choices, not product guarantees, and should be
    reported alongside results.
    """
    report = {"n_input": int(len(df))}
    mask = pd.Series(True, index=df.index)

    if require_quality_flag:
        m = df["quality_flag"] == 1
        report["removed_quality_flag"] = int((mask & ~m).sum())
        mask &= m
    if drop_degraded:
        m = df["degrade_flag"] == 0
        report["removed_degraded"] = int((mask & ~m).sum())
        mask &= m
    m = df["sensitivity"] >= min_sensitivity
    report["removed_low_sensitivity"] = int((mask & ~m).sum())
    mask &= m
    m = df["rh98"].between(min_height, max_height)
    report["removed_height_range"] = int((mask & ~m).sum())
    mask &= m

    out = df[mask].reset_index(drop=True)
    report["n_kept"] = int(len(out))
    report["thresholds"] = {
        "min_sensitivity": min_sensitivity,
        "require_quality_flag": require_quality_flag,
        "drop_degraded": drop_degraded,
        "height_range_m": [min_height, max_height],
    }
    return out, report
