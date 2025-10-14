from dataclasses import dataclass
from typing import Dict, Tuple, Optional

@dataclass
class NodeInfo:
    node_id: int
    kind: str        # "sat", "plane", "ground"
    lat: float       # degrees
    lon: float       # degrees
    alt_km: float    # km (0 cho ground)
    host: str        # hostname trong docker network (ví dụ: node-5)
    port: int        # data port (mặc định 7300)

# Bảng next-hop: (src, dst) -> next_node_id
NextHopTable = Dict[Tuple[int, int], int]
