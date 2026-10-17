/**
 * Kayan yazı kuşağı testleri — Qt `core/ticker.py` + `utils.format_phone` ile birebir.
 */
import { describe, expect, it } from 'vitest'

import {
  formatTelefon,
  ikincilMetin,
  inOutCubic,
  kusakMetni,
  kusakOgeleri,
  kusakX,
  KusakAnimasyonu,
} from '@/veri/kusak'

describe('formatTelefon (Qt utils.format_phone)', () => {
  it('11 haneyi gruplayarak yazar', () => {
    expect(formatTelefon('02623251335')).toBe('0262 325 13 35')
    expect(formatTelefon('0262 325 13 35')).toBe('0262 325 13 35')
  })

  it('10 hanenin başına 0 ekler', () => {
    expect(formatTelefon('2623251335')).toBe('0262 325 13 35')
  })

  it('boş/geçersiz değeri olduğu gibi döner', () => {
    expect(formatTelefon('')).toBe('-')
    expect(formatTelefon(null)).toBe('-')
    expect(formatTelefon('bilinmiyor')).toBe('bilinmiyor')
    expect(formatTelefon('123')).toBe('123')
  })
})

describe('kuşak metni', () => {
  const kayitlar = [
    { eczane: 'Deva', tel: '02623251335', bolge: 'Çayırova 2.Bölge' },
    { eczane: 'aslı eczanesi', tel: '', bolge: 'Çayırova 1.Bölge' },
  ]

  it('öğeleri "ECZANE - TELEFON" biçiminde üretir (ad büyük harf)', () => {
    expect(kusakOgeleri(kayitlar)).toEqual(['DEVA - 0262 325 13 35', 'ASLI ECZANESI - Çayırova 1.Bölge'])
  })

  it('telefon yoksa bölge adına düşer; bu kapalıysa "-" yazar', () => {
    expect(ikincilMetin({ tel: '' }, { eksikTelefonYerineBolge: false })).toBe('-')
    expect(ikincilMetin({ tel: '', bolge: 'B1' })).toBe('B1')
  })

  it('kayıt yoksa tek öğe "-"', () => {
    expect(kusakOgeleri([])).toEqual(['-'])
  })

  it('tekli modda tek öğe, listeli modda ayırıcıyla birleşir', () => {
    expect(kusakMetni(['A', 'B'], true, '    |   ')).toBe('A')
    expect(kusakMetni(['A', 'B'], false, '    |   ')).toBe('        A    |   B        ')
  })
})

describe('konum formülü ve faz makinesi', () => {
  it('oran 0 → sağ kenarda (görünmez), 0.5 → ortada, 1 → tamamen solda', () => {
    expect(kusakX(1920, 400, 0)).toBe(1920)
    expect(kusakX(1920, 400, 0.5)).toBe(Math.round(1920 - 0.5 * 2320))
    expect(kusakX(1920, 400, 1)).toBe(-400)
  })

  it('inOutCubic Qt ile aynı eğri', () => {
    expect(inOutCubic(0)).toBe(0)
    expect(inOutCubic(0.5)).toBe(0.5)
    expect(inOutCubic(1)).toBe(1)
    expect(inOutCubic(0.25)).toBeCloseTo(0.0625, 6)
  })

  it('faz sırası: giriş → durma → çıkış, sonra döngü tamamlanır', () => {
    const a = new KusakAnimasyonu(1200, 3000, 1200, 30) // 40 + 100 + 40 = 180 adım
    expect(a.toplamAdim).toBe(180)

    a.adim()
    expect(a.oran()).toBeGreaterThan(0) // giriş başladı
    expect(a.oran()).toBeLessThan(0.5)

    for (let i = 0; i < 39; i += 1) a.adim()
    expect(a.oran()).toBeCloseTo(0.5, 3) // giriş bitti → durma evresinin başı

    for (let i = 0; i < 100; i += 1) a.adim()
    expect(a.oran()).toBe(0.5) // durma evresi

    let tamamlandi = false
    for (let i = 0; i < 41; i += 1) tamamlandi = a.adim() || tamamlandi
    expect(tamamlandi).toBe(true) // döngü tamamlandı (adım 0'a döndü)
  })

  it('sıfırlama sayaçları temizler', () => {
    const a = new KusakAnimasyonu(300, 300, 300, 30)
    a.adim()
    a.sifirla()
    expect(a.oran()).toBe(0)
    expect(a.donguTamamlandi).toBe(false)
  })
})
