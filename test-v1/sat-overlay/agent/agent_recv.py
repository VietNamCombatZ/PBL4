import argparse, asyncio

parser = argparse.ArgumentParser()
parser.add_argument("--listen", default="0.0.0.0:7000", help="VD: 0.0.0.0:7000")
args = parser.parse_args()
HOST, PORT = args.listen.split(":")

class UdpSink(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport
        print(f"[recv] listening on {HOST}:{PORT}", flush=True)

    def datagram_received(self, data, addr):
        try:
            print(f"[recv] from {addr}: {data.decode('utf-8')}", flush=True)
        except:
            print(f"[recv] from {addr}: {len(data)} bytes", flush=True)

async def main():
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UdpSink(), local_addr=(HOST, int(PORT))
    )
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        transport.close()

if __name__ == "__main__":
    asyncio.run(main())
