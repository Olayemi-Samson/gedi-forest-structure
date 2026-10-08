"""Assign GEDI shots to administrative regions (any country, any GeoJSON).

Boundary files follow the geoBoundaries layout (property ``shapeName``). Nigeria
(GRID3, CC BY 4.0) and Brazil (CC BY 2.5) state boundaries are bundled in
``data/boundaries``. Other countries can be fetched with ``fetch_boundary``.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape

BOUNDARY_DIR = Path(__file__).resolve().parent.parent / "data" / "boundaries"

# geoBoundaries files are stored with Git LFS; this host serves the real file.
_GB_URL = (
    "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/main/"
    "releaseData/gbOpen/{iso}/{level}/geoBoundaries-{iso}-{level}_simplified.geojson"
)


def boundary_url(iso: str, level: str = "ADM1") -> str:
    return _GB_URL.format(iso=iso.upper(), level=level.upper())


def fetch_boundary(iso: str, level: str = "ADM1", dest: str | Path | None = None) -> Path:
    """Download a simplified geoBoundaries file. Check its licence before reuse:
    some countries are ODbL (share-alike), others CC BY."""
    dest = Path(dest) if dest else BOUNDARY_DIR / f"geoBoundaries-{iso.upper()}-{level.upper()}_simplified.geojson"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(boundary_url(iso, level), timeout=120) as r:
        payload = r.read()
    if payload.startswith(b"version https://git-lfs"):
        raise RuntimeError("Received a Git LFS pointer instead of data; the host did not serve the file.")
    json.loads(payload)  # validate before writing
    dest.write_bytes(payload)
    return dest


def bundled(iso: str, level: str = "ADM1") -> Path:
    p = BOUNDARY_DIR / f"geoBoundaries-{iso.upper()}-{level.upper()}_simplified.geojson"
    if not p.exists():
        raise FileNotFoundError(f"{p.name} is not bundled; run: gedi-forest regions-fetch --iso {iso.upper()}")
    return p


def load_regions(path: str | Path, name_field: str = "shapeName") -> list[tuple[str, object]]:
    """Return [(name, shapely geometry)] from a GeoJSON FeatureCollection."""
    fc = json.loads(Path(path).read_text())
    out = []
    for feat in fc["features"]:
        name = feat["properties"].get(name_field)
        if name is None:
            raise KeyError(f"Feature has no property '{name_field}'")
        out.append((str(name), shape(feat["geometry"])))
    return out


def assign_regions(lon, lat, regions: list[tuple[str, object]]) -> np.ndarray:
    """Name of the region containing each point (None where outside all regions).

    Points are tested against each region's bounding box first. If regions
    overlap, the first match wins.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    out = np.full(lon.shape, None, dtype=object)
    for name, geom in regions:
        minx, miny, maxx, maxy = geom.bounds
        cand = (out == None) & (lon >= minx) & (lon <= maxx) & (lat >= miny) & (lat <= maxy)  # noqa: E711
        if not cand.any():
            continue
        idx = np.flatnonzero(cand)
        inside = shapely.contains_xy(geom, lon[idx], lat[idx])
        out[idx[inside]] = name
    return out


def region_bounds(path: str | Path, region: str | None = None, name_field: str = "shapeName"):
    """(west, south, east, north) of one named region, or of the whole file."""
    regs = load_regions(path, name_field)
    if region is not None:
        match = [g for n, g in regs if n.lower() == region.lower()]
        if not match:
            raise KeyError(f"No region named '{region}'. Available: {sorted(n for n, _ in regs)}")
        geoms = match
    else:
        geoms = [g for _, g in regs]
    minx = min(g.bounds[0] for g in geoms)
    miny = min(g.bounds[1] for g in geoms)
    maxx = max(g.bounds[2] for g in geoms)
    maxy = max(g.bounds[3] for g in geoms)
    return minx, miny, maxx, maxy
