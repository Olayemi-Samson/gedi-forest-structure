from gedi_forest.cli import _granule_size_mb, spread_evenly


class AsProperty:
    size = 512.5


class AsMethod:
    def size(self):
        return 100.0


class Broken:
    size = None


def test_size_property():
    assert _granule_size_mb(AsProperty()) == 512.5


def test_size_method():
    assert _granule_size_mb(AsMethod()) == 100.0


def test_size_unknown_is_zero():
    assert _granule_size_mb(Broken()) == 0.0


def test_spread_evenly_covers_whole_time_range():
    items = list(range(100))  # stand-ins for granules in date order
    picked = spread_evenly(items, 5)
    assert picked[0] == 0 and picked[-1] == 99
    assert len(picked) == 5 and picked == sorted(picked)
    assert max(b - a for a, b in zip(picked, picked[1:])) <= 26  # no big gaps


def test_spread_evenly_edge_cases():
    assert spread_evenly([1, 2, 3], 10) == [1, 2, 3]
    assert spread_evenly([1, 2, 3], 0) == [1, 2, 3]
    assert spread_evenly(list(range(10)), 1) == [5]
    assert len(spread_evenly(list(range(10)), 10)) == 10


def test_sanity_report_flags_problems():
    import numpy as np
    import pandas as pd

    from gedi_forest.cli import sanity_report

    good = pd.DataFrame({"lon": np.linspace(8, 9, 2000), "lat": np.linspace(5, 6, 2000),
                         "year": [2020, 2021] * 1000, "granule": ["a"] * 2000,
                         "rh98": np.linspace(15, 40, 2000)})
    info, warns = sanity_report(good)
    assert warns == [] and info["shots"] == 2000

    bad = good.head(50).assign(year=2020, rh98=2.0)
    _, warns = sanity_report(bad)
    assert len(warns) >= 3
