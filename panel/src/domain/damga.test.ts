/**
 * Damga (`lastupdate`) biçim doğrulaması ve "en yeni" seçimi.
 *
 * GERÇEK BULGU (i5, PR #78): damga seçimi düz sözlüksel karşılaştırmaydı ve biçim doğrulanmıyordu.
 * Sunucudan nesne gelse `String()` → `"[object Object]"` olur ve `"[" > "2"` olduğu için bellekteki
 * GEÇERLİ damga ezilir → `durum.json`a çöp yazılır.
 */
import { describe, expect, it } from 'vitest'

import { damgaMetni, enYeniDamga } from './damga'

describe('damgaMetni', () => {
  it('panel biçimini ve ISO biçimini kabul eder', () => {
    expect(damgaMetni('2026-10-24 10:30:00')).toBe('2026-10-24 10:30:00')
    expect(damgaMetni('2026-10-24T10:30:00Z')).toBe('2026-10-24T10:30:00Z')
    expect(damgaMetni('  2026-10-24 10:30:00  ')).toBe('2026-10-24 10:30:00')
  })

  it('nesne/sayı/boş/biçimsiz değerleri reddeder', () => {
    expect(damgaMetni({ lastupdate: '2026-10-24 10:30:00' })).toBe('')
    expect(damgaMetni(123)).toBe('')
    expect(damgaMetni('')).toBe('')
    expect(damgaMetni(null)).toBe('')
    expect(damgaMetni(undefined)).toBe('')
    expect(damgaMetni('[object Object]')).toBe('')
    expect(damgaMetni('dün')).toBe('')
  })
})

describe('enYeniDamga', () => {
  it('iki geçerli damgadan YENİ olanı seçer', () => {
    expect(enYeniDamga('2026-10-24 09:00:00', '2026-10-24 10:30:00')).toBe('2026-10-24 10:30:00')
    // sıra önemsiz
    expect(enYeniDamga('2026-10-24 10:30:00', '2026-10-24 09:00:00')).toBe('2026-10-24 10:30:00')
  })

  it('çöp değer geçerli damgayı EZMEZ (regresyon)', () => {
    expect(enYeniDamga('2026-10-24 09:00:00', { x: 1 })).toBe('2026-10-24 09:00:00')
    expect(enYeniDamga('2026-10-24 09:00:00', '[object Object]')).toBe('2026-10-24 09:00:00')
    expect(enYeniDamga('2026-10-24 09:00:00', '')).toBe('2026-10-24 09:00:00')
  })

  it('hiç geçerli damga yoksa boş döner', () => {
    expect(enYeniDamga(null, undefined, {}, 'yok')).toBe('')
    expect(enYeniDamga()).toBe('')
  })
})
