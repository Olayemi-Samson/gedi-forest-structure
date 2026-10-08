from gedi_forest.cli import _granule_size_mb


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
