import type { NodeKind, PacketStatus } from './lib/types'

export const earthRadiusKm = 6371

export function altitudeOffset(lat: number, lon: number, alt_m: number | undefined, kind: NodeKind): number {
  const altKm = (alt_m ?? (kind === 'air' ? 10_000 : kind === 'sat' ? 550_000 : 0)) / 1000
  if (kind === 'ground' || kind === 'sea') return earthRadiusKm * 0.005 / earthRadiusKm // ~0.5%
  const km = altKm > 0 ? altKm : (kind === 'air' ? 10 : 550)
  return km / earthRadiusKm
}

export function nodeColor(kind: NodeKind, status?: PacketStatus): string {
  if (status === 'pending') return '#f59e0b'
  if (status === 'success') return '#22c55e'
  switch (kind) {
    case 'ground': return '#60a5fa'
    case 'sea': return '#38bdf8'
    case 'air': return '#f472b6'
    case 'sat': return '#f43f5e'
  }
}

export const fmtMs = (v?: number) => (v == null || !isFinite(v) ? '-' : `${v.toFixed(1)} ms`)
export const fmtMbps = (v?: number) => {
  if (v == null || !isFinite(v)) return '-'
  if (v >= 1) return `${v.toFixed(2)} Mbps`
  const kbps = v * 1000
  if (kbps >= 1) return `${kbps.toFixed(2)} Kbps`
  const bps = v * 1_000_000
  // show a few decimals for very small values
  const precision = bps < 10 ? 3 : bps < 100 ? 2 : 0
  return `${bps.toFixed(precision)} bps`
}
