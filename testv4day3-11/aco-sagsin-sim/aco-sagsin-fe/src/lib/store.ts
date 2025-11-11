import { create } from 'zustand'
import type { NodeInfo, LinkInfo, RouteResult, PacketEvent, PacketStatus } from './types'
import { getNodes, getLinks, postRoute, sendPacket, openEvents } from './api'

type PacketSession = { path: number[]; updates: Record<number, PacketStatus>; cumulative_latency_ms?: number; perHopLatency?: Record<number, number> }

type State = {
  nodes: NodeInfo[]
  links: LinkInfo[]
  currentRoute?: RouteResult
  hoverNodeId?: number
  packetSessions: Record<string, PacketSession>
  fetchNodes: () => Promise<void>
  fetchLinks: () => Promise<void>
  findRoute: (src: number, dst: number) => Promise<void>
  startPacket: (src: number, dst: number, protocol: 'TCP'|'UDP') => Promise<string>
  handlePacketEvent: (e: PacketEvent) => void
  setHoverNode: (id?: number) => void
  clearRoute: () => void
  ensureEventStream: () => void
}

let closeEvents: (() => void) | null = null

export const useStore = create<State>((set, get) => ({
  nodes: [],
  links: [],
  packetSessions: {},
  async fetchNodes() {
    const n = await getNodes(); set({ nodes: n })
  },
  async fetchLinks() {
    const l = await getLinks(); set({ links: l })
  },
  async findRoute(src, dst) {
    const r = await postRoute(src, dst); set({ currentRoute: r })
  },
  async startPacket(src, dst, protocol) {
    const { sessionId } = await sendPacket(src, dst, protocol)
    const route = get().currentRoute
    const path = route?.path ?? []
    const updates: Record<number, PacketStatus> = {}
  path.forEach((id) => { updates[id] = 'pending' })
  set((s) => ({ packetSessions: { ...s.packetSessions, [sessionId]: { path, updates, perHopLatency: {} } } }))
    get().ensureEventStream()
    return sessionId
  },
  ensureEventStream() {
    if (closeEvents) return
    openEvents((e) => get().handlePacketEvent(e)).then((cls) => { closeEvents = cls })
  },
  handlePacketEvent(e) {
    set((s) => {
      const cur = s.packetSessions[e.sessionId]
      if (!cur) return s
  const updates = { ...cur.updates, [e.nodeId]: e.status }
  const per = { ...(cur.perHopLatency || {}) }
  if (e.cumulative_latency_ms != null) per[e.nodeId] = e.cumulative_latency_ms
  return { packetSessions: { ...s.packetSessions, [e.sessionId]: { ...cur, updates, perHopLatency: per, cumulative_latency_ms: e.cumulative_latency_ms ?? cur.cumulative_latency_ms } } }
    })
  },
  setHoverNode(id) { set({ hoverNodeId: id }) },
  clearRoute() { set({ currentRoute: undefined }) },
}))
