import h5py
import numpy as np
import pandas as pd
import pytest

from gedi_forest import analysis, cli, filters, io

from .conftest import write_beam


def load(granule_dir):
    df = io.read_directory(granule_dir)
    return filters.add_time_columns(df)


def test_read_and_years(granule_dir):
    df = load(granule_dir)
    assert len(df) == 8000
    assert set(df["year"]) == {2019, 2021}
    assert df["rh98"].between(0, 120).all()


def test_schema_error_when_dataset_missing(tmp_path):
    p = tmp_path / "bad.h5"
    with h5py.File(p, "w") as f:
        g = f.create_group("BEAM0101")
        g["lat_lowestmode"] = np.zeros(3)
    with pytest.raises(io.SchemaError, match="missing datasets"):
        io.read_granule(p)


def test_schema_error_when_no_beams(tmp_path):
    p = tmp_path / "empty.h5"
    with h5py.File(p, "w") as f:
        f.create_group("METADATA")
    with pytest.raises(io.SchemaError, match="beam groups"):
        io.read_granule(p)


def test_centimetre_units_are_converted(tmp_path):
    p = tmp_path / "cm.h5"
    with h5py.File(p, "w") as f:
        write_beam(f, "BEAM0101", np.zeros(5) - 10, np.zeros(5) - 63, 1.0,
                   np.full(5, 25.0), rh_units="cm")
    df = io.read_granule(p)
    assert np.allclose(df["rh98"], 25.0, atol=0.01)


def test_quality_filter_counts(tmp_path):
    n = 10
    q = np.array([1, 1, 1, 1, 1, 1, 1, 1, 0, 0], "uint8")
    d = np.array([0, 0, 0, 0, 0, 0, 1, 0, 0, 0], "uint8")
    s = np.array([0.99, 0.99, 0.99, 0.5, 0.99, 0.99, 0.99, 0.99, 0.99, 0.99], "float32")
    h = np.array([20, 20, 20, 20, 500, 20, 20, 20, 20, 20], dtype=float)
    p = tmp_path / "q.h5"
    with h5py.File(p, "w") as f:
        write_beam(f, "BEAM0101", np.zeros(n) - 10, np.zeros(n) - 63, 1.0, h,
                   quality=q, degrade=d, sens=s)
    df = filters.add_time_columns(io.read_granule(p))
    kept, rep = filters.apply_quality(df)
    assert rep["n_input"] == 10
    assert rep["removed_quality_flag"] == 2
    assert rep["removed_degraded"] == 1
    assert rep["removed_low_sensitivity"] == 1
    assert rep["removed_height_range"] == 1
    # shots 0,1,2,5,7 survive; 3, 4, 6, 8 and 9 are each removed by one rule
    assert rep["n_kept"] == 5 == len(kept)
    assert list(kept["shot_number"]) == [0, 1, 2, 5, 7]


def test_grid_median_exact(granule_dir):
    df = load(granule_dir)
    early = df[df["year"] == 2019]
    grid = analysis.grid_stats(early, resolution=0.05, min_shots=5)
    assert len(grid) > 0
    assert grid["n"].sum() <= len(early)
    assert np.allclose(grid["median"], 30.0, atol=0.5)


def test_change_map_detects_clearing(granule_dir):
    df = load(granule_dir)
    cm = analysis.change_map(df, (2019,), (2021,), resolution=0.01, min_shots=3)
    assert len(cm) > 0
    west = cm[cm["lon"] < -62.96]
    east = cm[cm["lon"] > -62.94]
    assert west["delta_median"].mean() < -15  # about -20 m by construction
    assert abs(east["delta_median"].mean()) < 1
    s = analysis.summarize_change(cm)
    assert 0.1 < s["share_cells_height_loss"] < 0.6


def test_yearly_and_profile(granule_dir):
    df = load(granule_dir)
    y = analysis.yearly_summary(df).set_index("year")
    assert y.loc[2019, "median"] > y.loc[2021, "median"]
    prof = analysis.mean_profile(df)
    assert list(prof.index) == [2019, 2021]
    assert prof.loc[2019, 100] >= prof.loc[2019, 50]


def test_cli_process_and_report_end_to_end(granule_dir, tmp_path):
    shots = tmp_path / "out" / "shots.csv.gz"
    cli.main(["process", "--raw", str(granule_dir), "--out", str(shots)])
    assert shots.exists()
    res = tmp_path / "results"
    cli.main(["report", "--shots", str(shots), "--out", str(res)])
    for name in ["summary.json", "grid_stats.csv", "yearly_summary.csv",
                 "height_map.png", "height_by_year.png", "mean_profiles.png",
                 "change_map.csv", "change_map.png"]:
        assert (res / name).exists(), name
    summ = pd.read_json(res / "summary.json", typ="series")
    assert summ["n_shots"] == 8000
