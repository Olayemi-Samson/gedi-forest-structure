"""Synthetic GEDI-like HDF5 fixtures.

IMPORTANT: these files are fabricated for unit tests only. They exist to check
that the code behaves correctly on data with known properties. No result in this
repository's documentation or figures comes from them.
"""
from __future__ import annotations

import h5py
import numpy as np
import pytest

SECONDS_PER_YEAR = 365.25 * 24 * 3600


def make_rh(rh98: np.ndarray) -> np.ndarray:
    """Build monotonic (N, 101) rh profiles whose rh[:, 98] equals ``rh98``."""
    pct = np.arange(101)
    frac = np.clip(pct / 98.0, 0, 1.02)
    return (rh98[:, None] * frac[None, :]).astype("float32")


def write_beam(f, beam, lat, lon, year_offset, rh98, quality=None, degrade=None,
               sens=None, rh_units=None):
    n = len(lat)
    g = f.create_group(beam)
    g["shot_number"] = np.arange(n, dtype="int64")
    # delta_time is seconds since 2018-01-01
    g["delta_time"] = year_offset * SECONDS_PER_YEAR + 1000.0 + np.arange(n)
    g["lat_lowestmode"] = lat
    g["lon_lowestmode"] = lon
    g["quality_flag"] = np.ones(n, "uint8") if quality is None else quality
    g["degrade_flag"] = np.zeros(n, "uint8") if degrade is None else degrade
    g["sensitivity"] = np.full(n, 0.98, "float32") if sens is None else sens
    rh = make_rh(rh98)
    if rh_units == "cm":
        rh = rh * 100
    ds = g.create_dataset("rh", data=rh)
    if rh_units:
        ds.attrs["units"] = rh_units


@pytest.fixture
def granule_dir(tmp_path):
    """Two granules: 2019 (tall forest, 30 m) and 2021 (cleared area drops to 10 m).

    Shots sit in a 0.1 x 0.1 degree box at (-63, -10).
    """
    rng = np.random.default_rng(0)
    n = 4000
    lat = -10 + rng.uniform(0, 0.1, n)
    lon = -63 + rng.uniform(0, 0.1, n)

    h_early = np.full(n, 30.0) + rng.normal(0, 0.5, n)
    h_late = h_early.copy()
    cleared = lon < -62.95  # western half is cleared by 2021
    h_late[cleared] = 10.0 + rng.normal(0, 0.5, cleared.sum())

    with h5py.File(tmp_path / "g_2019.h5", "w") as f:
        write_beam(f, "BEAM0101", lat, lon, 1.5, h_early)  # ~mid 2019
    with h5py.File(tmp_path / "g_2021.h5", "w") as f:
        write_beam(f, "BEAM0101", lat, lon, 3.5, h_late)  # ~mid 2021
    return tmp_path
