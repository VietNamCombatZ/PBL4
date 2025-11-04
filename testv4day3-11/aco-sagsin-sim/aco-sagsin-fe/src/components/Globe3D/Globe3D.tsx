import Globe from 'react-globe.gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { NodeInfo, PacketStatus } from '../../lib/types'
import { altitudeOffset, nodeColor } from '../../utils'

type Arc = { startLat: number; startLng: number; endLat: number; endLng: number }

export default function Globe3D({ nodes, arcs, hoverNodeId, onHoverNode, statusByNode }: {
  nodes: NodeInfo[]
  arcs?: Arc[]
  hoverNodeId?: number
  onHoverNode?: (id?: number) => void
  statusByNode?: Record<number, PacketStatus>
}) {
  const ref = useRef<any>(null)
  const [w, setW] = useState<number>(window.innerWidth)
  const [h, setH] = useState<number>(600)
  useEffect(() => {
    const onR = () => { setW(window.innerWidth); setH(window.innerHeight - 140) }
    window.addEventListener('resize', onR)
    onR(); return () => window.removeEventListener('resize', onR)
  }, [])

  const pts = useMemo(() => nodes.map(n => ({ ...n })), [nodes])

  return (
    <Globe
      ref={ref}
      width={w}
      height={h}
      backgroundColor="rgba(2,6,23,1)"
      globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
      bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
      pointsData={pts}
      pointLat={(d: any) => d.lat}
      pointLng={(d: any) => d.lon}
  // Render all nodes as surface dots (no vertical pillars), regardless of their real altitude
  pointAltitude={(d: any) => 0}
      pointColor={(d: any) => nodeColor(d.kind, statusByNode?.[d.id])}
      pointRadius={0.5}
      onPointHover={(d: any) => onHoverNode?.(d?.id)}
      arcsData={arcs || []}
      arcColor={() => ['#22d3ee', '#38bdf8']}
      arcStroke={1.5}
      animateIn
    />
  )
}
