import type { NodeInfo, LinkInfo, RouteResult, PacketEvent } from './types'

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - vite injects env typing via vite/client
const BASE: string = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8080'
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
const USE_MOCK: boolean = ((import.meta as any).env?.VITE_USE_MOCK || '0') === '1'

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json()
}

export const getNodes = async (): Promise<NodeInfo[]> => j(await fetch(`${BASE}/nodes`))
export const getLinks = async (): Promise<LinkInfo[]> => j(await fetch(`${BASE}/links`))
export const postRoute = async (src: number, dst: number): Promise<RouteResult> =>
  j(await fetch(`${BASE}/route`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ src, dst }) }))

export const toggleLink = async (u: number, v: number, enabled: boolean) =>
  j(await fetch(`${BASE}/simulate/toggle-link`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ u, v, enabled }) }))

export const sendPacket = async (src: number, dst: number, protocol: 'TCP'|'UDP'): Promise<{ sessionId: string }> => {
  if (USE_MOCK) {
    const { mockSendPacket } = await import('./mock/server')
    return mockSendPacket(src, dst, protocol)
  }
  return j(await fetch(`${BASE}/simulate/send-packet`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ src, dst, protocol }) }))
}

export async function openEvents(onEvent: (e: PacketEvent) => void): Promise<() => void> {
  if (USE_MOCK) {
    const { mockOpenEvents } = await import('./mock/server')
    return mockOpenEvents(onEvent)
  }
  const es = new EventSource(`${BASE}/events`)
  es.onmessage = (ev) => {
    try { onEvent(JSON.parse(ev.data)) } catch {}
  }
  return () => es.close()
}
