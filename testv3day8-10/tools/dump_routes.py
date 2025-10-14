# tools/dump_routes.py
import argparse, socket, json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", type=int, required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=17200)  # Đổi nếu bạn map 7200->17200 khác đi
    args = ap.parse_args()

    s = socket.create_connection((args.host, args.port), timeout=5)
    req = {"dump": {"node": args.node}}
    s.sendall((json.dumps(req) + "\n").encode())
    data = s.recv(1<<20).decode().strip()
    s.close()

    try:
        resp = json.loads(data)
    except:
        print(data); return

    print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    main()
