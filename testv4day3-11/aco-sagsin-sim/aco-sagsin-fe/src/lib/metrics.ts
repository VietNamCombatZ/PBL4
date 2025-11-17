// Metrics helpers ported/adapted from aco_formulas.txt (lightweight TS version)
// Provides functions to compute link throughput and path latency using
// reasonable default RF parameters. All distances are meters, rates in bps.

const C_LIGHT_MPS = 299_792_458.0

export function deg2rad(d: number) { return d * Math.PI / 180.0 }

export function greatCircleDistanceM(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6_371_000.0
  const φ1 = deg2rad(lat1)
  const φ2 = deg2rad(lat2)
  const dφ = deg2rad(lat2 - lat1)
  const dλ = deg2rad(lon2 - lon1)
  const a = Math.sin(dφ/2)**2 + Math.cos(φ1)*Math.cos(φ2)*Math.sin(dλ/2)**2
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a))
  return R * c
}

export function slantRangeM(lat1: number, lon1: number, alt1m: number|undefined, lat2: number, lon2: number, alt2m: number|undefined) {
  // conservative fallback: use alt=0 when missing
  const a1 = alt1m ?? 0
  const a2 = alt2m ?? 0
  // convert to ECEF vectors
  const R = 6_371_000.0
  const toEcef = (lat: number, lon: number, alt: number) => {
    const φ = deg2rad(lat)
    const λ = deg2rad(lon)
    const r = R + alt
    const x = r * Math.cos(φ) * Math.cos(λ)
    const y = r * Math.cos(φ) * Math.sin(λ)
    const z = r * Math.sin(φ)
    return [x,y,z]
  }
  const [x1,y1,z1] = toEcef(lat1, lon1, a1)
  const [x2,y2,z2] = toEcef(lat2, lon2, a2)
  const dx = x1 - x2, dy = y1 - y2, dz = z1 - z2
  return Math.sqrt(dx*dx + dy*dy + dz*dz)
}

export function fsplDbKmGhz(d_km: number, f_ghz: number) {
  if (d_km <= 0 || f_ghz <= 0) return 0
  return 20.0 * Math.log10(d_km) + 20.0 * Math.log10(f_ghz) + 92.45
}

export function thermalNoiseDbm(bw_hz: number, noiseFigureDb = 5.0, t0_dbmhz = -174.0) {
  if (bw_hz <= 0) return -Infinity
  return t0_dbmhz + 10.0 * Math.log10(bw_hz) + noiseFigureDb
}

export function snrDb(pr_dbm: number, n_dbm: number) { return pr_dbm - n_dbm }
export function dbToLinear(db: number) { return Math.pow(10, db/10) }

export function shannonCapacityBps(bw_hz: number, snr_linear: number) {
  if (bw_hz <= 0) return 0
  return bw_hz * Math.log2(1 + Math.max(0, snr_linear))
}

export function linkThroughputBpsFromBudget(d_m: number, // distance
  f_ghz = 2.4, bw_hz = 1e6, pt_dbm = 30, gt_dbi = 0, gr_dbi = 0, nf_db = 5,
  phy_eff = 0.8, mac_eff = 0.9, code_rate = 0.9) {
  // simple budget -> throughput
  const d_km = Math.max(1e-6, d_m/1000.0)
  const fspl = fsplDbKmGhz(d_km, f_ghz)
  const pr_dbm = pt_dbm + gt_dbi + gr_dbi - fspl
  const n_dbm = thermalNoiseDbm(bw_hz, nf_db)
  const snr = pr_dbm - n_dbm
  const snr_lin = dbToLinear(snr)
  const c = shannonCapacityBps(bw_hz, snr_lin)
  const eff = Math.max(0, phy_eff) * Math.max(0, mac_eff) * Math.max(0, code_rate)
  return Math.max(0, eff * c)
}

export function transmissionDelayMs(packetBytes: number, rate_bps: number) {
  const bits = packetBytes * 8
  if (rate_bps <= 0) return Infinity
  return (bits / rate_bps) * 1000.0
}

export function propagationDelayMs(distance_m: number, speed_mps = C_LIGHT_MPS) {
  return distance_m / speed_mps * 1000.0
}

export function hopLatencyMs(packetBytes: number, rate_bps: number, distance_m: number, proc_ms = 1.0, queue_ms = 0.0) {
  return transmissionDelayMs(packetBytes, rate_bps) + propagationDelayMs(distance_m) + Math.max(0, proc_ms) + Math.max(0, queue_ms)
}

export function pathLatencyMsForNodes(path: number[], nodes: { id:number, lat:number, lon:number, alt_m?: number }[], packetBytes = 1500, // default MTU
  // link params
  f_ghz = 2.4, bw_hz = 1e6, pt_dbm = 30, gt_dbi = 0, gr_dbi = 0, nf_db = 5) {
  if (!path || path.length < 2) return 0
  let total = 0
  for (let i=0;i<path.length-1;i++){
    const a = nodes.find(n=>n.id===path[i])
    const b = nodes.find(n=>n.id===path[i+1])
    if (!a || !b) continue
    const d = slantRangeM(a.lat, a.lon, a.alt_m, b.lat, b.lon, b.alt_m)
    const linkCap = linkThroughputBpsFromBudget(d, f_ghz, bw_hz, pt_dbm, gt_dbi, gr_dbi, nf_db)
    // transmission delay uses link capacity
    total += hopLatencyMs(packetBytes, Math.max(1, linkCap), d)
  }
  return total
}

export function pathThroughputMbpsForNodes(path: number[], nodes: { id:number, lat:number, lon:number, alt_m?: number }[], packetBytes = 1500,
  f_ghz = 2.4, bw_hz = 1e6, pt_dbm = 30, gt_dbi = 0, gr_dbi = 0, nf_db = 5) {
  if (!path || path.length < 2) return 0
  const perLink: number[] = []
  for (let i=0;i<path.length-1;i++){
    const a = nodes.find(n=>n.id===path[i])
    const b = nodes.find(n=>n.id===path[i+1])
    if (!a || !b) continue
    const d = slantRangeM(a.lat, a.lon, a.alt_m, b.lat, b.lon, b.alt_m)
    const cap = linkThroughputBpsFromBudget(d, f_ghz, bw_hz, pt_dbm, gt_dbi, gr_dbi, nf_db)
    perLink.push(cap)
  }
  if (perLink.length === 0) return 0
  const pathBps = Math.min(...perLink)
  return pathBps / 1e6
}

export default {
  pathLatencyMsForNodes,
  pathThroughputMbpsForNodes,
}
