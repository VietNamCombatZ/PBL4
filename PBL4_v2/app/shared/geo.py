import math
from typing import Tuple

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 lat/lon points in km."""
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def midpoint(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """Midpoint of two lat/lon points (approx)."""
    rlat1 = math.radians(lat1)
    rlon1 = math.radians(lon1)
    rlat2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    bx = math.cos(rlat2) * math.cos(dlon)
    by = math.cos(rlat2) * math.sin(dlon)
    lat3 = math.atan2(math.sin(rlat1) + math.sin(rlat2), math.sqrt((math.cos(rlat1) + bx) ** 2 + by ** 2))
    lon3 = rlon1 + math.atan2(by, math.cos(rlat1) + bx)
    return math.degrees(lat3), (math.degrees(lon3) + 540) % 360 - 180
