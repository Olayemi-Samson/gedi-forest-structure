"""Read GEDI L2A granules (HDF5) into tidy pandas tables.

GEDI L2A stores one group per laser beam (BEAMxxxx). Each beam group holds
per-shot datasets. This module reads only the datasets needed for canopy
structure analysis and fails loudly (SchemaError) if a required dataset is
missing, so a change in product layout is never silently ignored.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import h5py
import numpy as np
import pandas as pd

# Beam groups defined for GEDI: four power beams and four coverage beams.
BEAM_NAMES = (
    "BEAM0000", "BEAM0001", "BEAM0010", "BEAM0011",
    "BEAM0101", "BEAM0110", "BEAM1000", "BEAM1011",
)

REQUIRED = (
    "shot_number", "delta_time", "lat_lowestmode", "lon_lowestmode",
    "quality_flag", "degrade_flag", "sensitivity", "rh",
)

# Relative-height percentiles kept in the output table (rh is stored 0..100).
RH_KEEP = tuple(range(0, 101, 5)) + (98,)
RH_KEEP = tuple(sorted(set(RH_KEEP)))


class SchemaError(RuntimeError):
    """Raised when a granule does not contain the datasets we expect."""


def _units(ds: h5py.Dataset) -> str:
    u = ds.attrs.get("units", "")
    if isinstance(u, bytes):
        u = u.decode(errors="ignore")
    elif isinstance(u, np.ndarray) and u.size:
        u = u.flat[0]
        u = u.decode(errors="ignore") if isinstance(u, bytes) else str(u)
    return str(u).strip().lower()


def read_beam(group: h5py.Group, beam: str, source: str) -> pd.DataFrame:
    missing = [name for name in REQUIRED if name not in group]
    if missing:
        raise SchemaError(f"{source}:{beam} is missing datasets: {missing}")

    rh = group["rh"][:]
    if rh.ndim != 2 or rh.shape[1] != 101:
        raise SchemaError(f"{source}:{beam} 'rh' has shape {rh.shape}, expected (N, 101)")

    # Convert to metres if the file declares centimetres.
    scale = 0.01 if _units(group["rh"]) in {"cm", "centimeters", "centimetres"} else 1.0

    data = {
        "beam": np.full(rh.shape[0], beam),
        "shot_number": group["shot_number"][:],
        "delta_time": group["delta_time"][:],
        "lat": group["lat_lowestmode"][:],
        "lon": group["lon_lowestmode"][:],
        "quality_flag": group["quality_flag"][:],
        "degrade_flag": group["degrade_flag"][:],
        "sensitivity": group["sensitivity"][:],
    }
    for p in RH_KEEP:
        data[f"rh{p}"] = (rh[:, p] * scale).astype("float32")
    df = pd.DataFrame(data)
    df["granule"] = Path(source).name
    return df


def read_granule(path: str | Path, beams: Iterable[str] | None = None) -> pd.DataFrame:
    """Read all (or selected) beams of one GEDI L2A granule."""
    path = Path(path)
    wanted = tuple(beams) if beams else BEAM_NAMES
    frames = []
    with h5py.File(path, "r") as f:
        found = [b for b in wanted if b in f]
        if not found:
            raise SchemaError(f"{path.name}: none of the expected beam groups found")
        for beam in found:
            frames.append(read_beam(f[beam], beam, str(path)))
    return pd.concat(frames, ignore_index=True)


def read_directory(directory: str | Path, pattern: str = "*.h5", **kw) -> pd.DataFrame:
    files = sorted(Path(directory).glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matching {pattern} in {directory}")
    return pd.concat([read_granule(p, **kw) for p in files], ignore_index=True)
