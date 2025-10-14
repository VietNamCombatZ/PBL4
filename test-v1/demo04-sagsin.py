# SAGSIN animation (LOS + Range + dynamic links + ORBITS/TRAILS)
# Satellites: circular/elliptic orbits
# UAVs: waypoints / circle / ellipse patterns
# Realtime animation (optional GIF export), Earth textured (fallback to wireframe)
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.lines import Line2D
from PIL import Image
import math
from collections import deque

from matplotlib.widgets import Button
try:
    # Matplotlib >= 3.5 có Dropdown
    from matplotlib.widgets import Dropdown
    HAS_DROPDOWN = True
except Exception:
    from matplotlib.widgets import TextBox
    HAS_DROPDOWN = False


# EARTH_TEXTURE_PATH = "./metadata/earth02.jpg"  # để rỗng "" nếu không có ảnh
EARTH_TEXTURE_PATH = ""

# ---------- Geometry helpers ----------
RE = 6371.0  # Earth radius (km)

def norm(v):
    return float(np.sqrt(np.dot(v, v)))

def unit(v):
    n = norm(v)
    return np.array(v, dtype=float)/n if n > 0 else np.array([1.0,0.0,0.0])

def rotate_vector(v, axis, angle_rad):
    # Rodrigues rotation
    k = unit(axis)
    v = np.array(v, dtype=float)
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return v*c + np.cross(k, v)*s + k*np.dot(k, v)*(1 - c)

def orthonormal_basis_from_normal(n_hat, preferred=None):
    n_hat = unit(n_hat)
    if preferred is None:
        # pick any vector not parallel to n_hat
        t = np.array([1.0, 0.0, 0.0]) if abs(n_hat[0]) < 0.9 else np.array([0.0,1.0,0.0])
    else:
        t = np.array(preferred, dtype=float)
    u_hat = unit(np.cross(n_hat, np.cross(t, n_hat)))
    v_hat = unit(np.cross(n_hat, u_hat))
    return u_hat, v_hat, n_hat  # plane basis (u along "x", v along "y")

def great_circle_xyz(lat_deg, lon_deg, h_km=0.0):
    lat = np.deg2rad(lat_deg); lon = np.deg2rad(lon_deg)
    r = RE + h_km
    return np.array([r*np.cos(lat)*np.cos(lon),
                     r*np.cos(lat)*np.sin(lon),
                     r*np.sin(lat)], dtype=float)


# ---- Find path ---- #
def shortest_path_dijkstra(n_nodes, links, src_idx, dst_idx):
    """
    links: list[(i,j,d)] như compute_links trả về (đồ thị vô hướng, trọng số = d)
    trả về: list chỉ số node tạo thành path; [] nếu không tới được
    """
    adj = [[] for _ in range(n_nodes)]
    for i, j, d in links:
        adj[i].append((j, d))
        adj[j].append((i, d))
    import heapq
    INF = 1e30
    dist = [INF]*n_nodes
    prev = [-1]*n_nodes
    dist[src_idx] = 0.0
    pq = [(0.0, src_idx)]
    while pq:
        du, u = heapq.heappop(pq)
        if du != dist[u]: 
            continue
        if u == dst_idx:
            break
        for v, w in adj[u]:
            nd = du + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if dist[dst_idx] == INF:
        return []
    # reconstruct
    path = []
    cur = dst_idx
    while cur != -1:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path

import random

class ACOPathFinder:
    """
    ACO cho routing nhất thời trên đồ thị links (i,j,d).
    alpha: trọng số pheromone
    beta:  trọng số heuristic (1/d)
    rho:   hệ số bay hơi pheromone (0..1)
    Q:     lượng pheromone đổ cho đường tốt
    ants:  số kiến mỗi vòng
    iters: số vòng lặp
    allow_revisit: cho kiến quay lại nút cũ khi kẹt (giảm kẹt đồ thị thưa)
    """
    def __init__(self, n_nodes, links, alpha=1.0, beta=2.0, rho=0.35, Q=120.0,
                 ants=28, iters=28, allow_revisit=True, seed=None):
        self.n = n_nodes
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.rho = float(rho)
        self.Q = float(Q)
        self.ants = int(ants)
        self.iters = int(iters)
        self.allow_revisit = bool(allow_revisit)
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        # adjacency và ma trận trọng số
        self.adj = [[] for _ in range(self.n)]
        self.w = {}   # (min(i,j),max(i,j)) -> distance
        for i, j, d in links:
            self.adj[i].append((j, d))
            self.adj[j].append((i, d))
            key = (min(i, j), max(i, j))
            self.w[key] = float(d)

        # pheromone khởi tạo
        tau0 = 1.0
        self.tau = {key: tau0 for key in self.w.keys()}

    def _edge_key(self, a, b):
        return (a, b) if a < b else (b, a)

    def _choose_next(self, u, visited):
        nbrs = self.adj[u]
        if not nbrs:
            return None
        probs = []
        nodes = []
        for v, d in nbrs:
            # chặn vòng lặp vô hạn: nếu không cho revisit thì skip v đã thăm
            if (not self.allow_revisit) and (v in visited):
                continue
            key = self._edge_key(u, v)
            tau = self.tau.get(key, 1e-6)
            eta = 1.0 / max(d, 1e-9)  # heuristic: nghịch đảo khoảng cách
            score = (tau ** self.alpha) * (eta ** self.beta)
            if score <= 0:
                continue
            probs.append(score)
            nodes.append((v, d))
        if not nodes:
            return None
        probs = np.array(probs, dtype=float)
        probs /= probs.sum()
        idx = np.random.choice(len(nodes), p=probs)
        return nodes[idx]  # (v, d)

    def _path_length(self, path):
        L = 0.0
        for a, b in zip(path[:-1], path[1:]):
            L += self.w[self._edge_key(a, b)]
        return L

    def _deposit(self, path, L):
        if L <= 0 or len(path) < 2:
            return
        delta = self.Q / L
        for a, b in zip(path[:-1], path[1:]):
            key = self._edge_key(a, b)
            self.tau[key] = self.tau.get(key, 0.0) + delta

    def solve(self, src, dst):
        best_path = []
        best_L = float('inf')

        # Nếu không có cạnh từ src hoặc đến dst -> thua ngay
        if not self.adj[src] or not self.adj[dst]:
            return []

        for _ in range(self.iters):
            iter_best = None
            iter_best_L = float('inf')

            # Mỗi vòng: bay hơi trước (cách phổ biến, có thể đổi thứ tự)
            for k in list(self.tau.keys()):
                self.tau[k] *= (1.0 - self.rho)
                if self.tau[k] < 1e-12:
                    self.tau[k] = 1e-12

            # Đội kiến xuất phát
            for _ant in range(self.ants):
                u = src
                visited = set([u])
                path = [u]
                steps = 0
                max_steps = self.n * 3  # giới hạn chiều dài để tránh lạc vô hạn

                while u != dst and steps < max_steps:
                    choice = self._choose_next(u, visited)
                    if choice is None:
                        # nếu kẹt: thử nới lỏng một lần bằng cách cho phép quay lại nút gần nhất
                        if not self.allow_revisit:
                            break
                        # allow revisit: cho xét mọi hàng xóm (kể cả visited)
                        # làm lại chọn next với allow_revisit=True tạm thời
                        nbrs = self.adj[u]
                        if not nbrs:
                            break
                        # soft-choice
                        nodes, probs = [], []
                        for v, d in nbrs:
                            key = self._edge_key(u, v)
                            tau = self.tau.get(key, 1e-6)
                            eta = 1.0 / max(d, 1e-9)
                            score = (tau ** self.alpha) * (eta ** self.beta)
                            if score <= 0:
                                continue
                            nodes.append((v, d))
                            probs.append(score)
                        if not nodes:
                            break
                        probs = np.array(probs, dtype=float); probs /= probs.sum()
                        v, d = nodes[np.random.choice(len(nodes), p=probs)]
                    else:
                        v, d = choice

                    path.append(v)
                    u = v
                    steps += 1
                    visited.add(u)

                if path[-1] == dst:
                    L = self._path_length(path)
                    if L < iter_best_L:
                        iter_best_L = L
                        iter_best = path

            # đổ pheromone cho đường tốt nhất của vòng
            if iter_best is not None:
                self._deposit(iter_best, iter_best_L)
                if iter_best_L < best_L:
                    best_L = iter_best_L
                    best_path = iter_best

        return best_path


# ---- Ping manager ---- #
class PingManager:
    def __init__(self, ax3d, ax_text=None):
        self.ax3d = ax3d
        self.ax_text = ax_text  # panel phải để ghi thông tin đường/relay
        self.active = False
        self.speed_km_s = 80000.0  # tốc độ hiển thị (chậm hơn tốc độ ánh sáng để nhìn rõ)
        self.path_idxs = []
        self.edges = []  # list[(a,b)]
        self.edge_idx = 0
        self.edge_s_travel = 0.0  # đã đi trên cạnh hiện tại (km)
        self.marker = ax3d.scatter([], [], [], s=30)  # điểm “ping”
        self.hl_lines = []  # các đường highlight
        self._path_label = None  # Text object trong panel phải

    def cleanup(self):
        for ln in self.hl_lines:
            try: ln.remove()
            except: pass
        self.hl_lines.clear()
        # ẩn marker
        self.marker._offsets3d = (np.array([]), np.array([]), np.array([]))
        if self._path_label is not None:
            try:
                self._path_label.set_text("")
            except:
                pass
        self.active = False

    def start(self, path_idxs, nodes):
        self.cleanup()
        if len(path_idxs) < 2:
            self.active = False
            self._write_text("Ping path: (no route)")
            return
        self.path_idxs = list(path_idxs)
        self.edges = list(zip(self.path_idxs[:-1], self.path_idxs[1:]))
        self.edge_idx = 0
        self.edge_s_travel = 0.0
        # vẽ highlight các cạnh lúc bắt đầu
        for (a, b) in self.edges:
            p = nodes[a].pos; q = nodes[b].pos
            ln, = self.ax3d.plot([p[0], q[0]], [p[1], q[1]], [p[2], q[2]], linewidth=2.0, alpha=0.85)
            self.hl_lines.append(ln)
        # đặt marker tại src
        src = nodes[self.path_idxs[0]].pos
        self.marker._offsets3d = (np.array([src[0]]), np.array([src[1]]), np.array([src[2]]))
        # ghi relay list
        names = [nodes[i].name for i in self.path_idxs]
        if len(names) >= 3:
            relays = names[1:-1]
            relay_str = " → ".join(relays) if relays else "(none)"
        else:
            relay_str = "(none)"
        self._write_text(f"Ping path:\n{ ' → '.join(names) }\nRelays: {relay_str}")
        self.active = True

    def _write_text(self, s):
        if self.ax_text is None:
            return
        if self._path_label is None:
            # gắn text ở phía dưới bảng ma trận
            self._path_label = self.ax_text.text(
                0.01, 0.02, s, family='monospace', fontsize=9, va='bottom', ha='left'
            )
        else:
            self._path_label.set_text(s)

    def update_lines(self, nodes):
        """Cập nhật các đoạn highlight theo vị trí node mới (vì node di chuyển)."""
        for ln, (a, b) in zip(self.hl_lines, self.edges):
            p = nodes[a].pos; q = nodes[b].pos
            ln.set_data([p[0], q[0]], [p[1], q[1]])
            try:
                ln.set_3d_properties([p[2], q[2]])
            except Exception:
                pass

    def step(self, dt, nodes, links_dict):
        if not self.active:
            return
        # nếu đã xong hết cạnh → tắt
        if self.edge_idx >= len(self.edges):
            self.active = False
            return
        a, b = self.edges[self.edge_idx]
        key = (min(a, b), max(a, b))
        # nếu link hiện tại đứt (LOS hoặc range thay đổi) → huỷ ping
        if key not in links_dict:
            self._write_text("Ping dropped: link broken.")
            self.active = False
            return
        p = nodes[a].pos; q = nodes[b].pos
        length = norm(q - p)
        # tiến dọc cạnh
        self.edge_s_travel += dt * self.speed_km_s
        s = self.edge_s_travel / max(length, 1e-9)
        if s >= 1.0:
            # tới node b
            self.marker._offsets3d = (np.array([q[0]]), np.array([q[1]]), np.array([q[2]]))
            self.edge_idx += 1
            self.edge_s_travel = 0.0
            if self.edge_idx >= len(self.edges):
                self._write_text("Ping delivered ✅")
                self.active = False
            return
        pos = p + (q - p) * s
        self.marker._offsets3d = (np.array([pos[0]]), np.array([pos[1]]), np.array([pos[2]]))


# ---- LOS check: segment vs Earth sphere intersection ----
def segment_intersects_earth(p1, p2, R=RE):
    p1 = np.asarray(p1, dtype=float); p2 = np.asarray(p2, dtype=float)
    d = p2 - p1
    a = float(np.dot(d, d))
    if a == 0:
        return float(np.dot(p1, p1)) < R*R
    b = 2.0*float(np.dot(p1, d))
    c = float(np.dot(p1, p1)) - R*R
    t = -b / (2.0*a)
    t = max(0.0, min(1.0, t))
    closest = p1 + t*d
    return float(np.dot(closest, closest)) < R*R

def has_los(p1, p2):
    return not segment_intersects_earth(p1, p2, RE)

# ---------- Node base ----------
class Node:
    def __init__(self, name, kind, pos, range_km, trail_len=200):
        self.name = name
        self.kind = kind  # "sat", "uav", "ground", "sea"
        self.pos = np.array(pos, dtype=float)
        self.range_km = float(range_km)
        self.trail = deque(maxlen=trail_len)  # list of positions for drawing path
        self.trail.append(self.pos.copy())
    def step(self, dt): pass

# ---------- Satellites ----------
class Satellite(Node):
    """
    orbit_type: "circular" or "elliptic"
      - circular: like before, rotate around n_hat with angular speed omega
      - elliptic:
          a_km: semi-major axis (km)
          e: eccentricity (0<e<1)
          periapsis_angle_rad: rotation inside orbital plane (argument of periapsis)
          mean_motion_rad_s: if None, use omega_rad_s as mean motion
    """
    def __init__(self, name,
                 altitude_km=None,  # used only for circular default radius
                 n_hat=(0,0,1),
                 pos0=None,
                 omega_rad_s=None,
                 range_km=2500,
                 orbit_type="circular",
                 a_km=None, e=0.0, periapsis_angle_rad=0.0, mean_motion_rad_s=None,
                 plane_reference_dir=None):
        radius = RE + (altitude_km if altitude_km is not None else 500.0)
        super().__init__(name, "sat", pos0 if pos0 is not None else [radius, 0, 0], range_km)
        self.orbit_type = orbit_type
        self.n_hat = unit(np.asarray(n_hat, dtype=float))
        # circular params
        if omega_rad_s is None:
            T = 5400.0  # ~90min
            omega_rad_s = 2*np.pi / T
        self.omega = float(omega_rad_s)
        self.radius_circ = radius
        # elliptic params
        self.a_km = a_km if a_km is not None else radius
        self.e = float(e)
        self.periapsis_angle = float(periapsis_angle_rad)
        self.mean_motion = mean_motion_rad_s if mean_motion_rad_s is not None else self.omega
        # plane basis (u along periapsis direction)
        u_hat, v_hat, _ = orthonormal_basis_from_normal(self.n_hat, preferred=plane_reference_dir)
        # rotate u_hat by periapsis angle in plane to align perigee direction
        self.u_hat = rotate_vector(u_hat, self.n_hat, self.periapsis_angle)
        self.v_hat = unit(np.cross(self.n_hat, self.u_hat))
        # anomaly state
        self._M = 0.0  # mean anomaly

        # if circular and no pos0, set pos on circle
        if pos0 is None and orbit_type == "circular":
            self.pos = self.u_hat * self.radius_circ  # start at periapsis-like direction
        elif pos0 is None and orbit_type == "elliptic":
            # start at periapsis
            r0 = self.a_km * (1 - self.e)
            self.pos = self.u_hat * r0

    def _elliptic_step(self, dt):
        # advance mean anomaly
        self._M += self.mean_motion * dt
        # solve Kepler: M = E - e*sinE
        E = self._solve_kepler(self._M, self.e)
        # true anomaly
        cosE, sinE = np.cos(E), np.sin(E)
        r = self.a_km * (1.0 - self.e*cosE)
        # relation: tan(f/2) = sqrt((1+e)/(1-e)) * tan(E/2)
        f = 2.0*np.arctan2(np.sqrt(1+self.e)*sinE, np.sqrt(1-self.e)*(1+cosE))
        cf, sf = np.cos(f), np.sin(f)
        # position in orbital plane
        pos_plane = self.u_hat * (r*cf) + self.v_hat * (r*sf)
        self.pos = pos_plane

    @staticmethod
    def _solve_kepler(M, e, tol=1e-10, itmax=20):
        # Newton-Raphson for E - e*sinE - M = 0
        E = M if e < 0.8 else np.pi
        for _ in range(itmax):
            f = E - e*np.sin(E) - M
            fp = 1 - e*np.cos(E)
            dE = -f/fp
            E += dE
            if abs(dE) < tol:
                break
        return E

    def step(self, dt):
        if self.orbit_type == "circular":
            # rotate current pos around plane normal
            r = unit(self.pos) * self.radius_circ
            self.pos = rotate_vector(r, self.n_hat, self.omega*dt)
        else:
            self._elliptic_step(dt)
        self.trail.append(self.pos.copy())

# ---------- UAVs ----------
class UAV(Node):
    """
    pattern: "waypoints" (default), "circle", "ellipse"
      - waypoints: như cũ
      - circle: bay trong MẶT PHẲNG bất kỳ (tâm center, pháp tuyến plane_n, bán kính R_km, tốc độ góc omega)
      - ellipse: tương tự circle nhưng 2 bán kính Rx_km, Ry_km
    """
    def __init__(self, name, pos0, waypoints,
                 speed_km_s=0.15, wp_tolerance_km=1.0, range_km=150,
                 pattern="waypoints",
                 center=None, plane_n=None, R_km=20.0, Rx_km=30.0, Ry_km=15.0,
                 angular_rate_rad_s=0.01, phase0_rad=0.0,
                 trail_len=400):
        super().__init__(name, "uav", pos0, range_km, trail_len=trail_len)
        self.pattern = pattern
        self.waypoints = [np.array(w, dtype=float) for w in waypoints] if waypoints else []
        self.speed = speed_km_s
        self.tol = wp_tolerance_km
        self.idx = 0
        # circle/ellipse params
        self.center = np.array(center, dtype=float) if center is not None else np.array(pos0, dtype=float)
        self.plane_n = unit(np.array(plane_n, dtype=float)) if plane_n is not None else unit(self.center)
        self.R_km = float(R_km)
        self.Rx_km = float(Rx_km)
        self.Ry_km = float(Ry_km)
        self.omega = float(angular_rate_rad_s)
        self.theta = float(phase0_rad)
        # basis in plane
        self.u_hat, self.v_hat, _ = orthonormal_basis_from_normal(self.plane_n, preferred=[1,0,0])

    def _step_waypoints(self, dt):
        if not self.waypoints:
            return
        target = self.waypoints[self.idx]
        dvec = target - self.pos; d = norm(dvec)
        if d < self.tol:
            self.idx = (self.idx + 1) % len(self.waypoints)
            return
        step_len = min(d, self.speed*dt)
        if d > 0:
            self.pos = self.pos + (dvec/d)*step_len

    def _step_circle(self, dt):
        self.theta += self.omega * dt
        self.pos = self.center + self.u_hat*(self.R_km*np.cos(self.theta)) + self.v_hat*(self.R_km*np.sin(self.theta))

    def _step_ellipse(self, dt):
        self.theta += self.omega * dt
        self.pos = self.center + self.u_hat*(self.Rx_km*np.cos(self.theta)) + self.v_hat*(self.Ry_km*np.sin(self.theta))

    def step(self, dt):
        if self.pattern == "circle":
            self._step_circle(dt)
        elif self.pattern == "ellipse":
            self._step_ellipse(dt)
        else:
            self._step_waypoints(dt)
        self.trail.append(self.pos.copy())

# ---------- Static nodes ----------
class StaticNode(Node):
    def __init__(self, name, kind, pos0, range_km, drift_km_s=0.0, drift_dir=None, trail_len=200):
        super().__init__(name, kind, pos0, range_km, trail_len=trail_len)
        self.drift = drift_km_s
        self.drift_dir = None if drift_dir is None else unit(np.array(drift_dir, dtype=float))
    def step(self, dt):
        if self.drift > 0 and self.drift_dir is not None:
            self.pos = self.pos + self.drift_dir*self.drift*dt
            r = norm(self.pos)
            if r != 0:
                self.pos = (self.pos/r)*RE
        self.trail.append(self.pos.copy())

# ---------- Scenario ----------
def build_nodes():
    nodes = []

    # Ground
    dn = great_circle_xyz(10.3815, 106.5422, 0.0)
    hn = great_circle_xyz(55.7558, 37.6173, 0.0)
    nodes.append(StaticNode("Danang-GS", "ground", dn, range_km=1200))
    nodes.append(StaticNode("Hanoi-GS",  "ground", hn, range_km=1200))

    # Sea (trôi nhẹ)
    ship = StaticNode("Ship-1", "sea", great_circle_xyz(14.0, 111.0, 0.0),
                      range_km=500, drift_km_s=0.02, drift_dir=[1,0,0], trail_len=500)
    nodes.append(ship)

    # UAVs: 1 waypoint, 1 circle, 1 ellipse (đặt gần Đà Nẵng, cao ~5km)
    wp = [great_circle_xyz(16.00,108.10,5.0),
          great_circle_xyz(16.10,108.20,5.0),
          great_circle_xyz(16.00,108.30,5.0),
          great_circle_xyz(15.90,108.20,5.0)]
    nodes.append(UAV("UAV-Alpha", wp[0], wp, speed_km_s=0.14, range_km=180, pattern="waypoints", trail_len=600))

    # UAV bay vòng tròn trong mặt phẳng tiếp tuyến tại tâm gần ĐN
    center_circle = great_circle_xyz(16.02,108.18,5.0)
    plane_n_circle = unit(center_circle)  # mặt phẳng tiếp tuyến
    nodes.append(UAV("UAV-Circle", center_circle + np.array([10,0,0]), None,
                     range_km=180, pattern="circle",
                     center=center_circle, plane_n=plane_n_circle,
                     R_km=30.0, angular_rate_rad_s=0.02, phase0_rad=0.0, trail_len=600))

    # UAV bay ellipse trong mặt phẳng tiếp tuyến
    center_ellipse = great_circle_xyz(16.05,108.25,5.0)
    plane_n_ellipse = unit(center_ellipse)
    nodes.append(UAV("UAV-Ellipse", center_ellipse + np.array([20,0,0]), None,
                     range_km=180, pattern="ellipse",
                     center=center_ellipse, plane_n=plane_n_ellipse,
                     Rx_km=40.0, Ry_km=20.0, angular_rate_rad_s=0.015, phase0_rad=0.5, trail_len=600))

    # Satellites
    # 1 circular LEO
    nodes.append(Satellite("Sat-Circ", altitude_km=550, n_hat=[0.2,1.0,0.1],
                           pos0=None, omega_rad_s=0.01, range_km=2600,
                           orbit_type="circular", plane_reference_dir=[1,0,0]))
    # 2 elliptic with different eccentricities/planes
    nodes.append(Satellite("Sat-E1",
                           n_hat=[1.0,0.2,0.3],
                           orbit_type="elliptic",
                           a_km=RE+700, e=0.15, periapsis_angle_rad=0.3,
                           mean_motion_rad_s=0.007, range_km=2800,
                           plane_reference_dir=[0,1,0]))
    nodes.append(Satellite("Sat-E2",
                           n_hat=[-0.3,0.8,0.5],
                           orbit_type="elliptic",
                           a_km=RE+900, e=0.25, periapsis_angle_rad=-0.6,
                           mean_motion_rad_s=0.006, range_km=3000,
                           plane_reference_dir=[0,0,1]))
    return nodes

# ---------- Link computation ----------
def compute_links(nodes):
    links = []
    N = len(nodes)
    for i in range(N):
        for j in range(i+1, N):
            a = nodes[i]; b = nodes[j]
            d = norm(a.pos - b.pos)
            if d <= min(a.range_km, b.range_km) and has_los(a.pos, b.pos):
                links.append((i, j, d))
    return links

# ---------- Coordinate matrix string ----------
def coords_matrix_str(nodes, t_s=None):
    """Trả về chuỗi ma trận tọa độ dạng bảng (monospace) cho panel bên phải."""
    lines = []
    if t_s is not None:
        lines.append(f"t = {t_s:8.2f} s")
        lines.append("")  # dòng trống

    header = f"{'Name':14s} {'Type':7s} {'X(km)':>12s} {'Y(km)':>12s} {'Z(km)':>12s}"
    lines.append(header)
    lines.append("-"*len(header))
    for n in nodes:
        x, y, z = n.pos
        lines.append(f"{n.name:14s} {n.kind:7s} {x:12.1f} {y:12.1f} {z:12.1f}")
    return "\n".join(lines)


# ---------- Earth textured drawing ----------
def draw_earth_textured(ax, radius=RE, tex_path=EARTH_TEXTURE_PATH):
    try:
        if not tex_path:
            raise FileNotFoundError("No texture path provided")
        # mesh for texture
        nu, nv = 90, 45  # tăng giảm theo hiệu năng
        u = np.linspace(0, 2*np.pi, nu)
        v = np.linspace(-np.pi/2, np.pi/2, nv)
        U, V = np.meshgrid(u, v)
        X = radius*np.cos(V)*np.cos(U)
        Y = radius*np.cos(V)*np.sin(U)
        Z = radius*np.sin(V)

        img = Image.open(tex_path).convert("RGBA")
        tex = np.array(img)
        H, W = tex.shape[:2]
        x_idx = (U/(2*np.pi)*W).astype(int) % W
        y_idx = ((-V + np.pi/2)/np.pi*H).astype(int)
        y_idx = np.clip(y_idx, 0, H-1)

        facecolors = tex[y_idx, x_idx]/255.0
        if facecolors.shape[-1] == 3:
            alpha = np.ones(facecolors.shape[:2] + (1,))
            facecolors = np.concatenate([facecolors, alpha], axis=-1)

        ax.plot_surface(X, Y, Z, rstride=1, cstride=1,
                        facecolors=facecolors, linewidth=0, antialiased=False)
    except Exception as e:
        # Fallback: wireframe
        u = np.linspace(0, 2*np.pi, 40)
        v = np.linspace(-np.pi/2, np.pi/2, 20)
        xs = radius*np.outer(np.cos(v), np.cos(u))
        ys = radius*np.outer(np.cos(v), np.sin(u))
        zs = radius*np.outer(np.sin(v), np.ones_like(u))
        ax.plot_wireframe(xs, ys, zs, linewidth=0.5)
        print("Earth texture fallback to wireframe:", e)

# ---------- Main (simulation + animation) ----------
def run(save_csv=True, save_path_csv="sagsin_all_nodes_coordinates.csv",
        save_gif=False, save_path_gif="sagsin_full_animation.gif",
        steps=300, dt=1.5, trail_max_points=400,
        show_matrix_panel=True):
    # 1) Log positions (optional CSV)
    nodes = build_nodes()
    records = []
    for k in range(steps):
        t = k*dt
        for n in nodes:
            records.append((t, n.name, n.kind, n.pos[0], n.pos[1], n.pos[2]))
        for n in nodes: 
            n.step(dt)
    df = pd.DataFrame(records, columns=["t_s","name","kind","x_km","y_km","z_km"])
    if save_csv: 
        df.to_csv(save_path_csv, index=False)

    # 2) Animation (reset to t=0)
    nodes = build_nodes()

    # --- Figure + layout: 3D (trái) + Matrix panel (phải) ---
    if show_matrix_panel:
        fig = plt.figure(figsize=(12, 7))
        gs = fig.add_gridspec(1, 2, width_ratios=[3.0, 1.6])
        ax = fig.add_subplot(gs[0, 0], projection='3d')
        axM = fig.add_subplot(gs[0, 1])
        axM.axis('off')
        axM.set_title("Coordinate Matrix (km)")
        table_text = axM.text(0.01, 0.98, coords_matrix_str(nodes, t_s=0.0),
                              family='monospace', fontsize=9, va='top', ha='left')
    else:
        fig = plt.figure()
        ax = fig.add_subplot(projection='3d')
        table_text = None

    draw_earth_textured(ax, radius=RE, tex_path=EARTH_TEXTURE_PATH)

    # Limits & view
    lim = 9000
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
    ax.view_init(elev=22, azim=35)

    # Initial scatters + labels + trails
    marker_by_kind = {"sat": "x", "uav": "o", "ground": "^", "sea": "s"}
    scatters, labels, trail_lines = [], [], []
    for n in nodes:
        sc = ax.scatter([n.pos[0]],[n.pos[1]],[n.pos[2]], marker=marker_by_kind.get(n.kind,"o"))
        lb = ax.text(n.pos[0], n.pos[1], n.pos[2], n.name)
        tl, = ax.plot([p[0] for p in n.trail],
                      [p[1] for p in n.trail],
                      [p[2] for p in n.trail], linewidth=0.6)
        scatters.append(sc); labels.append(lb); trail_lines.append(tl)

    # Legend
    legend_elems = [
        Line2D([0],[0], marker='x', linestyle='None', label='Satellite'),
        Line2D([0],[0], marker='o', linestyle='None', label='UAV'),
        Line2D([0],[0], marker='^', linestyle='None', label='Ground'),
        Line2D([0],[0], marker='s', linestyle='None', label='Sea'),
    ]
    ax.legend(handles=legend_elems, loc='upper left')
    ax.set_box_aspect([1,1,1])
    ax.set_xlabel("X (km)"); ax.set_ylabel("Y (km)"); ax.set_zlabel("Z (km)")
    ax.set_title("SAGSIN (LOS + Range links + Orbits/Trails)")

    if show_matrix_panel:
        # “khung” giả giúp layout text không bị co cụm ở cạnh
        axM.set_xlim(0, 1); axM.set_ylim(0, 1)

    fig.tight_layout()

        # --- UI: Dropdown/TextBox + Button ---
    names = [n.name for n in nodes]
    name_to_idx = {n.name: i for i, n in enumerate(nodes)}

    # vùng axes cho UI (tọa độ figure normalized)
    # đặt ở panel phải (axM) phía trên/dưới bảng
    ax_src = fig.add_axes([0.63, 0.54, 0.23, 0.05])
    ax_dst = fig.add_axes([0.63, 0.47, 0.23, 0.05])
    ax_btn = fig.add_axes([0.68, 0.40, 0.13, 0.05])

    if HAS_DROPDOWN:
        dd_src = Dropdown(ax_src, label='Source', options=names, value=names[0])
        dd_dst = Dropdown(ax_dst, label='Target', options=names, value=names[1 if len(names) > 1 else 0])
        src_get = lambda: dd_src.value
        dst_get = lambda: dd_dst.value
    else:
        # fallback: TextBox (gõ đúng tên node)
        from matplotlib.widgets import TextBox
        dd_src = TextBox(ax_src, 'Source', initial=names[0])
        dd_dst = TextBox(ax_dst, 'Target', initial=names[1 if len(names) > 1 else 0])
        src_get = lambda: dd_src.text
        dst_get = lambda: dd_dst.text

    btn_ping = Button(ax_btn, 'Ping')

    # Ping manager
    ping = PingManager(ax, ax_text=axM if show_matrix_panel else None)

    # callback nút Ping
    def on_ping_clicked(event):
        s_name = src_get(); t_name = dst_get()
        if s_name not in name_to_idx or t_name not in name_to_idx:
            if show_matrix_panel:
                axM.text(0.01, 0.02, "Invalid source/target name.", family='monospace',
                         fontsize=9, va='bottom', ha='left')
            return
        si = name_to_idx[s_name]; ti = name_to_idx[t_name]
        if si == ti:
            ping.cleanup()
            if show_matrix_panel:
                axM.text(0.01, 0.02, "Source == Target.", family='monospace',
                         fontsize=9, va='bottom', ha='left')
            return

        # snapshot đồ thị hiện tại
        cur_links = compute_links(nodes)

        # --- ACO routing ---
        aco = ACOPathFinder(
            n_nodes=len(nodes),
            links=cur_links,
            alpha=1.0,     # pheromone weight
            beta=2.2,      # heuristic weight (1/distance)
            rho=0.35,      # evaporation
            Q=120.0,       # deposit strength
            ants=28,       # ants per iteration
            iters=28,      # iterations
            allow_revisit=True,
            seed=None      # đặt số để tái lập, ví dụ 42
        )
        path = aco.solve(si, ti)

        # fallback phòng hờ nếu ACO vẫn “bí”
        if not path:
            path = shortest_path_dijkstra(len(nodes), cur_links, si, ti)

        ping.start(path, nodes)


    btn_ping.on_clicked(on_ping_clicked)


    link_lines = []  # dynamic Line3D objects

    def init():
        artists = scatters + labels + trail_lines + link_lines
        if table_text is not None: 
            artists.append(table_text)
        return artists

    def animate(frame):
        # step dynamics
        for n in nodes: 
            n.step(dt)

        # update node positions & labels
        for i, n in enumerate(nodes):
            x, y, z = n.pos
            scatters[i]._offsets3d = (np.array([x]), np.array([y]), np.array([z]))
            labels[i].set_position((x, y))
            try:
                labels[i].set_3d_properties(z, zdir='z')
            except Exception:
                pass
            tr = np.array(n.trail)
            trail_lines[i].set_data(tr[:,0], tr[:,1])
            try:
                trail_lines[i].set_3d_properties(tr[:,2])
            except Exception:
                pass

        # recompute links and redraw lines
                # recompute links and redraw lines
        nonlocal link_lines
        for ln in link_lines: 
            ln.remove()
        link_lines = []
        cur_links = compute_links(nodes)
        # dict nhanh để kiểm tra tồn tại link
        links_dict = { (min(i,j), max(i,j)): d for (i,j,d) in cur_links }

        for i, j, d in cur_links:
            p = nodes[i].pos; q = nodes[j].pos
            ln, = ax.plot([p[0], q[0]], [p[1], q[1]], [p[2], q[2]], linewidth=0.8)
            link_lines.append(ln)

        # cập nhật “ma trận tọa độ”
        if table_text is not None:
            t_now = (frame+1) * dt
            table_text.set_text(coords_matrix_str(nodes, t_s=t_now))

        # --- cập nhật Ping (marker + highlight lines di động) ---
        ping.update_lines(nodes)
        ping.step(dt, nodes, links_dict)


        # cập nhật “ma trận tọa độ”
        artists = scatters + labels + trail_lines + link_lines
        if table_text is not None:
            artists.append(table_text)
        # giữ ref marker + các highlight của ping
        artists.append(ping.marker)
        artists.extend(ping.hl_lines)
        return artists


    ani = animation.FuncAnimation(fig, animate, init_func=init,
                                  frames=steps, interval=40, blit=False)

    if save_gif:
        ani.save(save_path_gif, writer=animation.PillowWriter(fps=20))
    else:
        plt.show()


if __name__ == "__main__":
    SAVE_CSV = True   
    SAVE_GIF = False  # False -> xem realtime; True -> xuất GIF
    run(save_csv=SAVE_CSV, save_gif=SAVE_GIF)
