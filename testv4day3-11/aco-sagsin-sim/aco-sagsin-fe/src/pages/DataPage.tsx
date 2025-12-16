import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../lib/store'
import Globe3D from '../components/Globe3D/Globe3D'
import { getSpeed, setSpeed } from '../lib/api'

export default function DataPage() {
  const { nodes, fetchNodes, hoverNodeId, setHoverNode, startNodeMotionPolling } = useStore((s) => ({ nodes: s.nodes, fetchNodes: s.fetchNodes, hoverNodeId: s.hoverNodeId, setHoverNode: s.setHoverNode, startNodeMotionPolling: (s as any).startNodeMotionPolling }))
  const [kind, setKind] = useState<string>('all')
  const [q, setQ] = useState('')
  useEffect(() => { fetchNodes() }, [fetchNodes])
  // start/stop motion polling and reset speed on enter
  useEffect(() => {
    setSpeed(1).catch(()=>{})
    const stop = startNodeMotionPolling?.(1000)
    return () => {
      if (stop) stop()
      setSpeed(1).catch(()=>{})
      fetchNodes().catch(()=>{})
    }
  }, [startNodeMotionPolling])
  // local speed control
  const [mult, setMult] = useState<number>(1)
  useEffect(() => { getSpeed().then(s => setMult(s.multiplier)).catch(()=>{}) }, [])
  const cycleSpeed = async () => {
    const next = mult === 1 ? 10 : mult === 10 ? 100 : 1
    try { const res = await setSpeed(next); if (res.ok) setMult(res.multiplier) } catch {}
  }
  const filtered = useMemo(() => nodes.filter(n => (kind==='all'||n.kind===kind) && (`${n.id}`.includes(q) || n.name.toLowerCase().includes(q.toLowerCase()))), [nodes, kind, q])
  const counts = useMemo(() => nodes.reduce<Record<string,number>>((a,n)=>{a[n.kind]=(a[n.kind]||0)+1;return a},{}) , [nodes])
  const hoverNode = nodes.find(n => n.id === hoverNodeId)
  const total = useMemo(() => nodes?.length ?? 0, [nodes])
  useEffect(() => { console.log('Nodes count:', total) }, [total])
  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2">
        <div className="flex items-center gap-2 mb-2">
          <button onClick={cycleSpeed} className="bg-slate-700 hover:bg-slate-600 text-xs px-2 py-1 rounded">{mult === 1 ? '▶︎ 1x' : mult === 10 ? '⏩ 10x' : '⏭ 100x'}</button>
          <input className="bg-slate-800 rounded px-2 py-1" placeholder="Tìm theo id/name" value={q} onChange={e=>setQ(e.target.value)} />
          <select className="bg-slate-800 rounded px-2 py-1" value={kind} onChange={e=>setKind(e.target.value)}>
            <option value="all">All</option><option value="ground">ground</option><option value="air">air</option><option value="sea">sea</option><option value="sat">sat</option>
          </select>
          <button className="bg-sky-600 px-3 py-1 rounded" onClick={()=>fetchNodes()}>Làm mới</button>
          <div className="text-sm text-slate-400">Nodes: {total}</div>
          <div className="text-sm text-slate-400 ml-auto">Counts: {Object.entries(counts).map(([k,v])=>`${k}:${v}`).join(' ')}</div>
        </div>
        <Globe3D nodes={filtered} hoverNodeId={hoverNodeId} onHoverNode={setHoverNode} />
        <div className="mt-3 max-h-72 overflow-auto text-sm">
          <table className="w-full">
            <thead className="text-slate-400"><tr><th className="text-left">id</th><th className="text-left">name</th><th>kind</th><th>lat</th><th>lon</th><th>alt_m</th></tr></thead>
            <tbody>
              {filtered.map(n=> (
                <tr key={n.id} className="border-b border-slate-800"><td>{n.id}</td><td>{n.name}</td><td className="text-center">{n.kind}</td><td>{n.lat.toFixed(3)}</td><td>{n.lon.toFixed(3)}</td><td>{n.alt_m ?? '-'}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="col-span-1">
        <div className="bg-slate-900 rounded p-3 sticky top-24">
          <div className="font-semibold mb-2">Hover Node</div>
          {!hoverNode ? <div className="text-slate-400">—</div> : (
            <div className="text-sm">
              <div>id: {hoverNode.id}</div>
              <div>name: {hoverNode.name}</div>
              <div>kind: {hoverNode.kind}</div>
              <div>lat/lon: {hoverNode.lat.toFixed(3)}, {hoverNode.lon.toFixed(3)}</div>
              <div>alt_m: {hoverNode.alt_m ?? '-'}</div>
              <div>orbit: {hoverNode.orbit?.tle ? 'TLE available' : '-'}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
