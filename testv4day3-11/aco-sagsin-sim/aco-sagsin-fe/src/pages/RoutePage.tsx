import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../lib/store'
import Globe3D from '../components/Globe3D/Globe3D'
import { fmtMbps, fmtMs } from '../utils'
import { getSpeed, setSpeed } from '../lib/api'
import metrics from '../lib/metrics'

export default function RoutePage() {
  const { nodes, fetchNodes, links, fetchLinks, currentRoute, findRoute, hoverNodeId, setHoverNode, routeError, routeLoading, startNodeMotionPolling } = useStore()
  const [src, setSrc] = useState<number | ''>('')
  const [dst, setDst] = useState<number | ''>('')
  const [rwrPath, setRwrPath] = useState<number[] | undefined>(undefined)
  const [showACO, setShowACO] = useState(true)
  const [showRWR, setShowRWR] = useState(true)
  useEffect(() => { fetchNodes() }, [fetchNodes])
  useEffect(() => { fetchLinks() }, [fetchLinks])
  // Start dynamic motion polling (sat/air/sea positions) on mount
  useEffect(() => {
    // Reset speed to 1x on page enter
    setSpeed(1).catch(()=>{})
    const stop = startNodeMotionPolling?.(1000)
    return () => { if (stop) stop() }
  }, [startNodeMotionPolling])
  // Local speed control
  const [mult, setMult] = useState<number>(1)
  useEffect(() => { getSpeed().then(s => setMult(s.multiplier)).catch(()=>{}) }, [])
  const cycleSpeed = async () => {
    const next = mult === 1 ? 10 : mult === 10 ? 100 : 1
    try { const res = await setSpeed(next); if (res.ok) setMult(res.multiplier) } catch {}
  }

  // Random Walk with Restart baseline: try many random walks and return the
  // shortest successful path found. restartProb in [0,1], attempts controls how
  // many independent walks to try.
  const runRWR = (srcId: number, dstId: number, opts?: { attempts?: number, restartProb?: number, maxLen?: number }) => {
    const attempts = opts?.attempts ?? 300
    const restartProb = opts?.restartProb ?? 0.15
    const maxLen = opts?.maxLen ?? 200
    // build adjacency
    const adj: Record<number, number[]> = {}
    ;(links || []).forEach(l => {
      if (!l.enabled) return
      if (!adj[l.u]) adj[l.u] = []
      if (!adj[l.v]) adj[l.v] = []
      adj[l.u].push(l.v)
      adj[l.v].push(l.u)
    })
    let best: number[] | undefined = undefined
    for (let a = 0; a < attempts; a++) {
      let cur = srcId
      let path: number[] = [cur]
      for (let step = 0; step < maxLen; step++) {
        if (cur === dstId) break
        if (Math.random() < restartProb) {
          cur = srcId
          path = [cur]
          continue
        }
  const nbrs = adj[cur] || []
        if (nbrs.length === 0) break
        const nxt = nbrs[Math.floor(Math.random() * nbrs.length)]
        path.push(nxt)
        cur = nxt
        if (cur === dstId) break
      }
      if (path[path.length - 1] === dstId) {
        if (!best || path.length < best.length) best = path
      }
    }
    return best
  }

  const onFind = () => { if (src!=='' && dst!=='') findRoute(Number(src), Number(dst)) }
  const arcs = useMemo(() => {
    const list: any[] = []
    if (showACO && currentRoute?.path?.length) {
      for (let i=0;i<currentRoute.path.length-1;i++){
        const a = nodes.find(n=>n.id===currentRoute.path[i])
        const b = nodes.find(n=>n.id===currentRoute.path[i+1])
        if (a&&b) list.push({ startLat:a.lat, startLng:a.lon, endLat:b.lat, endLng:b.lon, color: '#38bdf8' })
      }
    }
    if (showRWR && rwrPath && rwrPath.length) {
      for (let i=0;i<rwrPath.length-1;i++){
        const a = nodes.find(n=>n.id===rwrPath[i])
        const b = nodes.find(n=>n.id===rwrPath[i+1])
        if (a&&b) list.push({ startLat:a.lat, startLng:a.lon, endLat:b.lat, endLng:b.lon, color: '#f97316' })
      }
    }
    return list
  }, [currentRoute, nodes, rwrPath, showACO, showRWR])

  // computed metrics for ACO and RWR using the formulas in src/lib/metrics
  const acoComputedLatency = useMemo(() => {
    if (!currentRoute?.path) return undefined
    const ms = metrics.pathLatencyMsForNodes(currentRoute.path, nodes)
    return isFinite(ms) ? ms : undefined
  }, [currentRoute?.path, nodes])
  const acoComputedThroughput = useMemo(() => {
    if (!currentRoute?.path) return undefined
    const mbps = metrics.pathThroughputMbpsForNodes(currentRoute.path, nodes)
    return isFinite(mbps) && mbps > 0 ? mbps : undefined
  }, [currentRoute?.path, nodes])

  const rwrComputedLatency = useMemo(() => {
    if (!rwrPath) return undefined
    const ms = metrics.pathLatencyMsForNodes(rwrPath, nodes)
    return isFinite(ms) ? ms : undefined
  }, [rwrPath, nodes])
  const rwrComputedThroughput = useMemo(() => {
    if (!rwrPath) return undefined
    const mbps = metrics.pathThroughputMbpsForNodes(rwrPath, nodes)
    return isFinite(mbps) && mbps > 0 ? mbps : undefined
  }, [rwrPath, nodes])

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-1 space-y-3">
        <div className="bg-slate-900 rounded p-3">
          <div className="font-semibold mb-2">Chọn nguồn/đích</div>
            <div className="flex justify-end mb-2">
              <button onClick={cycleSpeed} className="bg-slate-700 hover:bg-slate-600 text-xs px-2 py-1 rounded">
                {mult === 1 ? '▶︎ 1x' : mult === 10 ? '⏩ 10x' : '⏭ 100x'}
              </button>
            </div>
          <select className="bg-slate-800 rounded px-2 py-1 w-full mb-2" value={src} onChange={e=>setSrc(Number(e.target.value))}>
            <option value="">Chọn src</option>
            {nodes.map(n=> <option key={n.id} value={n.id}>{n.id} - {n.name}</option>)}
          </select>
          <select className="bg-slate-800 rounded px-2 py-1 w-full mb-2" value={dst} onChange={e=>setDst(Number(e.target.value))}>
            <option value="">Chọn dst</option>
            {nodes.map(n=> <option key={n.id} value={n.id}>{n.id} - {n.name}</option>)}
          </select>
          <div className="flex gap-2">
            <button className="bg-sky-600 px-3 py-1 rounded flex-1 disabled:opacity-50" disabled={routeLoading || src==='' || dst===''} onClick={onFind}>
              {routeLoading ? 'Đang tính...' : 'Tìm tuyến (ACO)'}
            </button>
            <button className="bg-amber-500 px-3 py-1 rounded flex-1" onClick={() => { if (src!=='' && dst!=='') { const p = runRWR(Number(src), Number(dst)); setRwrPath(p) } }}>Baseline (RWR)</button>
          </div>
          {routeError && <div className="mt-2 text-xs text-red-400">{routeError}</div>}
          <div className="flex items-center gap-2 mt-2">
            <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={showACO} onChange={e=>setShowACO(e.target.checked)} /> Show ACO</label>
            <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={showRWR} onChange={e=>setShowRWR(e.target.checked)} /> Show RWR</label>
          </div>
        </div>
        <div className="bg-slate-900 rounded p-3">
          <div className="font-semibold mb-2">Metrics</div>
          <div className="text-sm text-slate-300 space-y-1">
            <div className="font-semibold">ACO (server path)</div>
            <div>Latency (server): {fmtMs(currentRoute?.latency_ms)}</div>
            <div>Throughput (server): {fmtMbps(currentRoute?.throughput_mbps)}</div>
            <div className="mt-1">Latency (computed): {fmtMs(acoComputedLatency)}</div>
            <div>Throughput (computed): {fmtMbps(acoComputedThroughput)}</div>
            <div>Cost: {currentRoute?.cost ?? '-'}</div>

            <div className="mt-2 font-semibold">RWR (client baseline)</div>
            <div>Latency (computed): {fmtMs(rwrComputedLatency)}</div>
             <div>Throughput (computed): {fmtMbps(rwrComputedThroughput)}</div> 
          </div>
        </div>
        {currentRoute?.path && !routeError && (
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
        {rwrPath && rwrPath.length > 0 && (
          <div className="bg-slate-900 rounded p-3">
            <div className="font-semibold mb-2">RWR Path (Baseline)</div>
            <ol className="list-decimal list-inside text-sm">
              {rwrPath.map(pid => {
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
