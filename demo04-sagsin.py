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
    dn = great_circle_xyz(16.0544, 108.2022, 0.0)
    hn = great_circle_xyz(21.0278, 105.8342, 0.0)
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
        nonlocal link_lines
        for ln in link_lines: 
            ln.remove()
        link_lines = []
        for i, j, d in compute_links(nodes):
            p = nodes[i].pos; q = nodes[j].pos
            ln, = ax.plot([p[0], q[0]], [p[1], q[1]], [p[2], q[2]], linewidth=0.8)
            link_lines.append(ln)

        # cập nhật “ma trận tọa độ”
        if table_text is not None:
            t_now = (frame+1) * dt
            table_text.set_text(coords_matrix_str(nodes, t_s=t_now))

        artists = scatters + labels + trail_lines + link_lines
        if table_text is not None:
            artists.append(table_text)
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
