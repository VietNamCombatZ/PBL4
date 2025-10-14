import asyncio, os, json, random, sys, logging

CTRL_HOST = os.getenv("CONTROLLER_HOST", "controller")
CTRL_PORT = int(os.getenv("CONTROLLER_PORT", "7100"))
DATA_PORT = int(os.getenv("NODE_PORT", "7300"))

# Nếu không set NODE_ID, để 0 cho controller cấp ID
node_id_env = os.getenv("NODE_ID")
try:
    node_id = int(node_id_env) if node_id_env else 0
except Exception:
    node_id = 0

# Chọn loại node nếu không set: sat / plane / ground
node_kind = os.getenv("NODE_KIND") or (
    "sat" if random.random() < 1/3 else ("plane" if random.random() < 0.5 else "ground")
)

# Bảng directory do controller phát: id -> {"host": str, "port": int}
directory = {}

# Bảng next-hop cho node hiện tại: dst(int) -> next_id(int)
nexthop_for_me = {}

# Fallback relay (id vệ tinh gần nhất) do controller phát cho riêng node này
fallback_for_me = None

# ---- Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [node] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("node")


async def controller_loop():
    """Kết nối controller, handshake, nhận bảng nexthop/directory/fallback, tự reconnect nếu rớt."""
    global node_id, nexthop_for_me, directory, fallback_for_me

    while True:
        try:
            log.info("connecting to controller %s:%d ...", CTRL_HOST, CTRL_PORT)
            reader, writer = await asyncio.open_connection(CTRL_HOST, CTRL_PORT)
            log.info("connected to controller")

            # Handshake
            hello = {
                "hello": {
                    "node_id": node_id,
                    "kind": node_kind,
                    "lat": 0.0, "lon": 0.0, "alt_km": 0.0,
                    "port": DATA_PORT
                }
            }
            writer.write((json.dumps(hello) + "\n").encode())
            await writer.drain()

            # Nhận ack + assigned_id
            line = await reader.readline()
            if not line:
                log.warning("controller closed before ack; retrying...")
                writer.close()
                await writer.wait_closed()
                await asyncio.sleep(1)
                continue

            try:
                ack = json.loads(line.decode().strip())
            except Exception as e:
                log.error("bad ack json: %s", e)
                writer.close()
                await writer.wait_closed()
                await asyncio.sleep(1)
                continue

            assigned = int(ack.get("assigned_id") or 0)
            if assigned > 0 and assigned != node_id:
                log.info("assigned node_id=%d (was %d)", assigned, node_id)
                node_id = assigned

            # Vòng đọc cập nhật từ controller
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode().strip())
                except Exception:
                    continue

                if "nexthop" in msg:
                    table = msg["nexthop"]
                    mine = table.get(str(node_id)) or table.get(node_id) or {}
                    try:
                        nexthop_for_me = {int(k): int(v) for k, v in mine.items()}
                    except Exception:
                        nexthop_for_me = {}

                    if "directory" in msg:
                        try:
                            directory = {
                                int(k): {"host": v["host"], "port": int(v["port"])}
                                for k, v in msg["directory"].items()
                            }
                        except Exception:
                            pass

                    if "fallback" in msg:
                        try:
                            f = msg["fallback"].get(str(node_id)) or msg["fallback"].get(node_id)
                            fallback_for_me = int(f) if f is not None else None
                        except Exception:
                            fallback_for_me = None

            # Controller đóng kết nối -> reconnect
            log.warning("controller connection closed; reconnecting...")
            writer.close()
            await writer.wait_closed()
            await asyncio.sleep(1)

        except Exception as e:
            log.warning("controller connect error: %s; retrying...", e)
            await asyncio.sleep(1)


async def data_server():
    """TCP server nhận gói forward từ node khác hoặc từ controller.inject_to_node()."""
    async def handle(rcv_reader: asyncio.StreamReader, rcv_writer: asyncio.StreamWriter):
        try:
            line = await rcv_reader.readline()
            if not line:
                return
            try:
                msg = json.loads(line.decode().strip())
            except Exception:
                return

            if "forward" in msg:
                dst = int(msg["forward"]["dst"])
                payload = msg["forward"]["payload"]
                await forward_or_deliver(dst, payload)
        finally:
            try:
                rcv_writer.close()
                await rcv_writer.wait_closed()
            except Exception:
                pass

    srv = await asyncio.start_server(handle, "0.0.0.0", DATA_PORT)
    log.info("data server up on 0.0.0.0:%d", DATA_PORT)
    async with srv:
        await srv.serve_forever()


async def forward_or_deliver(dst: int, payload: str):
    """Nếu là đích thì deliver; nếu không, forward theo nexthop_for_me/directory với fallback."""
    if dst == node_id:
        print(f"[node {node_id}] DELIVERED: {payload}", flush=True)
        return

    # 1) next-hop trực tiếp nếu có
    next_id = nexthop_for_me.get(dst)

    # 2) fallback do controller chỉ định (vệ tinh gần nhất) nếu không có route trực tiếp
    if next_id is None and fallback_for_me and fallback_for_me in directory:
        next_id = fallback_for_me

    # 3) fallback mềm: chọn bất kỳ next-hop đã biết (từ bảng nexthop_for_me) mà có trong directory
    if next_id is None:
        candidates = [nh for nh in set(nexthop_for_me.values()) if nh in directory]
        if candidates:
            # xấp xỉ "gần đích" bằng khoảng cách theo id
            next_id = min(candidates, key=lambda k: abs(k - dst))

    # 4) nếu vẫn không có, đành bỏ
    if next_id is None:
        print(f"[node {node_id}] DROP (no nexthop): {payload}", flush=True)
        return

    info = directory.get(next_id)
    if not info:
        print(f"[node {node_id}] DROP (no directory for {next_id})", flush=True)
        return

    next_host = info["host"]
    next_port = int(info.get("port", DATA_PORT))
    try:
        reader, writer = await asyncio.open_connection(next_host, next_port)
        writer.write((json.dumps({"forward": {"dst": dst, "payload": payload}}) + "\n").encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except Exception as e:
        print(f"[node {node_id}] FORWARD ERR to {next_id}@{next_host}:{next_port}: {e}", flush=True)


async def main():
    # Chạy song song: 1) giữ kết nối controller (reconnect), 2) lắng nghe data
    await asyncio.gather(controller_loop(), data_server())


if __name__ == "__main__":
    asyncio.run(main())
