"""A deliberately honest ML baseline: predict RH98 with spatial cross-validation.

Random k-fold cross-validation on spatially autocorrelated data lets the model
see near-duplicates of every test point in training, which inflates scores.
``cross_validate`` supports both schemes so the gap can be measured, and the
default is spatial blocks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, KFold

DEFAULT_FEATURES = ("edge_dist_m", "age_since_loss", "elev", "treecover2000")


def block_ids(lat, lon, block_deg: float = 0.25) -> np.ndarray:
    """Integer id of the block_deg x block_deg square containing each point."""
    iy = np.floor(np.asarray(lat) / block_deg).astype(np.int64)
    ix = np.floor(np.asarray(lon) / block_deg).astype(np.int64)
    return iy * 1_000_003 + ix


def cross_validate(
    df: pd.DataFrame,
    features: tuple[str, ...] = DEFAULT_FEATURES,
    target: str = "rh98",
    scheme: str = "spatial",
    n_splits: int = 5,
    block_deg: float = 0.25,
    seed: int = 0,
) -> pd.DataFrame:
    """Per-fold RMSE / MAE / R2 for the model and a train-mean baseline."""
    feats = [f for f in features if f in df.columns and df[f].notna().any()]
    if not feats:
        raise ValueError(f"None of the features {features} are available in the data.")
    d = df.dropna(subset=[target]).reset_index(drop=True)
    X = d[feats].to_numpy(float)
    y = d[target].to_numpy(float)

    if scheme == "spatial":
        groups = block_ids(d["lat"], d["lon"], block_deg)
        if len(np.unique(groups)) < n_splits:
            raise ValueError("Fewer spatial blocks than folds; reduce n_splits or block_deg.")
        splits = GroupKFold(n_splits=n_splits).split(X, y, groups)
    elif scheme == "random":
        splits = KFold(n_splits=n_splits, shuffle=True, random_state=seed).split(X)
    else:
        raise ValueError("scheme must be 'spatial' or 'random'")

    rows = []
    for k, (tr, te) in enumerate(splits):
        model = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, random_state=seed)
        model.fit(X[tr], y[tr])
        pred = model.predict(X[te])
        base = np.full(len(te), y[tr].mean())
        rows.append({
            "fold": k, "scheme": scheme, "n_train": len(tr), "n_test": len(te),
            "rmse_model": float(np.sqrt(np.mean((y[te] - pred) ** 2))),
            "rmse_baseline": float(np.sqrt(np.mean((y[te] - base) ** 2))),
            "mae_model": float(mean_absolute_error(y[te], pred)),
            "r2_model": float(r2_score(y[te], pred)),
            "features": ",".join(feats),
        })
    return pd.DataFrame(rows)


def summarize(cv: pd.DataFrame) -> dict:
    return {
        "scheme": str(cv["scheme"].iloc[0]),
        "features": str(cv["features"].iloc[0]),
        "mean_rmse_model_m": float(cv["rmse_model"].mean()),
        "mean_rmse_baseline_m": float(cv["rmse_baseline"].mean()),
        "mean_r2_model": float(cv["r2_model"].mean()),
        "folds": int(len(cv)),
    }
