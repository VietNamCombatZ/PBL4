from __future__ import annotations

from src.types import Node
from src.data.fetch_satnogs import _norm_lon as norm_lon
from src.net.link_models import fspl_db


def test_norm_lon():
    assert -180 <= norm_lon(190) <= 180
    assert -180 <= norm_lon(-190) <= 180


def test_fspl_monotonic():
    f = 2.4e9
    d1 = fspl_db(1, f)
    d2 = fspl_db(10, f)
    assert d2 > d1
