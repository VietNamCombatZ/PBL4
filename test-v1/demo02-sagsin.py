import math
import numpy as np
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# ====== HẰNG SỐ ======
RE = 6371.0  # bán kính Trái Đất (km)

# ====== TIỆN ÍCH HÌNH HỌC ======
def norm(v):
    return math.sqrt(np.dot(v, v))

def unit(v):
    n = norm(v)
    return v / n if n > 0 else v

def rotate_vector(v, axis, angle_rad):
    # Rodrigues rotation: quay vector v quanh trục axis góc angle_rad
    k = unit(axis)
    v = np.array(v, dtype=float)
    return (v*math.cos(angle_rad) +
            np.cross(k, v)*math.sin(angle_rad) +
            k*np.dot(k, v)*(1 - math.cos(angle_rad)))

def great_circle_xyz(lat_deg, lon_deg, h_km=0.0):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    r = RE + h_km
    x = r * math.cos(lat) * math.cos(lon)
    y = r * math.cos(lat) * math.sin(lon)
    z = r * math.sin(lat)
    return np.array([x, y, z], dtype=float)

def segment_intersects_earth(p1, p2, R=RE):
    """
    Kiểm tra đoạn thẳng nối p1-p2 có cắt qua quả cầu bán kính R (Trái Đất) không.
    Nếu CẮT (bị che), return True => KHÔNG đường nhìn. 
    Nếu KHÔNG cắt (LOS OK), return False.
    """
    p1 = np.array(p1); p2 = np.array(p2)
    d = p2 - p1
    a = np.dot(d, d)
    b = 2 * np.dot(p1, d)
    c = np.dot(p1, p1) - R*R
    # nghiệm gần nhất t* của khoảng cách tới tâm
    if a == 0:
        # p1==p2
        return np.dot(p1, p1) < R*R  # nằm trong Trái Đất?
    t = -b / (2*a)
    t_clamp = max(0.0, min(1.0, t))
    closest = p1 + t_clamp * d
    return np.dot(closest, closest) < R*R

def has_los(p1, p2):
    return not segment_intersects_earth(p1, p2, RE)

# ====== LỚP CƠ SỞ ======
@dataclass
class Node:
    name: str
    kind: str  # "sat", "uav", "ground", "sea"
    range_km: float  # tầm phủ liên kết
    pos: np.ndarray  # (x,y,z) km

    def update(self, dt: float):
        pass

# ====== VỆ TINH: quỹ đạo tròn đơn giản ======
@dataclass
class Satellite(Node):
    # Quỹ đạo tròn bán kính (RE + altitude)
    # pos0: vị trí ban đầu trên quỹ đạo; n_hat: pháp tuyến mặt phẳng quỹ đạo (độ nghiêng)
    altitude_km: float = 500.0
    omega_rad_s: float = field(default=0.0)  # tốc độ góc (rad/s)
    n_hat: np.ndarray = field(default_factory=lambda: np.array([0,0,1], dtype=float))
    _angle: float = 0.0
    _radius: float = field(init=False)

    def __post_init__(self):
        self._radius = RE + self.altitude_km
        if self.omega_rad_s == 0.0:
            # Tính omega từ chu kỳ quỹ đạo tròn xấp xỉ (phớt lờ GM): lấy LEO ~ 90 phút
            T = 5400.0  # 90 phút
            self.omega_rad_s = 2*math.pi / T
        # Bảo đảm n_hat là đơn vị
        self.n_hat = unit(self.n_hat)
        # Đặt pos vào vòng tròn ban đầu trong mặt phẳng quỹ đạo
        if norm(self.pos) == 0:
            self.pos = np.array([self._radius, 0.0, 0.0])

    def update(self, dt: float):
        # Quay pos quanh trục n_hat với góc omega*dt
        self._angle += self.omega_rad_s * dt
        # Giữ độ dài pos luôn = radius, và quay quanh n_hat
        # Trước khi quay, đảm bảo pos nằm trên mặt phẳng vuông góc n_hat (áp lực đơn giản)
        r = unit(self.pos) * self._radius
        self.pos = rotate_vector(r, self.n_hat, self.omega_rad_s * dt)

# ====== UAV: bay theo waypoint ======
@dataclass
class UAV(Node):
    speed_km_s: float = 0.2  # ~720 km/h
    waypoints: List[np.ndarray] = field(default_factory=list)
    wp_tolerance_km: float = 1.0
    _idx: int = 0

    def update(self, dt: float):
        if not self.waypoints:
            return
        target = self.waypoints[self._idx]
        dvec = target - self.pos
        d = norm(dvec)
        if d < self.wp_tolerance_km:
            self._idx = (self._idx + 1) % len(self.waypoints)
            return
        step = min(d, self.speed_km_s * dt)
        self.pos = self.pos + unit(dvec) * step

# ====== GROUND / SEA ======
@dataclass
class StaticNode(Node):
    drift_km_s: float = 0.0
    drift_dir: Optional[np.ndarray] = None
    def update(self, dt: float):
        if self.drift_km_s > 0 and self.drift_dir is not None:
            self.pos = self.pos + unit(self.drift_dir) * self.drift_km_s * dt
            # ép nằm sát bề mặt (ground/sea)
            r = norm(self.pos)
            if r != 0:
                self.pos = (self.pos / r) * RE

# ====== MÔ PHỎNG ======
class SagsinSim:
    def __init__(self, nodes: List[Node], dt: float = 1.0):
        self.nodes = nodes
        self.dt = dt
        self.time = 0.0
        self.links = []  # list of (i,j)

    def step(self):
        for n in self.nodes:
            n.update(self.dt)
        self.time += self.dt
        self.links = self.compute_links()

    def compute_links(self):
        links = []
        N = len(self.nodes)
        for i in range(N):
            for j in range(i+1, N):
                a, b = self.nodes[i], self.nodes[j]
                d = norm(a.pos - b.pos)
                # both must be within each other's range
                if d <= min(a.range_km, b.range_km) and has_los(a.pos, b.pos):
                    links.append((i, j, d))
        return links

# ====== DEMO THIẾT LẬP HỆ THỐNG ======
def demo_build():
    nodes: List[Node] = []

    # 1) Ground stations (Đà Nẵng, Hà Nội) ~ lat/lon
    dn = great_circle_xyz(16.0544, 108.2022, 0.0)
    hn = great_circle_xyz(21.0278, 105.8342, 0.0)
    nodes.append(StaticNode(name="Danang-GS", kind="ground", range_km=1200, pos=dn))
    nodes.append(StaticNode(name="Hanoi-GS",  kind="ground", range_km=1200, pos=hn))

    # 2) Sea ship (trôi nhẹ theo hướng đông)
    ship = StaticNode(name="Ship-1", kind="sea", range_km=500, pos=great_circle_xyz(14.0, 111.0, 0.0),
                      drift_km_s=0.02, drift_dir=np.array([1.0, 0.0, 0.0]))
    nodes.append(ship)

    # 3) UAVs quanh Đà Nẵng
    wp = [
        great_circle_xyz(16.00, 108.10, 5.0),
        great_circle_xyz(16.10, 108.20, 5.0),
        great_circle_xyz(16.00, 108.30, 5.0),
        great_circle_xyz(15.90, 108.20, 5.0),
    ]
    uav1 = UAV(name="UAV-Alpha", kind="uav", range_km=150, pos=wp[0].copy(), waypoints=wp, speed_km_s=0.14)
    uav2 = UAV(name="UAV-Bravo", kind="uav", range_km=150, pos=wp[2].copy(), waypoints=list(reversed(wp)), speed_km_s=0.12)
    nodes.extend([uav1, uav2])

    # 4) Vệ tinh LEO (2 vệ tinh, mặt phẳng quỹ đạo khác nhau)
    sat1 = Satellite(name="Sat-A", kind="sat", range_km=2500,
                     pos=np.array([RE+550, 0, 0], dtype=float),
                     altitude_km=550, n_hat=unit(np.array([0.2, 1.0, 0.1])))
    sat2 = Satellite(name="Sat-B", kind="sat", range_km=2500,
                     pos=np.array([0, RE+500, 0], dtype=float),
                     altitude_km=500, n_hat=unit(np.array([1.0, 0.2, 0.3])))
    nodes.extend([sat1, sat2])

    return nodes

def main():
    nodes = demo_build()
    sim = SagsinSim(nodes, dt=2.0)  # bước 2 giây
    T = 600  # tổng 600s cho demo

    print("t(s), #links, examples")
    for _ in range(int(T / sim.dt)):
        sim.step()
        if int(sim.time) % 20 == 0:
            # in nhanh một vài liên kết
            show = ", ".join([f"{nodes[i].name}-{nodes[j].name}@{d:.0f}km" for i, j, d in sim.links[:4]])
            print(f"{int(sim.time):4d}, {len(sim.links):2d}, {show}")

    # (Tuỳ chọn) Vẽ snapshot cuối
    try:
        import matplotlib.pyplot as plt
        fig = plt.figure()
        ax = fig.add_subplot(projection='3d')
        # Vẽ quả cầu Trái Đất (wireframe)
        u = np.linspace(0, 2*np.pi, 40)
        v = np.linspace(-np.pi/2, np.pi/2, 20)
        xs = RE*np.outer(np.cos(v), np.cos(u))
        ys = RE*np.outer(np.cos(v), np.sin(u))
        zs = RE*np.outer(np.sin(v), np.ones_like(u))
        ax.plot_wireframe(xs, ys, zs, linewidth=0.5)

        # Vẽ nodes
        for n in nodes:
            ax.scatter(n.pos[0], n.pos[1], n.pos[2])
            ax.text(n.pos[0], n.pos[1], n.pos[2], n.name)

        # Vẽ links cuối
        for i, j, _d in sim.links:
            p, q = nodes[i].pos, nodes[j].pos
            ax.plot([p[0], q[0]], [p[1], q[1]], [p[2], q[2]], linewidth=0.8)

        ax.set_box_aspect([1,1,1])
        ax.set_xlabel("X (km)"); ax.set_ylabel("Y (km)"); ax.set_zlabel("Z (km)")
        ax.set_title("SAGSIN snapshot")
        plt.show()
    except Exception as e:
        print("Plot skipped:", e)

if __name__ == "__main__":
    main()
