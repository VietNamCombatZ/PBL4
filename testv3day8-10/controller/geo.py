import math
import numpy as np
from sgp4.api import jday

EARTH_R_KM = 6371.0
WGS84_A = 6378.137            # km (bán trục lớn)
WGS84_F = 1/298.257223563
WGS84_B = WGS84_A * (1 - WGS84_F)
WGS84_E2 = 1 - (WGS84_B**2 / WGS84_A**2)

def gmst_from_jd(jd_ut1):
    """GMST theo Vallado (xấp xỉ đủ dùng cho demo)."""
    T = (jd_ut1 - 2451545.0) / 36525.0
    gmst = 280.46061837 + 360.98564736629 * (jd_ut1 - 2451545.0) \
           + 0.000387933 * T*T - (T**3)/38710000.0
    gmst = math.radians(gmst % 360.0)
    return gmst

def teme_to_ecef(r_teme_km, jd, fr):
    """
    Xấp xỉ: quay quanh trục Z theo GMST để từ TEME -> ECEF.
    Với demo routing là đủ (chưa xét nutation/polar motion).
    """
    jd_ut1 = jd + fr
    theta = gmst_from_jd(jd_ut1)
    R3 = np.array([[ math.cos(theta),  math.sin(theta), 0.0],
                   [-math.sin(theta),  math.cos(theta), 0.0],
                   [ 0.0,              0.0,            1.0]])
    r_ecef = R3 @ np.array(r_teme_km)
    return r_ecef  # km

def ecef_to_geodetic_wgs84(r_ecef_km):
    x, y, z = (coord * 1000.0 for coord in r_ecef_km)  # m
    a = WGS84_A * 1000.0
    e2 = WGS84_E2
    lon = math.atan2(y, x)
    r = math.hypot(x, y)
    # Bowring iteration
    lat = math.atan2(z, r)
    for _ in range(5):
        sinlat = math.sin(lat)
        N = a / math.sqrt(1 - e2 * sinlat*sinlat)
        alt = r / math.cos(lat) - N
        lat = math.atan2(z, r * (1 - e2 * (N / (N + alt))))
    sinlat = math.sin(lat)
    N = a / math.sqrt(1 - e2 * sinlat*sinlat)
    alt = r / math.cos(lat) - N
    # ra độ & km
    return math.degrees(lat), math.degrees(lon), alt / 1000.0

def haversine_km(lat1, lon1, lat2, lon2):
    r = EARTH_R_KM
    p = math.pi / 180
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = (math.sin(dlat/2)**2
         + math.cos(lat1*p)*math.cos(lat2*p)*math.sin(dlon/2)**2)
    return 2 * r * math.asin(math.sqrt(a))

def los_possible(lat1, lon1, alt1_km, lat2, lon2, alt2_km, earth_r_km=EARTH_R_KM):
    """
    Kiểm tra line-of-sight đơn giản với độ cong Trái Đất:
    - Nếu cả hai là ground (alt=0), coi như không LOS trừ khi khoảng cách rất nhỏ (tùy bạn).
    - Nếu có alt>0 (vệ tinh/máy bay), coi độ cao -> đường chân trời.
    Công thức xấp xỉ: d_horizon ≈ sqrt(2*R*h + h^2).
    """
    d_km = haversine_km(lat1, lon1, lat2, lon2)
    h1 = max(0.0, alt1_km)
    h2 = max(0.0, alt2_km)
    d_hor1 = math.sqrt(2*earth_r_km*h1 + h1*h1)
    d_hor2 = math.sqrt(2*earth_r_km*h2 + h2*h2)
    return d_km <= (d_hor1 + d_hor2)
