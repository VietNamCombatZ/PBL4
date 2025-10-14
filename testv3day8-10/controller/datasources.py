# controller/datasources.py
import asyncio, time, json, math, random, os
from typing import Dict, List, Tuple, Optional
import aiohttp
from sgp4.api import Satrec, jday
# from .models import NodeInfo
# from .geo import teme_to_ecef, ecef_to_geodetic_wgs84
from models import NodeInfo
from geo import teme_to_ecef, ecef_to_geodetic_wgs84

CELESTRAK_ACTIVE_JSON = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json"
SATNOGS_STATIONS_API = "https://network.satnogs.org/api/stations/"
NDBC_STATION_TABLE   = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"
OPENSKY_STATES_ALL   = "https://opensky-network.org/api/states/all"

class DataSource:
    def __init__(self, earth_r_km=6371.0):
        self.earth_r_km = earth_r_km

        # ---- CelesTrak (đã có từ trước) ----
        self._sat_assignment: Dict[int, int] = {}
        self._tle_cache: Optional[List[dict]] = None
        self._tle_cache_time: float = 0.0
        self._tle_ttl_sec: int = 300

        # ---- SatNOGS (Ground) ----
        self._gn_assignment: Dict[int, int] = {}      # node_id ground -> index in satnogs list
        self._satnogs_cache: Optional[List[dict]] = None
        self._satnogs_cache_time: float = 0.0
        self._satnogs_ttl_sec: int = 1800             # 30 phút

        # ---- NDBC (buoys/shore stations) ----
        self._ndbc_assignment: Dict[int, int] = {}    # node_id ground -> index in ndbc list
        self._ndbc_cache: Optional[List[dict]] = None
        self._ndbc_cache_time: float = 0.0
        self._ndbc_ttl_sec: int = 3600                # 60 phút

        # ---- OpenSky (Planes) ----
        self._plane_assignment: Dict[int, int] = {}   # node_id plane -> index in plane list
        self._opensky_cache: Optional[List[dict]] = None
        self._opensky_cache_time: float = 0.0
        self._opensky_ttl_sec: int = 15               # 15s (đủ “sống” mà đỡ gọi liên tục)

    # =======================
    #  Common helpers
    # =======================
    def _assign_indices(self, node_ids: List[int], universe_len: int, mapping: Dict[int,int]):
        """
        Gán mỗi node một index ổn định trong [0..universe_len-1].
        Nếu đã có, giữ nguyên. Nếu node mới, gán theo hash để ổn định.
        """
        if universe_len <= 0: return
        for nid in node_ids:
            if nid not in mapping:
                mapping[nid] = (hash(nid) % universe_len)

    # =======================
    #  CelesTrak (đã gửi trước)
    # =======================
    async def _fetch_active_tles(self) -> List[dict]:
        now = time.time()
        if self._tle_cache and now - self._tle_cache_time < self._tle_ttl_sec:
            return self._tle_cache
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
            async with sess.get(CELESTRAK_ACTIVE_JSON) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        self._tle_cache = [d for d in data if "TLE_LINE1" in d and "TLE_LINE2" in d]
        self._tle_cache_time = now
        return self._tle_cache

    def _assign_sat_indices(self, sat_nodes: List[int], tle_list_len: int):
        self._assign_indices(sat_nodes, tle_list_len, self._sat_assignment)

    async def update_from_celestrak(self, nodes: Dict[int, NodeInfo]):
        try:
            tle_list = await self._fetch_active_tles()
        except Exception:
            return nodes
        if not tle_list: return nodes

        sat_node_ids = [nid for nid, n in nodes.items() if n.kind == "sat"]
        if not sat_node_ids: return nodes

        self._assign_sat_indices(sat_node_ids, len(tle_list))

        t = time.gmtime()
        jd, fr = jday(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec + 0.0)

        for nid in sat_node_ids:
            idx = self._sat_assignment.get(nid, 0) % len(tle_list)
            tle = tle_list[idx]
            l1, l2 = tle["TLE_LINE1"].strip(), tle["TLE_LINE2"].strip()
            try:
                sat = Satrec.twoline2rv(l1, l2)
                e, r, v = sat.sgp4(jd, fr)
                if e != 0: continue
                r_ecef = teme_to_ecef(r, jd, fr)
                lat_deg, lon_deg, alt_km = ecef_to_geodetic_wgs84(r_ecef)
                n = nodes[nid]
                n.lat = float(lat_deg)
                n.lon = float(((lon_deg + 180) % 360) - 180)
                n.alt_km = max(0.0, float(alt_km))
            except Exception:
                pass
        return nodes

    # =======================
    #  SatNOGS (Ground)
    # =======================
    async def _fetch_satnogs(self) -> List[dict]:
        now = time.time()
        if self._satnogs_cache and now - self._satnogs_cache_time < self._satnogs_ttl_sec:
            return self._satnogs_cache
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sess:
            async with sess.get(SATNOGS_STATIONS_API) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        # Lọc những trạm có lat/lon hợp lệ; ưu tiên active
        stations = []
        for s in data:
            lat = s.get("latitude"); lon = s.get("longitude")
            if lat is None or lon is None: continue
            stations.append({
                "id": s.get("id"),
                "name": s.get("name") or s.get("station"),
                "lat": float(lat),
                "lon": float(lon),
                "alt_km": max(0.0, float(s.get("elevation") or 0.0)/1000.0),
                "active": bool(s.get("active", True))
            })
        # Sắp xếp active trước để gán “đẹp” hơn
        stations.sort(key=lambda x: (not x["active"], x["id"] or 0))
        self._satnogs_cache = stations
        self._satnogs_cache_time = now
        return self._satnogs_cache

    async def update_from_satnogs(self, nodes: Dict[int, NodeInfo]):
        """
        Gán các node kind='ground' từ danh sách trạm SatNOGS (lat/lon/alt=height).
        Không phải tất cả ground đều cần gán từ SatNOGS; bạn có thể chỉ gán một phần.
        """
        grounds = [nid for nid, n in nodes.items() if n.kind == "ground"]
        if not grounds:
            return nodes

        try:
            stations = await self._fetch_satnogs()
        except Exception:
            return nodes

        if not stations: 
            return nodes

        # Gán ổn định node ground -> một trạm SatNOGS
        self._assign_indices(grounds, len(stations), self._gn_assignment)

        for nid in grounds:
            idx = self._gn_assignment[nid] % len(stations)
            st = stations[idx]
            n = nodes[nid]
            n.lat = st["lat"]
            n.lon = ((st["lon"] + 180) % 360) - 180
            n.alt_km = st["alt_km"]
        return nodes

    # =======================
    #  NDBC (Buoys / SAGSIN / Shore)
    # =======================
    async def _fetch_ndbc(self) -> List[dict]:
        """
        Parse station_table.txt:
        Dòng dữ liệu thường dạng: <id> <name...> <lat> <lon> <type> ...
        File này không phải CSV chặt chẽ → ta parse “mạnh tay”: tìm 2 số float (lat/lon) trong dòng.
        """
        now = time.time()
        if self._ndbc_cache and now - self._ndbc_cache_time < self._ndbc_ttl_sec:
            return self._ndbc_cache

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sess:
            async with sess.get(NDBC_STATION_TABLE) as resp:
                resp.raise_for_status()
                text = await resp.text()

        stations = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): 
                continue
            # tách theo khoảng trắng
            parts = line.split()
            # tìm 2 số float liên tiếp coi như lat lon
            lat = lon = None
            floats = []
            for p in parts:
                try:
                    floats.append(float(p))
                except:
                    floats.append(None)
            # tìm cặp float
            for i in range(len(floats)-1):
                if floats[i] is not None and floats[i+1] is not None:
                    lat = floats[i]; lon = floats[i+1]; break
            if lat is None or lon is None:
                continue
            # id thường ở cột đầu
            st_id = parts[0]
            # name: ghép các token trước 2 số float
            try:
                name_end = floats.index(lat)  # vị trí token lat
            except ValueError:
                name_end = 1
            name = " ".join(parts[1:name_end]) if name_end > 1 else st_id
            stations.append({
                "id": st_id,
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "alt_km": 0.0,   # coi như mực nước biển
            })

        # Có thể lọc theo “SAGSIN” nếu bạn có danh sách mã trạm SAGSIN cụ thể.
        self._ndbc_cache = stations
        self._ndbc_cache_time = now
        return self._ndbc_cache

    async def update_from_ndbc(self, nodes: Dict[int, NodeInfo]):
        """
        Bơm thêm/trộn toạ độ cho một số node ground từ danh sách NDBC.
        Nếu bạn muốn tách riêng: ví dụ “nửa số ground từ SatNOGS, nửa từ NDBC”.
        Ở đây làm đơn giản: nếu đã gán SatNOGS rồi thì bỏ qua; nếu chưa, gán từ NDBC.
        """
        grounds = [nid for nid, n in nodes.items() if n.kind == "ground"]
        if not grounds:
            return nodes

        try:
            ndbc = await self._fetch_ndbc()
        except Exception:
            return nodes
        if not ndbc:
            return nodes

        # Node nào chưa có trong _gn_assignment thì gán từ NDBC
        ungained = [nid for nid in grounds if nid not in self._gn_assignment]
        if not ungained:
            return nodes

        self._assign_indices(ungained, len(ndbc), self._ndbc_assignment)

        for nid in ungained:
            idx = self._ndbc_assignment[nid] % len(ndbc)
            st = ndbc[idx]
            n = nodes[nid]
            n.lat = st["lat"]
            n.lon = ((st["lon"] + 180) % 360) - 180
            n.alt_km = st["alt_km"]
        return nodes

    # =======================
    #  OpenSky (Planes)
    # =======================
    async def _fetch_opensky(self) -> List[dict]:
        now = time.time()
        if self._opensky_cache and now - self._opensky_cache_time < self._opensky_ttl_sec:
            return self._opensky_cache

        auth = None
        u = os.getenv("OPENSKY_USER"); p = os.getenv("OPENSKY_PASS")
        if u and p:
            auth = aiohttp.BasicAuth(u, p)

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10), auth=auth) as sess:
            async with sess.get(OPENSKY_STATES_ALL) as resp:
                # Không raise ngay để chấp nhận 429/401 gracefully
                if resp.status != 200:
                    # fall back: giữ cache cũ
                    return self._opensky_cache or []
                data = await resp.json(content_type=None)

        # data['states'] là list, mỗi phần tử:
        # [0] icao24, [1] callsign, [2] origin_country, [5] lon, [6] lat, [13] geo_altitude(m), ...
        planes = []
        for st in (data.get("states") or []):
            try:
                lon = st[5]; lat = st[6]
                geo_alt_m = st[13]  # có thể None
                if lat is None or lon is None:
                    continue
                alt_km = max(0.0, float(geo_alt_m)/1000.0) if geo_alt_m is not None else 10.0 # fallback ~10km
                planes.append({
                    "icao24": st[0], "callsign": (st[1] or "").strip(),
                    "lat": float(lat), "lon": float(lon), "alt_km": float(alt_km)
                })
            except Exception:
                continue

        # nếu rỗng, giữ cache cũ (nếu có)
        if not planes:
            return self._opensky_cache or []

        self._opensky_cache = planes
        self._opensky_cache_time = now
        return self._opensky_cache

    async def update_from_opensky(self, nodes: Dict[int, NodeInfo]):
        """
        Gán node kind='plane' từ OpenSky states/all.
        Với số node > số máy bay: node sẽ “chia sẻ” 1 máy bay (modulo).
        """
        plane_nodes = [nid for nid, n in nodes.items() if n.kind == "plane"]
        if not plane_nodes:
            return nodes

        try:
            planes = await self._fetch_opensky()
        except Exception:
            return nodes
        if not planes:
            return nodes

        self._assign_indices(plane_nodes, len(planes), self._plane_assignment)

        for nid in plane_nodes:
            idx = self._plane_assignment[nid] % len(planes)
            st = planes[idx]
            n = nodes[nid]
            n.lat = st["lat"]
            n.lon = ((st["lon"] + 180) % 360) - 180
            n.alt_km = max(0.0, st["alt_km"])
        return nodes

    # =======================
    #  Sẵn có: populate & tick mock
    # =======================
    async def populate_initial(self, nodes: Dict[int, NodeInfo]):
        # ... (giữ nguyên như bạn đang có)
        for nid, n in nodes.items():
            if n.kind == "ground":
                n.lat = random.uniform(-60, 60)
                n.lon = random.uniform(-180, 180)
                n.alt_km = 0.0
            elif n.kind == "sat":
                n.lat = random.uniform(-60, 60)
                n.lon = random.uniform(-180, 180)
                n.alt_km = random.uniform(400, 800)
            else: # plane
                n.lat = random.uniform(-60, 60)
                n.lon = random.uniform(-180, 180)
                n.alt_km = random.uniform(9, 12)
        return nodes

    async def tick_update(self, nodes: Dict[int, NodeInfo]):
        # ... (giữ nguyên mô phỏng nhỏ cho mượt mà)
        for n in nodes.values():
            if n.kind in ("sat", "plane"):
                n.lon += random.uniform(-0.5, 0.5)
                n.lat += random.uniform(-0.2, 0.2)
                if n.lon > 180: n.lon -= 360
                if n.lon < -180: n.lon += 360
                n.lat = max(-85, min(85, n.lat))
        return nodes
