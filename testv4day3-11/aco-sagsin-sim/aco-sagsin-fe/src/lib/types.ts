export type NodeKind = 'sat' | 'air' | 'ground' | 'sea'
export interface NodeInfo {
  id: number; name: string; kind: NodeKind;
  lat: number; lon: number; alt_m?: number;
  orbit?: { tle?: string };
}
export interface LinkInfo { u: number; v: number; enabled: boolean }
export interface RouteResult {
  path: number[]; cost?: number;
  latency_ms?: number; throughput_mbps?: number;
}
export type PacketStatus = 'pending' | 'success'
export interface PacketEvent {
  type: 'packet-progress';
  sessionId: string; nodeId: number;
  status: PacketStatus;
  arrived_ms?: number; cumulative_latency_ms?: number;
  message?: string;
}
