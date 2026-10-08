import numpy as np
import pandas as pd

from gedi_forest import compare


def make_df(n_clusters=30, per=200, center=30.0, cluster_sd=3.0, shot_sd=1.0, seed=0, region="A"):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_clusters):
        offset = rng.normal(0, cluster_sd)
        rows.append(pd.DataFrame({
            "rh98": center + offset + rng.normal(0, shot_sd, per),
            "granule": f"g{k}", "beam": "BEAM0101", "region": region}))
    return pd.concat(rows, ignore_index=True)


def test_cluster_ci_is_wider_than_naive_ci():
    """Shots within a track are correlated; ignoring that understates uncertainty."""
    df = make_df()
    _, lo, hi, k = compare.cluster_bootstrap_median(df, n_boot=300)
    rng = np.random.default_rng(1)
    vals = df["rh98"].to_numpy()
    naive = [np.median(rng.choice(vals, len(vals))) for _ in range(300)]
    nlo, nhi = np.percentile(naive, [2.5, 97.5])
    assert k == 30
    assert (hi - lo) > 3 * (nhi - nlo)


def test_compare_regions_orders_and_filters():
    a = make_df(center=32, region="A", seed=1)
    b = make_df(center=22, region="B", seed=2)
    tiny = make_df(n_clusters=1, per=10, center=50, region="tiny", seed=3)
    out = compare.compare_regions(pd.concat([a, b, tiny]), "region", min_shots=100, n_boot=100)
    assert list(out["region"]) == ["A", "B"]  # tiny dropped, A taller than B
    assert out.loc[0, "ci_low"] <= out.loc[0, "median_rh98"] <= out.loc[0, "ci_high"]


def test_difference_in_medians_sign_and_ci():
    a = make_df(center=32, seed=4)
    b = make_df(center=22, seed=5)
    d = compare.difference_in_medians(a, b, n_boot=300)
    assert 7 < d["difference_m"] < 13
    assert d["ci_low"] < d["difference_m"] < d["ci_high"]
    same = compare.difference_in_medians(make_df(seed=6), make_df(seed=7), n_boot=300)
    assert same["ci_low"] < 0 < same["ci_high"]  # no true difference: CI spans zero


def test_single_cluster_returns_nan_ci():
    df = make_df(n_clusters=1)
    med, lo, hi, k = compare.cluster_bootstrap_median(df)
    assert k == 1 and np.isnan(lo) and np.isnan(hi)
