import { create } from 'zustand'
import type { NodeInfo, LinkInfo, RouteResult, PacketEvent, PacketStatus } from './types'
import { getNodes, getLinks, postRoute, sendPacket, openEvents } from './api'
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8080'

type PacketSession = { path: number[]; updates: Record<number, PacketStatus>; cumulative_latency_ms?: number; perHopLatency?: Record<number, number>; messages?: Record<number, string>; created_at?: number }

type State = {
  nodes: NodeInfo[]
  links: LinkInfo[]
  currentRoute?: RouteResult
  routeError?: string
  routeLoading?: boolean
  hoverNodeId?: number
  packetSessions: Record<string, PacketSession>
  fetchNodes: () => Promise<void>
  fetchLinks: () => Promise<void>
  findRoute: (src: number, dst: number) => Promise<void>
  startPacket: (src: number, dst: number, protocol: 'TCP'|'UDP') => Promise<string>
  clearSession: (sessionId: string) => void
  handlePacketEvent: (e: PacketEvent) => void
  setHoverNode: (id?: number) => void
  clearRoute: () => void
  ensureEventStream: () => void
  startNodeMotionPolling?: (intervalMs?: number) => () => void
}

let closeEvents: (() => void) | null = null

export const useStore = create<State>((set, get) => ({
  nodes: [],
  links: [],
  routeError: undefined,
  routeLoading: false,
  packetSessions: {},
  async fetchNodes() {
    const n = await getNodes(); set({ nodes: n })
  },
  async fetchLinks() {
    const l = await getLinks(); set({ links: l })
  },
  async findRoute(src, dst) {
    set({ routeLoading: true, routeError: undefined })
    try {
      const r = await postRoute(src, dst)
      set({ currentRoute: r, routeError: undefined })
    } catch (e: any) {
      // capture numeric status if thrown by api helper
      const msg = e?.message === '422' ? 'No feasible path (disconnected components or disabled links).' : (e?.message || 'Route request failed')
      set({ routeError: msg, currentRoute: undefined })
    } finally {
      set({ routeLoading: false })
    }
  },
  async startPacket(src, dst, protocol) {
    // sendPacket may return the computed path from the server; prefer that so
    // the FE timeline matches the events emitted by the controller.
    const res: any = await sendPacket(src, dst, protocol)
    const sessionId: string = res.sessionId
    const pathFromServer: number[] | undefined = res.path
    // If server provided a path (and optional cost), set it as the current route
    if (pathFromServer && pathFromServer.length > 0) {
      const r = { path: pathFromServer, cost: res.cost } as RouteResult
      set({ currentRoute: r })
    }
    const route = get().currentRoute
    const path = pathFromServer ?? route?.path ?? []
    const updates: Record<number, PacketStatus> = {}
  path.forEach((id) => { updates[id] = 'pending' })
  set((s) => ({ packetSessions: { ...s.packetSessions, [sessionId]: { path, updates, perHopLatency: {}, created_at: Date.now() } } }))
    get().ensureEventStream()
    return sessionId
  },
  ensureEventStream() {
    if (closeEvents) return
    openEvents((e) => get().handlePacketEvent(e)).then((cls) => { closeEvents = cls })
  },
  clearSession(sessionId) { set((s) => { const copy = { ...s.packetSessions }; delete copy[sessionId]; return { packetSessions: copy } }) },
  handlePacketEvent(e) {
    set((s) => {
      const cur = s.packetSessions[e.sessionId]
      // If we don't have a session record yet (e.g., session started outside the UI),
      // create a minimal session and then apply the incoming event. We will
      // reconstruct the path incrementally as events arrive.
      if (!cur) {
        const path = [e.nodeId]
        const updates: Record<number, PacketStatus> = { [e.nodeId]: e.status }
        const perHopLatency: Record<number, number> = {}
        if (e.cumulative_latency_ms != null) perHopLatency[e.nodeId] = e.cumulative_latency_ms
        const messages: Record<number, string> = {}
        if (e.message) messages[e.nodeId] = e.message
        return { packetSessions: { ...s.packetSessions, [e.sessionId]: { path, updates, perHopLatency, cumulative_latency_ms: e.cumulative_latency_ms, messages, created_at: Date.now() } } }
      }
      // existing session: update its status, per-hop latency and messages.
      const updates = { ...cur.updates, [e.nodeId]: e.status }
      const per = { ...(cur.perHopLatency || {}) }
      if (e.cumulative_latency_ms != null) per[e.nodeId] = e.cumulative_latency_ms
      const msgs = { ...(cur.messages || {}) }
      if (e.message) msgs[e.nodeId] = e.message
      // ensure the path contains this node (append if not present). Events are
      // emitted in path order, so appending is safe.
      const path = Array.isArray(cur.path) ? [...cur.path] : []
      if (!path.includes(e.nodeId)) path.push(e.nodeId)
      return { packetSessions: { ...s.packetSessions, [e.sessionId]: { ...cur, path, updates, perHopLatency: per, cumulative_latency_ms: e.cumulative_latency_ms ?? cur.cumulative_latency_ms, messages: msgs, created_at: cur.created_at ?? Date.now() } } }
    })
  },
  setHoverNode(id) { set({ hoverNodeId: id }) },
  clearRoute() { set({ currentRoute: undefined }) },
  startNodeMotionPolling(intervalMs = 1000) {
    let timer: any
    const tick = async () => {
      try {
        const res = await fetch(`${API_BASE}/nodes/positions`)
        if (!res.ok) throw new Error('positions fetch failed')
        const pos: Array<{ id: number; lat: number; lon: number; alt_km?: number }> = await res.json()
        const map = new Map(pos.map(p => [p.id, p]))
        set(state => ({
          nodes: state.nodes.map(n => {
            const p = map.get(n.id)
            return p ? { ...n, lat: p.lat, lon: p.lon } : n
          })
        }))
      } catch (_) {
        // ignore transient errors
      } finally {
        timer = setTimeout(tick, intervalMs)
      }
    }
    tick()
    return () => clearTimeout(timer)
  },
}))
