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
last_dist_tbl = {}     # Dict[int, Dict[str, int]]  (per-src table)
last_directory = {}    # Dict[int, Dict[str, Any]]
last_fallback = {}     # Dict[int, Optional[int]]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("controller")


async def handle_node(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Handshake: node gửi {"hello": {"node_id": <int|0>, "kind": "...", "port": 7300, "lat":0,"lon":0,"alt_km":0}}
    Controller sẽ cấp node_id nếu thiếu/trùng, và trả ack: {"ok": true, "assigned_id": nid}
    """
    peer = writer.get_extra_info('peername')  # (ip, port)
    peer_ip = peer[0] if peer else None

    # Nhận hello
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

    host_name = str(info.get("host_name") or "")
    nodes[nid] = NodeInfo(
        node_id=nid,
        kind=kind,
        lat=float(info.get("lat", 0.0)),
        lon=float(info.get("lon", 0.0)),
        alt_km=float(info.get("alt_km", 0.0)),
        host=host_name or peer_ip,           # IP thật của TCP peer
        port=port
    )
    writer_by_node[nid] = writer
    log.info("node %d connected (%s:%d)", nid, nodes[nid].host, nodes[nid].port)

    # Gửi ack kèm assigned_id
    writer.write((json.dumps({"ok": True, "assigned_id": nid}) + "\n").encode())
    await writer.drain()

    # Lắng nghe cập nhật tọa độ từ node (optional)
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
        # cleanup khi node ngắt
        writer_by_node.pop(nid, None)
        # (tuỳ nhu cầu: có thể giữ nodes[nid] để route tạm thời, hoặc xoá hẳn)
        nodes.pop(nid, None)
        log.info("node %d disconnected", nid)


async def data_ingress_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Nhận gói từ 'server' -> {"send": {"src": 1, "dst": 5, "payload":"..."}}
    Bơm vào node src qua TCP nội bộ của node đó.
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

        tbl = last_dist_tbl.get(n, {})      # dst(str) -> next_id
        routable = sorted([int(k) for k in tbl.keys()])  # các đích có route từ n
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
        return


    s = req.get("send", {})
    try:
        src = int(s.get("src")); dst = int(s.get("dst"))
    except Exception:
        writer.write((json.dumps({"ok": False, "reason": "bad_request"})+"\n").encode())
        await writer.drain(); writer.close(); return
    payload = s.get("payload", "")

    # chỉ bơm nếu controller có route s->d trong 'nexthop' raw
    mine = next((nh for (s2,d2), nh in nexthop.items() if s2 == src and d2 == dst), None)
    if mine is None:
        writer.write((json.dumps({"ok": False, "reason":"no_route"})+"\n").encode())
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

            # 2) Xây đồ thị & chạy ACO -> nexthop
            adj = build_graph(nodes, MAX_LINK_KM)
            def comp_sizes(adj):
                seen=set(); sizes=[]
                for u in adj:
                    if u in seen: continue
                    stack=[u]; cnt=0; seen.add(u)
                    while stack:
                        x=stack.pop(); cnt+=1
                        for y in adj[x]:
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

            # 3) Phát tán nexthop + directory tới mọi node
            # dist_tbl chỉ chứa đích còn online
            dist_tbl = {}
            for (s, d), nh in nexthop.items():
                if nh in live_ids and d in live_ids and s in live_ids:
                    dist_tbl.setdefault(s, {})[str(d)] = nh

            live_ids = set(writer_by_node.keys())
            directory = {nid: {"host": nodes[nid].host, "port": nodes[nid].port, "kind": nodes[nid].kind}
                          for nid in live_ids}

            fallback_next = {}
            sats = [nid for nid,n in nodes.items() if n.kind == "sat"]
            for s in nodes.keys():
                best = None; best_d = 1e18
                a = nodes[s]
                for sid in sats:
                    if sid == s: continue
                    b = nodes[sid]
                    # dùng haversine và (nếu có) kiểm tra LOS
                    dkm = haversine_km(a.lat, a.lon, b.lat, b.lon)
                     # if not los_possible(a, b): continue   # nếu bạn có check LOS
                    if dkm < best_d:
                        best_d = dkm; best = sid
                fallback_next[s] = best

            payload = {"nexthop": dist_tbl, "directory": directory, "fallback": fallback_next}

            # LƯU lại để phục vụ dump
            global last_dist_tbl, last_directory, last_fallback
            last_dist_tbl = dist_tbl
            last_directory = directory
            last_fallback = fallback_next

            #phát tán như hiện tại
            msg = (json.dumps(payload) + "\n").encode()
            for nid, w in list(writer_by_node.items()):
                try:
                    w.write(msg)
                    await w.drain()
                except Exception:
                    pass

            # đã log ở trên nên không cần nữa
            # edges = sum(len(v) for v in adj.values()) // 2
            # log.info("tick: nodes=%d edges=%d", len(nodes), edges)
            await asyncio.sleep(UPDATE_INTERVAL)

        except Exception as e:
            log.exception("periodic_update error: %s", e)
            await asyncio.sleep(1)


async def main():
    # Mở cả 2 server trước, rồi mới log "servers up"
    srv1 = await asyncio.start_server(handle_node, HOST, CTRL_PORT)
    srv2 = await asyncio.start_server(data_ingress_server, HOST, DATA_INGRESS)
    log.info("control servers up: ctrl=%d, ingress=%d", CTRL_PORT, DATA_INGRESS)

    asyncio.create_task(periodic_update())
    async with srv1, srv2:
        await asyncio.gather(srv1.serve_forever(), srv2.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
