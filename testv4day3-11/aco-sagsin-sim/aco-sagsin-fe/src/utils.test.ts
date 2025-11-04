import { describe, it, expect } from 'vitest'
import { altitudeOffset } from './utils'

describe('altitudeOffset', () => {
  it('uses defaults for air and sat', () => {
    expect(altitudeOffset(0,0,undefined,'air')).toBeGreaterThan(0)
    expect(altitudeOffset(0,0,undefined,'sat')).toBeGreaterThan(0)
  })
  it('ground is tiny offset', () => {
    expect(altitudeOffset(0,0,0,'ground')).toBeLessThan(0.01)
  })
})
