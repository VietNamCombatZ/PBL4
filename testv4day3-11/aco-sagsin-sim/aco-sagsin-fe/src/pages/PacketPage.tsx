import { useEffect, useMemo, useState } from 'react'
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
                      return (
                        <li key={pid} className="flex items-center justify-between">
                          <div className="cursor-pointer hover:text-white" onClick={() => setHoverNode(pid)}>
                            <div className="text-sm font-medium">{pid} - {n?.name ?? ''}</div>
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
        <Globe3D nodes={nodes} arcs={arcs} hoverNodeId={hoverNodeId} onHoverNode={setHoverNode} statusByNode={statusMap} />
      </div>
    </div>
  )
}
