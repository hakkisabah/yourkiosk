/** Derin kopya: reactive Proxy'ler klonlanabilmeli (structuredClone DataCloneError atıyordu). */
import { reactive } from 'vue'
import { describe, expect, it } from 'vitest'

import { kopya } from './kopya'

describe('kopya', () => {
  it('reactive Proxy’yi klonlar (structuredClone burada patlıyordu)', () => {
    const kaynak = reactive({ veri: { a: 1, liste: [1, 2] } })
    expect(() => structuredClone(kaynak)).toThrow()
    const k = kopya(kaynak)
    expect(k).toEqual({ veri: { a: 1, liste: [1, 2] } })
  })

  it('kopya bağımsızdır: kopyayı değiştirmek kaynağı etkilemez', () => {
    const kaynak = reactive({ a: { b: 1 } })
    const k = kopya(kaynak)
    k.a.b = 99
    expect(kaynak.a.b).toBe(1)
  })

  it('undefined/null olduğu gibi döner', () => {
    expect(kopya(undefined)).toBeUndefined()
    expect(kopya(null)).toBeNull()
  })
})
