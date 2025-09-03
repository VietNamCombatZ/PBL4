# SAGSIN animation (final): Satellites + UAVs + Ground/Sea
# - Realtime animation (no GIF required) or optional GIF export via SAVE_GIF
import numpy as np
import math
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.lines import Line2D

# ---------- Geometry helpers ----------
RE = 6371.0  # Earth radius (km)

def norm(v):
    return np.sqrt(np.dot(v, v))

def unit(v):
    n = norm(v)
    return v / n if n > 0 else v

def rotate_vector(v, axis, angle_rad):
    k = unit(axis)
    v = np.array(v, dtype=float)
    return (v*np.cos(angle_rad) +
            np.cross(k, v)*np.sin(angle_rad) +
            k*np.dot(k, v)*(1 - np.cos(angle_rad)))

def great_circle_xyz(lat_deg, lon_deg, h_km=0.0):
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)
    r = RE + h_km
    x = r * np.cos(lat) * np.cos(lon)
    y = r * np.cos(lat) * np.sin(lon)
    z = r * np.sin(lat)
    return np.array([x, y, z], dtype=float)

# ---------- Node classes ----------
class Node:
    def __init__(self, name, kind, pos):
        self.name = name
        self.kind = kind  # "sat", "uav", "ground", "sea"
        self.pos = np.array(pos, dtype=float)
    def step(self, dt):
        pass

class Satellite(Node):
    def __init__(self, name, altitude_km, n_hat, pos0=None, omega_rad_s=None):
        super().__init__(name, "sat", pos0 if pos0 is not None else [RE+altitude_km, 0, 0])
        self.altitude_km = altitude_km
        self.radius = RE + altitude_km
        self.n_hat = unit(np.asarray(n_hat, dtype=float))
        if omega_rad_s is None:
            T = 5400.0  # ~90 minutes LEO (đơn giản)
            omega_rad_s = 2*np.pi / T
        self.omega = omega_rad_s
        if norm(self.pos) == 0:
            self.pos = np.array([self.radius, 0, 0], dtype=float)
    def step(self, dt):
        r = unit(self.pos) * self.radius
        self.pos = rotate_vector(r, self.n_hat, self.omega * dt)

class UAV(Node):
    def __init__(self, name, pos0, waypoints, speed_km_s=0.15, wp_tolerance_km=1.0):
        super().__init__(name, "uav", pos0)
        self.waypoints = [np.array(w, dtype=float) for w in waypoints]
        self.speed = speed_km_s
        self.tol = wp_tolerance_km
        self.idx = 0
    def step(self, dt):
        if not self.waypoints:
            return
        target = self.waypoints[self.idx]
        dvec = target - self.pos
        d = norm(dvec)
        if d < self.tol:
            self.idx = (self.idx + 1) % len(self.waypoints)
            return
        step_len = min(d, self.speed * dt)
        if d > 0:
            self.pos = self.pos + (dvec / d) * step_len

class StaticNode(Node):
    def __init__(self, name, kind, pos0, drift_km_s=0.0, drift_dir=None):
        super().__init__(name, kind, pos0)
        self.drift = drift_km_s
        self.drift_dir = None if drift_dir is None else unit(np.array(drift_dir, dtype=float))
    def step(self, dt):
        if self.drift > 0 and self.drift_dir is not None:
            self.pos = self.pos + self.drift_dir * self.drift * dt
            # ép nằm đúng bề mặt (bán kính RE)
            r = norm(self.pos)
            if r != 0:
                self.pos = (self.pos / r) * RE

# ---------- Build scenario ----------
def build_nodes():
    nodes = []
    # Ground stations
    dn = great_circle_xyz(16.0544, 108.2022, 0.0)
    hn = great_circle_xyz(21.0278, 105.8342, 0.0)
    nodes.append(StaticNode("Danang-GS", "ground", dn))
    nodes.append(StaticNode("Hanoi-GS",  "ground", hn))

    # Sea ship (trôi nhẹ về phía đông)
    ship = StaticNode("Ship-1", "sea", great_circle_xyz(14.0, 111.0, 0.0),
                      drift_km_s=0.02, drift_dir=[1, 0, 0])
    nodes.append(ship)

    # UAVs quanh Đà Nẵng (cao ~5km)
    wp = [
        great_circle_xyz(16.00, 108.10, 5.0),
        great_circle_xyz(16.10, 108.20, 5.0),
        great_circle_xyz(16.00, 108.30, 5.0),
        great_circle_xyz(15.90, 108.20, 5.0),
    ]
    nodes.append(UAV("UAV-Alpha", wp[0], wp, speed_km_s=0.14))
    nodes.append(UAV("UAV-Bravo", wp[2], list(reversed(wp)), speed_km_s=0.12))

    # Satellites
    nodes.extend([
        Satellite("Sat-A", 550,  [0.2, 1.0, 0.1], pos0=[RE+550, 0, 0]),
        Satellite("Sat-B", 500,  [1.0, 0.2, 0.3], pos0=[0, RE+500, 0]),
        Satellite("Sat-C", 600,  [-0.3, 0.8, 0.5], pos0=[0, 0, RE+600]),
        Satellite("Sat-D", 1200, [0.0, 0.0, 1.0], pos0=[RE+1200, 0, 0]),
    ])
    return nodes

# ---------- Main (simulation + animation) ----------
def run(save_csv=True, save_path_csv="sagsin_all_nodes_coordinates.csv",
        save_gif=False, save_path_gif="sagsin_full_animation.gif",
        steps=160, dt=2.0):
    # 1) Thu thập toạ độ theo thời gian (dễ debug/ghi log)
    nodes = build_nodes()
    records = []
    for k in range(steps):
        t = k * dt
        for n in nodes:
            records.append((t, n.name, n.kind, n.pos[0], n.pos[1], n.pos[2]))
        for n in nodes:
            n.step(dt)
    df = pd.DataFrame(records, columns=["t_s", "name", "kind", "x_km", "y_km", "z_km"])
    if save_csv:
        df.to_csv(save_path_csv, index=False)

    # 2) Animation realtime (hoặc xuất GIF)
    nodes = build_nodes()  # reset để animation bắt đầu từ t=0

    # Quả cầu Trái Đất (wireframe)
    u = np.linspace(0, 2*np.pi, 40)
    v = np.linspace(-np.pi/2, np.pi/2, 20)
    xs = RE*np.outer(np.cos(v), np.cos(u))
    ys = RE*np.outer(np.cos(v), np.sin(u))
    zs = RE*np.outer(np.sin(v), np.ones_like(u))

    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    ax.plot_wireframe(xs, ys, zs, linewidth=0.5)

    # Giới hạn & góc nhìn
    lim = 9000
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)
    ax.view_init(elev=22, azim=35)

    # Vẽ các node ban đầu
    marker_by_kind = {"sat": "x", "uav": "o", "ground": "^", "sea": "s"}
    artists = []
    labels = []
    for n in nodes:
        sc = ax.scatter([n.pos[0]], [n.pos[1]], [n.pos[2]],
                        marker=marker_by_kind.get(n.kind, "o"))
        txt = ax.text(n.pos[0], n.pos[1], n.pos[2], n.name)
        artists.append(sc)
        labels.append(txt)

    # Legend (không set màu cụ thể)
    legend_elems = [
        Line2D([0],[0], marker='x', linestyle='None', label='Satellite'),
        Line2D([0],[0], marker='o', linestyle='None', label='UAV'),
        Line2D([0],[0], marker='^', linestyle='None', label='Ground'),
        Line2D([0],[0], marker='s', linestyle='None', label='Sea'),
    ]
    ax.legend(handles=legend_elems, loc='upper left')

    ax.set_box_aspect([1, 1, 1])
    ax.set_xlabel("X (km)")
    ax.set_ylabel("Y (km)")
    ax.set_zlabel("Z (km)")
    ax.set_title("SAGSIN: Satellites + UAVs + Ground/Sea (demo)")
    fig.tight_layout()

    def init():
        return artists + labels

    def animate(frame):
        # cập nhật trạng thái
        for n in nodes:
            n.step(dt)
        # cập nhật scatter/label mà không remove()
        for i, n in enumerate(nodes):
            x, y, z = n.pos
            # cập nhật 3D offsets cho scatter
            artists[i]._offsets3d = (np.array([x]), np.array([y]), np.array([z]))
            # cập nhật label
            labels[i].set_position((x, y))
            try:
                labels[i].set_3d_properties(z, zdir='z')
            except Exception:
                pass
        return artists + labels

    ani = animation.FuncAnimation(fig, animate, init_func=init,
                                  frames=steps, interval=50, blit=False)

    if save_gif:
        ani.save(save_path_gif, writer=animation.PillowWriter(fps=20))
    else:
        plt.show()

if __name__ == "__main__":
    # tuỳ chọn: bật/tắt lưu file
    SAVE_CSV = True
    SAVE_GIF = False  # False => xem realtime; True => xuất GIF
    run(save_csv=SAVE_CSV, save_gif=SAVE_GIF)
