import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../lib/store'
import Globe3D from '../components/Globe3D/Globe3D'
import { fmtMbps, fmtMs } from '../utils'

export default function RoutePage() {
  const { nodes, fetchNodes, currentRoute, findRoute, hoverNodeId, setHoverNode } = useStore()
  const [src, setSrc] = useState<number | ''>('')
  const [dst, setDst] = useState<number | ''>('')
  useEffect(() => { fetchNodes() }, [fetchNodes])

  const onFind = () => { if (src!=='' && dst!=='') findRoute(Number(src), Number(dst)) }
  const arcs = useMemo(() => {
    if (!currentRoute?.path?.length) return [] as any[]
    const list: any[] = []
    for (let i=0;i<currentRoute.path.length-1;i++){
      const a = nodes.find(n=>n.id===currentRoute.path[i])
      const b = nodes.find(n=>n.id===currentRoute.path[i+1])
      if (a&&b) list.push({ startLat:a.lat, startLng:a.lon, endLat:b.lat, endLng:b.lon })
    }
    return list
  }, [currentRoute, nodes])

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-1 space-y-3">
        <div className="bg-slate-900 rounded p-3">
          <div className="font-semibold mb-2">Chọn nguồn/đích</div>
          <select className="bg-slate-800 rounded px-2 py-1 w-full mb-2" value={src} onChange={e=>setSrc(Number(e.target.value))}>
            <option value="">Chọn src</option>
            {nodes.map(n=> <option key={n.id} value={n.id}>{n.id} - {n.name}</option>)}
          </select>
          <select className="bg-slate-800 rounded px-2 py-1 w-full mb-2" value={dst} onChange={e=>setDst(Number(e.target.value))}>
            <option value="">Chọn dst</option>
            {nodes.map(n=> <option key={n.id} value={n.id}>{n.id} - {n.name}</option>)}
          </select>
          <button className="bg-sky-600 px-3 py-1 rounded w-full" onClick={onFind}>Tìm tuyến (ACO)</button>
        </div>
        <div className="bg-slate-900 rounded p-3">
          <div className="font-semibold mb-2">Metrics</div>
          <div className="text-sm text-slate-300 space-y-1">
            <div>Latency: {fmtMs(currentRoute?.latency_ms)}</div>
            <div>Throughput: {fmtMbps(currentRoute?.throughput_mbps)}</div>
            <div>Cost: {currentRoute?.cost ?? '-'}</div>
          </div>
        </div>
        {currentRoute?.path && (
          <div className="bg-slate-900 rounded p-3">
            <div className="font-semibold mb-2">Path</div>
            <ol className="list-decimal list-inside text-sm">
              {currentRoute.path.map(pid => {
                const n = nodes.find(nn=>nn.id===pid)
                return <li key={pid} className="cursor-pointer hover:text-white" onClick={()=>setHoverNode(pid)}>{pid} - {n?.name ?? ''}</li>
              })}
            </ol>
          </div>
        )}
      </div>
      <div className="col-span-2">
        <Globe3D nodes={nodes} arcs={arcs} hoverNodeId={hoverNodeId} onHoverNode={setHoverNode} />
      </div>
    </div>
  )
}
