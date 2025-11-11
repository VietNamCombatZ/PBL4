import { useEffect, useMemo, useState } from 'react'
import type { PacketStatus } from '../lib/types'
import { useStore } from '../lib/store'
import Globe3D from '../components/Globe3D/Globe3D'
import { fmtMs } from '../utils'

export default function PacketPage() {
  const { nodes, fetchNodes, currentRoute, findRoute, packetSessions, startPacket, hoverNodeId, setHoverNode } = useStore()
  const [src, setSrc] = useState<number | ''>('')
  const [dst, setDst] = useState<number | ''>('')
  const [protocol, setProtocol] = useState<'TCP'|'UDP'>('TCP')
  const [sessionId, setSessionId] = useState<string>('')
  useEffect(() => { fetchNodes() }, [fetchNodes])

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

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-1 space-y-3">
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
              <ul className="space-y-2">
                {session.path.map((pid: number, idx: number) => {
                  const n = nodes.find(nn => nn.id === pid)
                  const st = displayedStatus[pid] || 'pending'
                  const isLast = idx === session.path.length - 1
                  const latMs = session?.latencyByNode?.[pid]
                  return (
                    <li key={pid} className="flex items-center justify-between">
                      <div className="cursor-pointer hover:text-white" onClick={() => setHoverNode(pid)}>
                        <div className="text-sm font-medium">{pid} - {n?.name ?? ''}</div>
                        <div className="text-xs text-slate-400">{fmtMs(latMs ?? undefined)}</div>
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
