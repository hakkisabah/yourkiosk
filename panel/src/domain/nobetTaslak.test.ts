/**
 * Nöbet taslağı kuralları (saf) — "kaydettim ama değişmedi" sınıfını kilitler.
 *
 * Kurallar `VeriView.kaydet()` içinde gömülüyken test edilemiyordu; gerçek olayda panel
 * ESKİ içeriği yazdı ve kullanıcı değişikliğin uygulanmadığını gördü.
 */
import { describe, expect, it } from 'vitest'

import { bozukKayitVar, kaydaHazirla, kirliMi, yazmaDogrulandiMi } from './nobetTaslak'

const DOLU = [
  { eczane: 'A', start: '2026-10-24T08:30:00', end: '2026-10-24T23:59:00' },
  { eczane: 'B', start: '2026-10-24T08:30:00', end: '2026-10-24T23:59:00' },
]

describe('bozukKayitVar', () => {
  it('start/end doluysa sorun yok', () => {
    expect(bozukKayitVar(DOLU)).toBe(false)
  })

  it('boş start yakalanır', () => {
    expect(bozukKayitVar([{ start: '  ', end: '2026-10-24T23:59:00' }])).toBe(true)
  })

  it('eksik end yakalanır', () => {
    expect(bozukKayitVar([{ start: '2026-10-24T08:30:00' }])).toBe(true)
  })
})

describe('kirliMi', () => {
  it('aynı içerik → temiz', () => {
    expect(kirliMi({ a: 1 }, { a: 1 })).toBe(false)
  })

  it('farklı içerik → kirli', () => {
    expect(kirliMi({ a: 1 }, { a: 2 })).toBe(true)
  })

  it('boş/undefined güvenli', () => {
    expect(kirliMi(null, undefined)).toBe(false)
    expect(kirliMi({}, null)).toBe(false)
  })
})

describe('kaydaHazirla', () => {
  const kaynak = { Nobetler: { T1: { I1: [{ B1: [DOLU[0]] }] } } }
  const kopya = JSON.parse(JSON.stringify(kaynak))

  it('değişiklik yoksa YAZMAZ ve nedenini söyler', () => {
    const karar = kaydaHazirla(kopya, kaynak, DOLU)
    expect(karar.yazilsin).toBe(false)
    expect(karar.mesaj).toContain('değişiklik yok')
  })

  it('bozuk kayıt varsa YAZMAZ', () => {
    const karar = kaydaHazirla(kopya, kaynak, [{ start: '', end: 'x' }])
    expect(karar.yazilsin).toBe(false)
    expect(karar.mesaj).toContain('başlangıç')
  })

  it('değişiklik varsa YAZAR', () => {
    const taslak = JSON.parse(JSON.stringify(kaynak))
    taslak.Nobetler.T1.I1[0].B1[0].adres = 'YENİ'
    const karar = kaydaHazirla(taslak, kaynak, DOLU)
    expect(karar.yazilsin).toBe(true)
    expect(karar.mesaj).toBe('')
  })
})

describe('yazmaDogrulandiMi', () => {
  it('gönderilen = geri okunan', () => {
    expect(yazmaDogrulandiMi({ a: [1, 2] }, { a: [1, 2] })).toBe(true)
  })

  it('farklıysa false (sessiz uyuşmazlık yakalanır)', () => {
    expect(yazmaDogrulandiMi({ a: 1 }, { a: 2 })).toBe(false)
    expect(yazmaDogrulandiMi({ a: 1 }, null)).toBe(false)
  })
})
