import asyncio, os, json
from typing import Dict
import logging, sys

from models import NodeInfo
from datasources import DataSource
from aco import aco_next_hop, build_graph
from geo import haversine_km

HOST = "0.0.0.0"
CTRL_PORT = 7100        # kênh control (node kết nối vào)
DATA_INGRESS = 7200     # server nhận gói để bơm vào mạng
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL_SEC", "10"))
MAX_LINK_KM = float(os.getenv("MAX_LINK_KM", "3000"))

nodes: Dict[int, NodeInfo] = {}
writer_by_node: Dict[int, asyncio.StreamWriter] = {}
nexthop: Dict = {}

# Lưu cho tools/dump_routes.py
last_dist_tbl: Dict[int, Dict[str, int]] = {}
last_directory: Dict[int, dict] = {}
last_fallback: Dict[int, int | None] = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("controller")


async def handle_node(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Handshake: node gửi {"hello": {"node_id": <int|0>, "kind": "...", "port": 7300,
                                   "lat":0,"lon":0,"alt_km":0, "host_name": "<hostname>" }}
    Controller cấp node_id nếu thiếu/trùng và trả {"ok": true, "assigned_id": nid}
    """
    peer = writer.get_extra_info('peername')  # (ip, port)
    peer_ip = peer[0] if peer else None

    line = await reader.readline()
    if not line:
        writer.close()
        return
    hello = json.loads(line.decode().strip())
    info = hello.get("hello", {})

    # Cấp phát / hợp lệ hóa node_id
    try:
        wanted = int(info.get("node_id") or 0)
    except Exception:
        wanted = 0
    if wanted <= 0 or wanted in nodes:
        used = set(nodes.keys())
        nid = 1
        while nid in used:
            nid += 1
    else:
        nid = wanted

    # Lưu thông tin node
    try:
        port = int(info.get("port", 7300))
    except Exception:
        port = 7300
    kind = str(info.get("kind", "sat"))

    # Ưu tiên hostname do node gửi; thiếu thì dùng IP peer
    host_name = str(info.get("host_name") or "").strip()
    host_value = host_name if host_name else peer_ip

    nodes[nid] = NodeInfo(
        node_id=nid,
        kind=kind,
        lat=float(info.get("lat", 0.0)),
        lon=float(info.get("lon", 0.0)),
        alt_km=float(info.get("alt_km", 0.0)),
        host=host_value,
        port=port
    )
    writer_by_node[nid] = writer
    log.info("node %d connected (%s:%d)", nid, nodes[nid].host, nodes[nid].port)

    # Gửi ack kèm assigned_id
    writer.write((json.dumps({"ok": True, "assigned_id": nid}) + "\n").encode())
    await writer.drain()

    # Lắng nghe cập nhật toạ độ từ node (optional)
    try:
        while not reader.at_eof():
            line = await reader.readline()
            if not line:
                break
            msg = json.loads(line.decode().strip())
            if "coord" in msg:
                c = msg["coord"]
                n = nodes.get(nid)
                if n:
                    n.lat = float(c.get("lat", n.lat))
                    n.lon = float(c.get("lon", n.lon))
                    n.alt_km = float(c.get("alt_km", n.alt_km))
    finally:
        # cleanup khi node ngắt: xoá khỏi writer_by_node và nodes để tránh phát IP/hostname cũ
        writer_by_node.pop(nid, None)
        nodes.pop(nid, None)
        log.info("node %d disconnected", nid)


async def data_ingress_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Nhận:
      - Dump: {"dump": {"node": N}}
      - Gửi: {"send": {"src": 1, "dst": 5, "payload":"..."}}
    """
    line = await reader.readline()
    if not line:
        writer.close(); return
    req = json.loads(line.decode().strip())

    # === DUMP bảng định tuyến của 1 node ===
    if "dump" in req:
        try:
            n = int(req["dump"]["node"])
        except Exception:
            writer.write((json.dumps({"ok": False, "reason": "bad_request"})+"\n").encode())
            await writer.drain(); writer.close(); return

        tbl = last_dist_tbl.get(n, {})  # dst(str) -> next_id
        routable = sorted([int(k) for k in tbl.keys()])
        resp = {
            "ok": True,
            "node": n,
            "routable_dsts": routable,
            "nexthop": tbl,                 # bảng next-hop chi tiết cho node n
            "fallback": last_fallback.get(n),
            "directory_size": len(last_directory),
        }
        writer.write((json.dumps(resp) + "\n").encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        return

    # === SEND ===
    s = req.get("send", {})
    try:
        src = int(s.get("src")); dst = int(s.get("dst"))
    except Exception:
        writer.write((json.dumps({"ok": False, "reason": "bad_request"})+"\n").encode())
        await writer.drain(); writer.close(); return
    payload = s.get("payload", "")

    # chỉ bơm nếu controller có route s->d trong 'nexthop' raw
    mine = next((nh for (s2, d2), nh in nexthop.items() if s2 == src and d2 == dst), None)
    if mine is None:
        writer.write((json.dumps({"ok": False, "reason": "no_route"})+"\n").encode())
        await writer.drain(); writer.close(); return

    ok = await inject_to_node(src, {"forward": {"dst": dst, "payload": payload}})
    writer.write((json.dumps({"ok": ok})+"\n").encode())
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def inject_to_node(nid: int, obj: dict) -> bool:
    n = nodes.get(nid)
    if not n or not n.host:
        return False
    try:
        reader, writer = await asyncio.open_connection(n.host, n.port)
        writer.write((json.dumps(obj) + "\n").encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        return True
    except Exception as e:
        log.error("inject_to_node %s failed: %s", nid, e)
        return False


async def periodic_update():
    ds = DataSource()

    # Chờ ít nhất 1 node handshake xong
    while not nodes:
        await asyncio.sleep(0.5)

    # Khởi tạo toạ độ lần đầu
    await ds.populate_initial(nodes)

    while True:
        try:
            # 1) Cập nhật toạ độ (mô phỏng + dữ liệu thật nếu có)
            await ds.tick_update(nodes)
            await ds.update_from_celestrak(nodes)
            await ds.update_from_satnogs(nodes)
            await ds.update_from_ndbc(nodes)
            await ds.update_from_opensky(nodes)

            # 2) Xây đồ thị & chạy ACO -> nexthop (không dùng neighbors trong dump nữa)
            adj = build_graph(nodes, MAX_LINK_KM)
            def comp_sizes(adj_: Dict[int, Dict[int, float]]):
                seen=set(); sizes=[]
                for u in adj_:
                    if u in seen: continue
                    stack=[u]; cnt=0; seen.add(u)
                    while stack:
                        x=stack.pop(); cnt+=1
                        for y in adj_[x]:
                            if y not in seen:
                                seen.add(y); stack.append(y)
                    sizes.append(cnt)
                return sorted(sizes, reverse=True)

            sizes = comp_sizes(adj)
            edges = sum(len(v) for v in adj.values()) // 2
            log.info("tick: nodes=%d edges=%d comps=%d max_comp=%d",
                      len(nodes), edges, len(sizes), sizes[0] if sizes else 0)

            global nexthop
            nexthop = aco_next_hop(nodes, MAX_LINK_KM, iters=8, ants=30)

            # 3) Phát tán nexthop + directory tới mọi node (CHỈ node online)
            live_ids = set(writer_by_node.keys())  # <-- gán TRƯỚC khi dùng

            # dist_tbl: chỉ giữ route mà src/dst/next đều online
            dist_tbl: Dict[int, Dict[str, int]] = {}
            for (s, d), nh in nexthop.items():
                if s in live_ids and d in live_ids and nh in live_ids:
                    dist_tbl.setdefault(s, {})[str(d)] = nh

            # directory: chỉ online
            directory = {
                nid: {"host": nodes[nid].host, "port": nodes[nid].port, "kind": nodes[nid].kind}
                for nid in live_ids
            }

            # Fallback: chọn 1 vệ tinh online gần nhất cho mỗi src online
            fallback_next: Dict[int, int | None] = {}
            sats = [nid for nid in live_ids if nodes[nid].kind == "sat"]
            for s in live_ids:
                best = None; best_d = 1e18
                a = nodes[s]
                for sid in sats:
                    if sid == s: continue
                    b = nodes[sid]
                    dkm = haversine_km(a.lat, a.lon, b.lat, b.lon)
                    if dkm < best_d:
                        best_d = dkm; best = sid
                fallback_next[s] = best

            payload = {"nexthop": dist_tbl, "directory": directory, "fallback": fallback_next}

            # LƯU lại để phục vụ dump
            global last_dist_tbl, last_directory, last_fallback
            last_dist_tbl = dist_tbl
            last_directory = directory
            last_fallback = fallback_next

            # broadcast
            msg = (json.dumps(payload) + "\n").encode()
            for nid, w in list(writer_by_node.items()):
                try:
                    w.write(msg)
                    await w.drain()
                except Exception:
                    pass

            await asyncio.sleep(UPDATE_INTERVAL)

        except Exception as e:
            log.exception("periodic_update error: %s", e)
            await asyncio.sleep(1)


async def main():
    srv1 = await asyncio.start_server(handle_node, HOST, CTRL_PORT)
    srv2 = await asyncio.start_server(data_ingress_server, HOST, DATA_INGRESS)
    log.info("control servers up: ctrl=%d, ingress=%d", CTRL_PORT, DATA_INGRESS)

    asyncio.create_task(periodic_update())
    async with srv1, srv2:
        await asyncio.gather(srv1.serve_forever(), srv2.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
