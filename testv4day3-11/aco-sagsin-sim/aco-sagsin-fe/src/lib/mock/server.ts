import type { PacketEvent } from '../types'

export async function mockSendPacket(_src: number, _dst: number, _protocol: 'TCP'|'UDP') {
  return { sessionId: Math.random().toString(36).slice(2) }
}

export async function mockOpenEvents(onEvent: (e: PacketEvent) => void) {
  const timers = new Set<number>()
  // emit random progress for demo
  const t = setInterval(() => {
    const e: PacketEvent = {
      type: 'packet-progress',
      sessionId: 'mock',
      nodeId: Math.floor(Math.random() * 10),
      status: Math.random() > 0.5 ? 'pending' : 'success',
      arrived_ms: Math.random() * 10,
      cumulative_latency_ms: Math.random() * 1000,
    }
    onEvent(e)
  }, 1000)
  timers.add(t as unknown as number)
  return () => { timers.forEach((tt) => clearInterval(tt)); timers.clear() }
}
