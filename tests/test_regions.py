"""Tests against the REAL bundled boundary files (geoBoundaries: Nigeria, Brazil)."""
import json

import numpy as np
import pytest

from gedi_forest import regions


@pytest.fixture(scope="module")
def nga():
    return regions.load_regions(regions.bundled("NGA"))


@pytest.fixture(scope="module")
def bra():
    return regions.load_regions(regions.bundled("BRA"))


def test_nigeria_has_36_states_plus_fct(nga):
    names = {n for n, _ in nga}
    assert len(nga) == 37
    assert {"Cross River", "Lagos", "Ogun", "Edo", "Ondo",
            "Abuja Federal Capital Territory"} <= names


def test_brazil_has_26_states_plus_df(bra):
    assert len(bra) == 27
    assert {"Rondonia", "Amazonas", "Para", "Acre"} <= {n for n, _ in bra}


def test_known_nigerian_cities_fall_in_right_state(nga):
    cities = {  # (lon, lat), real coordinates
        "Calabar": (8.3220, 4.9517, "Cross River"),
        "Lagos": (3.3792, 6.5244, "Lagos"),
        "Abuja": (7.3986, 9.0765, "Abuja Federal Capital Territory"),
        "Ibadan": (3.9470, 7.3775, "Oyo"),
        "Kano": (8.5920, 12.0022, "Kano"),
    }
    lon = np.array([v[0] for v in cities.values()])
    lat = np.array([v[1] for v in cities.values()])
    got = regions.assign_regions(lon, lat, nga)
    assert list(got) == [v[2] for v in cities.values()]


def test_point_in_ocean_is_unassigned(nga):
    got = regions.assign_regions([3.0], [0.0], nga)  # Gulf of Guinea
    assert got[0] is None


def test_known_brazilian_cities(bra):
    got = regions.assign_regions([-63.9004, -60.0217, -48.5044],
                                 [-8.7612, -3.1190, -1.4558], bra)
    assert list(got) == ["Rondonia", "Amazonas", "Para"]


def test_boundary_metadata_licences_are_recorded():
    nga = json.loads((regions.BOUNDARY_DIR / "geoBoundaries-NGA-ADM1-metaData.json").read_text())
    bra = json.loads((regions.BOUNDARY_DIR / "geoBoundaries-BRA-ADM1-metaData.json").read_text())
    assert "CC BY 4.0" in nga["boundaryLicense"]
    assert "Creative Commons Attribution 2.5" in bra["boundaryLicense"]


def test_boundary_url_is_lfs_media_host():
    u = regions.boundary_url("cod", "adm1")
    assert u.startswith("https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/")
    assert u.endswith("geoBoundaries-COD-ADM1_simplified.geojson")


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_rejects_lfs_pointer(monkeypatch, tmp_path):
    monkeypatch.setattr(regions.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(b"version https://git-lfs.github.com/spec/v1\noid sha256:x\n"))
    with pytest.raises(RuntimeError, match="LFS pointer"):
        regions.fetch_boundary("COD", dest=tmp_path / "x.geojson")


def test_fetch_writes_valid_geojson(monkeypatch, tmp_path):
    payload = json.dumps({"type": "FeatureCollection", "features": []}).encode()
    monkeypatch.setattr(regions.urllib.request, "urlopen", lambda *a, **k: _Resp(payload))
    p = regions.fetch_boundary("COD", dest=tmp_path / "x.geojson")
    assert json.loads(p.read_text())["type"] == "FeatureCollection"


def test_region_bounds_contain_known_city_and_reject_unknown():
    w, s, e, n = regions.region_bounds(regions.bundled("NGA"), "Cross River")
    assert w < 8.3220 < e and s < 4.9517 < n  # Calabar
    with pytest.raises(KeyError, match="Available"):
        regions.region_bounds(regions.bundled("NGA"), "Atlantis")
    cw, cs, ce, cn = regions.region_bounds(regions.bundled("NGA"))
    assert cw < w and ce > e and cs <= s and cn > n  # whole country is bigger
