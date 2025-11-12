import Globe from 'react-globe.gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
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

  // separate ground/sea (render as simple points) from elevated nodes (air/sat)
  const groundPts = useMemo(() => nodes.filter(n => n.kind === 'ground' || n.kind === 'sea').map(n => ({ ...n })), [nodes])
  const elevatedObjs = useMemo(() => nodes.filter(n => n.kind !== 'ground' && n.kind !== 'sea').map(n => ({ ...n })), [nodes])

  return (
    <Globe
      ref={ref}
      width={w}
      height={h}
      backgroundColor="rgba(2,6,23,1)"
      globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
      bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
      pointsData={groundPts}
      pointLat={(d: any) => d.lat}
      pointLng={(d: any) => d.lon}
      // ground/sea points: placed on surface
      pointAltitude={() => 0}
      pointColor={(d: any) => nodeColor(d.kind, statusByNode?.[d.id])}
      pointRadius={0.5}
      // elevated nodes rendered as custom three.js objects so they appear as single spheres
      objectsData={elevatedObjs}
      objectLat={(d: any) => d.lat}
      objectLng={(d: any) => d.lon}
      objectAltitude={(d: any) => altitudeOffset(d.lat, d.lon, d.alt_m, d.kind)}
      objectThreeObject={(d: any) => {
        const color = nodeColor(d.kind, statusByNode?.[d.id])
        const mat = new THREE.MeshStandardMaterial({ color })
        const geo = new THREE.SphereGeometry(0.6, 8, 8)
        const mesh = new THREE.Mesh(geo, mat)
        return mesh
      }}
      onPointHover={(d: any) => onHoverNode?.(d?.id)}
      onObjectHover={(d: any) => onHoverNode?.(d?.id)}
      arcsData={arcs || []}
      arcColor={() => ['#22d3ee', '#38bdf8']}
      arcStroke={1.5}
      animateIn
    />
  )
}
