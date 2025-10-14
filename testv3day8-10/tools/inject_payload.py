# python3 tools/inject_payload.py  --src 1 --dst 5 --msg "Hello ACO"
import argparse, asyncio, json

async def main(src, dst, msg):
    reader, writer = await asyncio.open_connection("localhost", 17200)
    writer.write((json.dumps({"send": {"src": src, "dst": dst, "payload": msg}})+"\n").encode())
    line = await reader.readline()
    print(line.decode().strip())
    writer.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=int, required=True)
    p.add_argument("--dst", type=int, required=True)
    p.add_argument("--msg", type=str, required=True)
    a = p.parse_args()
    asyncio.run(main(a.src, a.dst, a.msg))
