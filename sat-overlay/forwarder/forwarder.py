import asyncio, json, base64, os

# Cổng UDP vệ tinh lắng nghe
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("SAT_PORT", "9000"))

# Gói overlay JSON:
# {
#   "dst": "IP_or_host:port",                 # đích cuối (nếu path rỗng thì gửi payload tới đây)
#   "path": ["hop1_ip:port","hop2_ip:port"],  # danh sách các hop còn lại; 1 vệ tinh => path rỗng khi đã tới
#   "payload_b64": "<base64-bytes>"           # dữ liệu của ứng dụng
# }

class UdpForwarder(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport
        print(f"[sat] listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)

    def datagram_received(self, data, addr):
        try:
            pkt = json.loads(data.decode("utf-8"))
            path = pkt.get("path", [])
            if path:
                # Còn hop ở phía trước → chuyển tiếp gói overlay đến hop kế tiếp
                next_hop = path.pop(0)
                pkt["path"] = path
                self._send_json(pkt, next_hop)
            else:
                # Đã tới hop cuối → giải nén và gửi payload tới đích ứng dụng
                dst = pkt["dst"]
                payload = base64.b64decode(pkt["payload_b64"])
                ip, port = dst.split(":")
                self.transport.sendto(payload, (ip, int(port)))
        except Exception as e:
            print("[sat] ERR:", e, flush=True)

    def _send_json(self, pkt, next_hop):
        ip, port = next_hop.split(":")
        self.transport.sendto(json.dumps(pkt).encode("utf-8"), (ip, int(port)))

async def main():
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UdpForwarder(), local_addr=(LISTEN_HOST, LISTEN_PORT)
    )
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        transport.close()

if __name__ == "__main__":
    asyncio.run(main())
