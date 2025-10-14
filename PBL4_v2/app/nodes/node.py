import os
import time
import json
import socket
import threading

CTRL_HOST = os.getenv("CTRL_HOST", "controller")
CTRL_PORT = int(os.getenv("CTRL_PORT", "5000"))
HEARTBEAT_INTERVAL = 10


class NodeClient:
	def __init__(self, node_id: int):
		self.node_id = node_id
		self.sock: socket.socket | None = None
		self.running = True
		self.lock = threading.Lock()

	def start(self):
		threading.Thread(target=self._connect_loop, daemon=True).start()
		threading.Thread(target=self._heartbeat_loop, daemon=True).start()
		while self.running:
			time.sleep(5)

	def _connect_loop(self):
		while self.running:
			if not self.sock:
				try:
					s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					s.settimeout(10)
					s.connect((CTRL_HOST, CTRL_PORT))
					reg = json.dumps({"node_id": self.node_id}) + "\n"
					s.sendall(reg.encode())
					self.sock = s
					threading.Thread(target=self._reader, args=(s,), daemon=True).start()
					print(f"[node {self.node_id}] Connected to controller")
				except Exception as e:
					print(f"[node {self.node_id}] connect failed: {e}")
					self.sock = None
			time.sleep(5)

	def _reader(self, s: socket.socket):
		buf = b""
		try:
			while True:
				chunk = s.recv(4096)
				if not chunk:
					break
				buf += chunk
				while b"\n" in buf:
					line, buf = buf.split(b"\n", 1)
					self._handle_line(line)
		except Exception as e:
			print(f"[node {self.node_id}] reader error {e}")
		finally:
			s.close()
			if self.sock is s:
				self.sock = None
			print(f"[node {self.node_id}] disconnected")

	def _handle_line(self, raw: bytes):
		try:
			msg = json.loads(raw.decode(errors='ignore'))
		except Exception:
			return
		mtype = msg.get("type")
		if mtype == "welcome":
			pass
		elif mtype == "snapshot":
			# Could store counts; placeholder
			pass
		elif mtype == "route_reply":
			print(f"[node {self.node_id}] route reply: dest={msg.get('dest')} next={msg.get('next_hop')}")
		elif mtype == "hb_ack":
			# ignore for now
			pass

	def _heartbeat_loop(self):
		while self.running:
			time.sleep(HEARTBEAT_INTERVAL)
			if not self.sock:
				continue
			try:
				hb = json.dumps({"type": "heartbeat", "ts": time.time()}) + "\n"
				self.sock.sendall(hb.encode())
			except Exception:
				self.sock = None

	def query_route(self, dest: int):
		if not self.sock:
			return
		try:
			q = json.dumps({"type": "route_query", "dest": dest}) + "\n"
			self.sock.sendall(q.encode())
		except Exception:
			self.sock = None


def main():
	node_id = int(os.getenv("NODE_ID", "0"))
	role = os.getenv("ROLE", "node")
	print(f"[node {node_id}] Starting node step2 role={role}")
	client = NodeClient(node_id)
	client.start()


if __name__ == "__main__":
	main()
