import os
import time
import json
import socket
import threading
from typing import Dict, Tuple, Any
from app.shared.fetchers import DataFetcher, Position
from app.shared.geo import haversine_km


PORT = int(os.getenv("CTRL_PORT", "5000"))
REFRESH_SECS = 60
PUSH_INTERVAL_SECS = 15


class Controller:
	def __init__(self):
		self.fetcher = DataFetcher()
		self.clients: Dict[int, Tuple[socket.socket, Tuple[str, int]]] = {}
		self.routing: Dict[int, Dict[int, int]] = {}  # routing[src][dst] = next_hop
		self.lock = threading.Lock()

	def start(self):
		threading.Thread(target=self._refresh_loop, daemon=True).start()
		threading.Thread(target=self._push_loop, daemon=True).start()
		self._tcp_server()

	def _refresh_loop(self):
		while True:
			try:
				self.fetcher.refresh_all()
				snap = self.fetcher.snapshot()
				print(f"[controller] refresh: sats={len(snap['satellites'])} gs={len(snap['ground_stations'])} ac={len(snap['aircraft'])}")
				self._rebuild_routing_baseline()
			except Exception as e:
				print("[controller] refresh error", e)
			time.sleep(REFRESH_SECS)

	def _push_loop(self):
		while True:
			time.sleep(PUSH_INTERVAL_SECS)
			with self.lock:
				snapshot = self.fetcher.snapshot()
				# send condensed snapshot (only counts + maybe subset?)
				payload = {
					"type": "snapshot",
					"ts": time.time(),
					"counts": {
						"satellites": len(snapshot['satellites']),
						"ground_stations": len(snapshot['ground_stations']),
						"aircraft": len(snapshot['aircraft'])
					}
				}
				data = (json.dumps(payload) + "\n").encode()
				dead = []
				for nid, (conn, _) in self.clients.items():
					try:
						conn.sendall(data)
					except Exception:
						dead.append(nid)
				for d in dead:
					self.clients.pop(d, None)
				if self.clients:
					print(f"[controller] pushed snapshot to {len(self.clients)} nodes")

	def _tcp_server(self):
		srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		srv.bind(("0.0.0.0", PORT))
		srv.listen(50)
		print(f"[controller] TCP server listening on {PORT}")
		while True:
			conn, addr = srv.accept()
			threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

	def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]):
		try:
			line = conn.recv(1024).decode(errors='ignore').strip()
			# Expect registration JSON
			nid = None
			try:
				reg = json.loads(line)
				nid = int(reg.get("node_id"))
			except Exception:
				conn.close()
				return
			with self.lock:
				self.clients[nid] = (conn, addr)
			print(f"[controller] node {nid} connected from {addr}")
			conn.sendall((json.dumps({"type": "welcome", "node_id": nid}) + "\n").encode())
			buf = b""
			while True:
				chunk = conn.recv(4096)
				if not chunk:
					break
				buf += chunk
				while b"\n" in buf:
					line, buf = buf.split(b"\n", 1)
					self._process_message(nid, line)
		except Exception as e:
			print(f"[controller] client error {addr} {e}")
		finally:
			with self.lock:
				for k, v in list(self.clients.items()):
					if v[0] is conn:
						self.clients.pop(k, None)
			conn.close()
			print(f"[controller] node disconnected {addr}")

	def _process_message(self, nid: int, raw: bytes):
		try:
			msg = json.loads(raw.decode(errors='ignore'))
		except Exception:
			return
		mtype = msg.get("type")
		if mtype == "heartbeat":
			# echo ack (could include routing for node later)
			ack = json.dumps({"type": "hb_ack", "t": time.time()}) + "\n"
			try:
				self.clients[nid][0].sendall(ack.encode())
			except Exception:
				pass
		elif mtype == "route_query":
			dest = int(msg.get("dest"))
			nh = self.routing.get(nid, {}).get(dest)
			resp = {"type": "route_reply", "dest": dest, "next_hop": nh}
			try:
				self.clients[nid][0].sendall((json.dumps(resp) + "\n").encode())
			except Exception:
				pass

	def _rebuild_routing_baseline(self):
		# Very simple baseline: fully connected over currently connected nodes using distance heuristic -> choose nearest step toward destination.
		with self.lock:
			nodes = list(self.clients.keys())
		# For now assign synthetic positions on a circle to nodes until real mapping implemented
		pos_map: Dict[int, Tuple[float, float]] = {}
		for idx, nid in enumerate(sorted(nodes)):
			angle = 360.0 * idx / max(len(nodes), 1)
			lat = 20 * (idx % 5)  # fake distribution
			lon = angle
			pos_map[nid] = (lat, lon)
		routing: Dict[int, Dict[int, int]] = {}
		for src in nodes:
			routing[src] = {}
			for dst in nodes:
				if src == dst:
					continue
				# pick neighbor with minimal distance to destination (excluding self); naive O(n^2)
				best_nh = None
				best_dist = float('inf')
				lat_dst, lon_dst = pos_map[dst]
				for cand in nodes:
					if cand == src:
						continue
					lat_c, lon_c = pos_map[cand]
					d = haversine_km(lat_c, lon_c, lat_dst, lon_dst)
					if d < best_dist:
						best_dist = d
						best_nh = cand
				if best_nh is not None:
					routing[src][dst] = best_nh
		with self.lock:
			self.routing = routing
		if nodes:
			print(f"[controller] routing baseline built for {len(nodes)} nodes")


def main():
	print("[controller] Starting controller (step 2)...")
	Controller().start()


if __name__ == "__main__":
	main()
