import numpy as np
import pandas as pd
import pytest

from gedi_forest import model


def spatial_df(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    lat = rng.uniform(-10, -8, n)
    lon = rng.uniform(-64, -62, n)
    field = 20 + 8 * np.sin(lat * 4) * np.cos(lon * 4)  # smooth, spatially autocorrelated
    edge = rng.uniform(0, 1000, n)
    rh98 = field + 4 * np.minimum(edge, 300) / 300 + rng.normal(0, 1.0, n)
    return pd.DataFrame({"lat": lat, "lon": lon, "edge_dist_m": edge, "rh98": rh98,
                         "age_since_loss": np.nan, "elev": 200 + 50 * rng.normal(size=n),
                         "treecover2000": 80.0})


def test_random_cv_overstates_skill_vs_spatial_cv():
    df = spatial_df()
    feats = ("lat", "lon", "edge_dist_m")
    sp = model.cross_validate(df, feats, scheme="spatial", block_deg=0.5)
    rd = model.cross_validate(df, feats, scheme="random")
    assert rd["r2_model"].mean() > sp["r2_model"].mean() + 0.1


def test_model_beats_mean_baseline_when_signal_exists():
    df = spatial_df()
    cv = model.cross_validate(df, ("edge_dist_m",), scheme="spatial", block_deg=0.5)
    assert (cv["rmse_model"] < cv["rmse_baseline"]).all()


def test_unavailable_features_are_skipped_and_empty_raises():
    df = spatial_df()
    cv = model.cross_validate(df, ("edge_dist_m", "not_a_column", "age_since_loss"))
    assert cv["features"].iloc[0] == "edge_dist_m"  # all-NaN age and missing column dropped
    with pytest.raises(ValueError, match="available"):
        model.cross_validate(df, ("nope",))


def test_too_few_blocks_raises():
    df = spatial_df().assign(lat=-9.0, lon=-63.0)
    with pytest.raises(ValueError, match="blocks"):
        model.cross_validate(df, ("edge_dist_m",), block_deg=0.5)


def test_block_ids_are_consistent():
    ids = model.block_ids([-9.01, -9.02, -9.9], [-63.01, -63.02, -62.1], 0.5)
    assert ids[0] == ids[1] != ids[2]


def test_summarize():
    cv = model.cross_validate(spatial_df(n=3000), ("edge_dist_m",), block_deg=0.5)
    s = model.summarize(cv)
    assert s["folds"] == 5 and s["scheme"] == "spatial"
