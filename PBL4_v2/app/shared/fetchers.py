import requests
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Any


SATELLITE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json"
GROUND_STATIONS_URL = "https://network.satnogs.org/api/stations/"  # paginated
SAGSIN_TABLE_URL = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"
AIRCRAFT_URL = "https://opensky-network.org/api/states/all"


@dataclass
class Position:
    lat: float
    lon: float
    alt_km: float | None = None


@dataclass
class Satellite:
    norad_id: int
    name: str
    position: Position | None = None


@dataclass
class GroundStation:
    id: int | str
    name: str
    position: Position


@dataclass
class Aircraft:
    icao24: str
    callsign: str | None
    position: Position | None


class DataFetcher:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self._satellites: Dict[int, Satellite] = {}
        self._ground_stations: Dict[str, GroundStation] = {}
        self._aircraft: Dict[str, Aircraft] = {}
        self.last_refresh: float | None = None

    # Public API
    def refresh_all(self):
        self.fetch_satellites(limit=50)
        self.fetch_ground_stations(limit=30)
        self.fetch_aircraft(limit=50)
        self.last_refresh = time.time()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "satellites": [asdict(s) for s in self._satellites.values()],
            "ground_stations": [asdict(g) for g in self._ground_stations.values()],
            "aircraft": [asdict(a) for a in self._aircraft.values()],
            "last_refresh": self.last_refresh,
        }

    # Fetchers
    def fetch_satellites(self, limit: int | None = None):
        try:
            resp = self.session.get(SATELLITE_URL, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            count = 0
            for sat in data:
                if limit and count >= limit:
                    break
                try:
                    norad = int(sat.get("NORAD_CAT_ID"))
                except Exception:
                    continue
                name = sat.get("OBJECT_NAME", f"SAT-{norad}")
                # Position not directly in GP JSON; left None for now (would require propagation via SGP4)
                self._satellites[norad] = Satellite(norad_id=norad, name=name)
                count += 1
        except Exception as e:
            print("[fetch] satellites error", e)

    def fetch_ground_stations(self, limit: int | None = None):
        try:
            # SatNOGS API is paginated. We'll just pull first page.
            resp = self.session.get(GROUND_STATIONS_URL, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            count = 0
            for g in data:
                if limit and count >= limit:
                    break
                try:
                    gid = g.get("id")
                    name = g.get("name") or f"GS-{gid}"
                    lat = float(g.get("lat"))
                    lon = float(g.get("lng"))
                except Exception:
                    continue
                pos = Position(lat=lat, lon=lon, alt_km=0)
                self._ground_stations[str(gid)] = GroundStation(id=gid, name=name, position=pos)
                count += 1
        except Exception as e:
            print("[fetch] ground stations error", e)

    def fetch_aircraft(self, limit: int | None = None):
        try:
            resp = self.session.get(AIRCRAFT_URL, timeout=20)
            if resp.status_code == 429:
                print("[fetch] aircraft rate limited")
                return
            resp.raise_for_status()
            data = resp.json()
            states = data.get("states", [])
            count = 0
            for st in states:
                if limit and count >= limit:
                    break
                if not isinstance(st, list) or len(st) < 17:
                    continue
                icao24 = st[0]
                callsign = st[1].strip() if st[1] else None
                lat = st[6]
                lon = st[5]
                baro_alt = st[7]
                if lat is None or lon is None:
                    continue
                alt_km = baro_alt / 1000.0 if baro_alt else None
                pos = Position(lat=lat, lon=lon, alt_km=alt_km)
                self._aircraft[icao24] = Aircraft(icao24=icao24, callsign=callsign, position=pos)
                count += 1
        except Exception as e:
            print("[fetch] aircraft error", e)
