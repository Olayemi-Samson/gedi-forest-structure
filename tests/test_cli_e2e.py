"""Full command-line chain on fabricated granules placed in real locations.

Shot values are fabricated; the boundaries used for assignment are the REAL
bundled Nigeria and Brazil files. This checks that the pieces work together.
"""
import json

import h5py
import numpy as np
import pandas as pd

from gedi_forest import cli

from .conftest import write_beam
from .test_disturbance import E, N, S, W, _grid, _write


def _granules(tmp_path, name, lon0, lat0, height, n_gran=6, n=500, years=(1.5, 3.5), seed=0):
    d = tmp_path / name
    d.mkdir()
    rng = np.random.default_rng(seed)
    for g in range(n_gran):
        lon = lon0 + rng.uniform(0, 0.1, n)
        lat = lat0 + rng.uniform(0, 0.1, n)
        h = height + rng.normal(g - n_gran / 2, 1.0, n)  # per-track offset
        with h5py.File(d / f"g{g}.h5", "w") as f:
            write_beam(f, "BEAM0101", lat, lon, years[g % len(years)], h)
    return d


def test_process_then_compare_nigeria_vs_brazil(tmp_path):
    ng = _granules(tmp_path, "ng", 8.5, 5.6, 26.0, seed=1)      # inside Cross River
    br = _granules(tmp_path, "br", -63.0, -10.0, 34.0, seed=2)  # inside Rondonia
    both = tmp_path / "both"
    both.mkdir()
    for p in list(ng.glob("*.h5")):
        (both / f"ng_{p.name}").write_bytes(p.read_bytes())
    for p in list(br.glob("*.h5")):
        (both / f"br_{p.name}").write_bytes(p.read_bytes())

    shots = tmp_path / "shots.csv.gz"
    cli.main(["process", "--raw", str(both), "--out", str(shots)])
    res = tmp_path / "cmp"
    cli.main(["compare", "--shots", str(shots), "--iso", "NGA", "BRA",
              "--min-shots", "100", "--n-boot", "100", "--out", str(res)])

    by_region = pd.read_csv(res / "by_region.csv")
    assert set(by_region["region"]) == {"NGA: Cross River", "BRA: Rondonia"}
    top = by_region.iloc[0]
    assert top["region"] == "BRA: Rondonia" and top["median_rh98"] > 30

    summary = json.loads((res / "summary.json").read_text())
    assert summary["n_shots_assigned"] == summary["n_shots_total"] == 6000
    assert summary["difference"]["a"] == "BRA" and 5 < summary["difference"]["difference_m"] < 11
    assert (res / "by_region.png").exists()


def test_disturbance_then_model(tmp_path):
    LON, LAT = _grid()
    loss = np.zeros(LON.shape, "uint8")
    loss[LON < -62.98] = 3
    tc = np.full(LON.shape, 80, "uint8")
    lp, tp = tmp_path / "loss.tif", tmp_path / "tc.tif"
    _write(lp, loss)
    _write(tp, tc)

    raw = tmp_path / "raw"
    raw.mkdir()
    rng = np.random.default_rng(3)
    for g in range(8):
        n = 800
        lon = W + rng.uniform(0, E - W, n)
        lat = S + rng.uniform(0, N - S, n)
        # Fabricated truth: cleared 2003 block regrows; forest shorter near that edge.
        in_block = lon < -62.98
        dist_deg = np.where(in_block, 0, lon + 62.98)
        h = np.where(in_block, 12 + rng.normal(0, 1, n),
                     18 + 14 * np.minimum(dist_deg / 0.01, 1) + rng.normal(0, 1, n))
        with h5py.File(raw / f"g{g}.h5", "w") as f:
            write_beam(f, "BEAM0101", lat, lon, 1.5 if g % 2 else 3.5, h)

    shots = tmp_path / "shots.csv.gz"
    cli.main(["process", "--raw", str(raw), "--out", str(shots)])
    dres = tmp_path / "dist"
    cli.main(["disturbance", "--shots", str(shots), "--lossyear", str(lp), "--treecover", str(tp),
              "--n-boot", "100", "--out", str(dres)])
    for name in ["shots_with_context.csv.gz", "edge_profile.csv", "recovery_curve.csv",
                 "edge_profile.png", "recovery_curve.png", "summary.json"]:
        assert (dres / name).exists(), name

    ctx = pd.read_csv(dres / "shots_with_context.csv.gz")
    assert {"intact", "recovering"} <= set(ctx["state"].dropna())
    edge = pd.read_csv(dres / "edge_profile.csv")
    # The fabricated truth has a ~14 m edge effect; the profile should recover most of it.
    assert edge["median_rh98"].iloc[-1] - edge["median_rh98"].iloc[0] > 8

    mres = tmp_path / "mod"
    cli.main(["model", "--shots", str(dres / "shots_with_context.csv.gz"),
              "--block-deg", "0.01", "--out", str(mres)])
    summ = json.loads((mres / "model_summary.json").read_text())
    assert summ["spatial"]["mean_rmse_model_m"] < summ["spatial"]["mean_rmse_baseline_m"]
