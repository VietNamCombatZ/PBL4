import { useEffect, useMemo, useState } from 'react'
import type { PacketStatus } from '../lib/types'
import { useStore } from '../lib/store'
import Globe3D from '../components/Globe3D/Globe3D'
import { fmtMs } from '../utils'
import { getSpeed, setSpeed } from '../lib/api'

export default function PacketPage() {
  const { nodes, fetchNodes, currentRoute, findRoute, packetSessions, startPacket, hoverNodeId, setHoverNode, clearSession, startNodeMotionPolling } = useStore()
  const [src, setSrc] = useState<number | ''>('')
  const [dst, setDst] = useState<number | ''>('')
  const [protocol, setProtocol] = useState<'TCP'|'UDP'>('TCP')
  const [sessionId, setSessionId] = useState<string>('')
  useEffect(() => { fetchNodes() }, [fetchNodes])
  // start/stop motion and reset speed per page
  useEffect(() => {
    setSpeed(1).catch(()=>{})
    const stop = startNodeMotionPolling?.(1000)
    return () => { if (stop) stop() }
  }, [startNodeMotionPolling])
  // local speed control
  const [mult, setMult] = useState<number>(1)
  useEffect(() => { getSpeed().then(s => setMult(s.multiplier)).catch(()=>{}) }, [])
  const cycleSpeed = async () => {
    const next = mult === 1 ? 10 : mult === 10 ? 100 : 1
    try { const res = await setSpeed(next); if (res.ok) setMult(res.multiplier) } catch {}
  }

  // ensure we subscribe to controller SSE on page mount so events originating
  // outside the UI (host curl / other containers) are received and populate
  // `packetSessions` in the store.
  useEffect(() => {
    try {
      // ensureEventStream is stable from the store
      ;(async () => { await (useStore.getState().ensureEventStream?.() as any) })()
    } catch {}
  }, [])

  // if a session wasn't explicitly selected but events arrive, auto-select
  // the most-recent session so the UI shows incoming events triggered from
  // other sources (e.g. host curl). We watch packetSessions object and set
  // sessionId to the newest key when none is selected.
  useEffect(() => {
    if (sessionId) return
    const ids = Object.keys(packetSessions)
    if (ids.length > 0) {
      setSessionId(ids[ids.length - 1])
    }
  }, [packetSessions, sessionId])

  const onSend = async () => {
    if (src===''||dst==='') return
    if (!currentRoute?.path?.length) await findRoute(Number(src), Number(dst))
    const s = await startPacket(Number(src), Number(dst), protocol)
    setSessionId(s)
  }
  const session = packetSessions[sessionId]
  const statusMap = session?.updates
  // derive displayed statuses so that when a later node is success,
  // all previous nodes are shown success as well
  const displayedStatus: Record<number, PacketStatus> = {}
  if (session?.path) {
    session.path.forEach((pid: number) => { displayedStatus[pid] = statusMap?.[pid] ?? 'pending' })
    for (let i = 0; i < session.path.length; i++) {
      const pid = session.path[i]
      if (displayedStatus[pid] === 'success') {
        for (let j = 0; j < i; j++) displayedStatus[session.path[j]] = 'success'
      }
    }
  }
  const arcs = useMemo(() => {
    if (!session?.path?.length) return [] as any[]
    const list: any[] = []
    for (let i=0;i<session.path.length-1;i++){
      const a = nodes.find(n=>n.id===session.path[i])
      const b = nodes.find(n=>n.id===session.path[i+1])
      if (a&&b) list.push({ startLat:a.lat, startLng:a.lon, endLat:b.lat, endLng:b.lon })
    }
    return list
  }, [session, nodes])

  // messages per node for the current session
  const messagesByNode = session?.messages ?? {}

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-1 space-y-3">
        <div className="flex justify-end">
          <button onClick={cycleSpeed} className="bg-slate-700 hover:bg-slate-600 text-xs px-2 py-1 rounded">{mult === 1 ? '▶︎ 1x' : mult === 10 ? '⏩ 10x' : '⏭ 100x'}</button>
        </div>
        {/* Session history: pick older sessions created either by UI or external sends */}
        <div className="bg-slate-900 rounded p-3">
          <div className="font-semibold mb-2">Session History</div>
          <div className="text-sm">
            {Object.keys(packetSessions).length === 0 && <div className="text-slate-400">No sessions yet</div>}
            <ul className="space-y-1 max-h-48 overflow-auto">
              {Object.keys(packetSessions).slice().reverse().map((sid) => {
                const s = packetSessions[sid]
                const preview = s?.path ? s.path.join('\u2192') : ''
                const ts = s?.created_at ? new Date(s.created_at).toLocaleString() : ''
                return (
                  <li key={sid} className="flex items-center justify-between">
                    <button
                      className={`w-full text-left px-2 py-1 rounded ${sid === sessionId ? 'bg-sky-700' : 'bg-slate-800 hover:bg-slate-700'}`}
                      onClick={() => setSessionId(sid)}
                    >
                      <div className="text-xs font-medium">{sid.slice(0,8)}</div>
                      <div className="text-xxs text-slate-400">{preview}</div>
                      <div className="text-xxs text-slate-500 mt-1">{ts}</div>
                    </button>
                    <button className="ml-2 text-xs px-2 py-1 bg-rose-600 rounded" onClick={() => { clearSession(sid); if (sessionId===sid) setSessionId('') }}>Delete</button>
                  </li>
                )
              })}
            </ul>
          </div>
        </div>
        <div className="bg-slate-900 rounded p-3">
          <div className="font-semibold mb-2">Gửi gói</div>
          <select className="bg-slate-800 rounded px-2 py-1 w-full mb-2" value={src} onChange={e=>setSrc(Number(e.target.value))}>
            <option value="">Chọn src</option>
            {nodes.map(n=> <option key={n.id} value={n.id}>{n.id} - {n.name}</option>)}
          </select>
          <select className="bg-slate-800 rounded px-2 py-1 w-full mb-2" value={dst} onChange={e=>setDst(Number(e.target.value))}>
            <option value="">Chọn dst</option>
            {nodes.map(n=> <option key={n.id} value={n.id}>{n.id} - {n.name}</option>)}
          </select>
          <select className="bg-slate-800 rounded px-2 py-1 w-full mb-2" value={protocol} onChange={e=>setProtocol(e.target.value as any)}>
            <option value="TCP">TCP</option>
            <option value="UDP">UDP</option>
          </select>
          <button className="bg-sky-600 px-3 py-1 rounded w-full" onClick={onSend}>Gửi gói</button>
        </div>
        <div className="bg-slate-900 rounded p-3">
          <div className="font-semibold mb-2">Tổng độ trễ</div>
          <div className="text-sm">{fmtMs(session?.cumulative_latency_ms)}</div>
        </div>
        {session?.path && (
          <div className="bg-slate-900 rounded p-3">
            <div className="font-semibold mb-2">Trạng thái</div>
            {/* vertical timeline: node text on left, status circle and connecting line on right */}
            <div className="text-sm">
              {(() => {
                // derive displayed statuses so that once a later node is success,
                // all previous nodes up to it are considered success too
                const displayed: Record<number, string> = {}
                const path = session.path
                // initialize with existing statuses (default pending)
                path.forEach((pid: number) => { displayed[pid] = statusMap?.[pid] ?? 'pending' })
                // propagate successes backwards
                for (let i = 0; i < path.length; i++) {
                  const pid = path[i]
                  if (displayed[pid] === 'success') {
                    for (let j = 0; j < i; j++) displayed[path[j]] = 'success'
                  }
                }
                return (
                  <ul className="space-y-2">
                    {path.map((pid: number, idx: number) => {
                      const n = nodes.find(nn => nn.id === pid)
                      const st = displayed[pid] || 'pending'
                      const isLast = idx === path.length - 1
                      const perLatency = (session.perHopLatency && session.perHopLatency[pid]) ?? undefined
                      return (
                        <li key={pid} className="flex items-center justify-between">
                          <div className="cursor-pointer hover:text-white" onClick={() => setHoverNode(pid)}>
                            <div className="text-sm font-medium">{pid} - {n?.name ?? ''}</div>
                            <div className="text-xs text-slate-400">{perLatency != null ? fmtMs(perLatency) : '-'}</div>
                            {messagesByNode[pid] && <div className="text-xs text-amber-300 mt-1">Message: {messagesByNode[pid]}</div>}
                          </div>
                          <div className="flex flex-col items-center ml-4">
                            {/* circle */}
                            <div className={`w-4 h-4 rounded-full ${st === 'success' ? 'bg-emerald-500' : 'bg-amber-500'}`}></div>
                            {/* connecting vertical line (except last) */}
                            {!isLast && <div className="w-px h-6 bg-slate-700 mt-1"></div>}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                )
              })()}
            </div>
          </div>
        )}
      </div>
      <div className="col-span-2">
        <Globe3D nodes={nodes} arcs={arcs} hoverNodeId={hoverNodeId} onHoverNode={setHoverNode} statusByNode={displayedStatus} />
      </div>
    </div>
  )
}
