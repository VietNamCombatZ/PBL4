import argparse, asyncio, json, base64, socket

# Gửi 1 thông điệp UDP qua overlay:
#   - path: danh sách hop (ở PoC 1 vệ tinh: chính là [ "<SAT_HOST>:<SAT_PORT>" ])
#   - dst: "IP:port" của app đích (máy B)
#   - message: nội dung text (sẽ được base64)

parser = argparse.ArgumentParser()
parser.add_argument("--first-hop", required=True, help="ví dụ: 203.0.113.10:9000 (IP máy chạy vệ tinh, port xuất bản)")
parser.add_argument("--dst", required=True, help='ví dụ: "198.51.100.20:7000" (đích cuối trên máy B)')
parser.add_argument("--message", default="Hello via satellite!", help="nội dung gửi")
args = parser.parse_args()

async def send_once():
    first_ip, first_port = args.first_hop.split(":")
    payload_b64 = base64.b64encode(args.message.encode("utf-8")).decode("ascii")

    pkt = {
        "dst": args.dst,
        "path": [],  # 1 vệ tinh: path rỗng trong gói gửi vào first-hop (forwarder chỉ giải nén khi path trống)
        "payload_b64": payload_b64
    }

    # Vì first-hop chính là vệ tinh duy nhất, ta gửi trực tiếp gói overlay tới nó.
    # Nếu sau này nhiều vệ tinh: đặt path = ["hop2","hop3",...]; first-hop chỉ là điểm ta gửi gói đầu tiên tới.
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: asyncio.DatagramProtocol(), remote_addr=(first_ip, int(first_port))
    )
    transport.sendto(json.dumps(pkt).encode("utf-8"))
    await asyncio.sleep(0.1)
    transport.close()

if __name__ == "__main__":
    asyncio.run(send_once())
