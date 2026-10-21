/** Okuma planı: boş kovada 404 üretilmemeli, dolu kovada tüm dosyalar okunmalı. */
import { describe, expect, it } from 'vitest'

import { okumaPlani } from './dosyaSecimi'

describe('okumaPlani', () => {
  it('boş kovada hiçbir dosyayı okumaya çalışmaz (404 yağmuru yok)', () => {
    const plan = okumaPlani([], 'kiosk/')
    expect(plan.length).toBeGreaterThan(0)
    expect(plan.every((k) => k.varMi === false)).toBe(true)
  })

  it('yalnız kovada bulunan dosyaları okur', () => {
    const plan = okumaPlani(['kiosk/ayarlar.json', 'kiosk/lastupdate.json', 'kiosk/yayin-gorselleri/x.jpg'], 'kiosk/')
    const varOlan = plan.filter((k) => k.varMi).map((k) => k.ad).sort()
    expect(varOlan).toEqual(['ayarlar.json', 'lastupdate.json'])
  })

  it('liste alınamadıysa (null) tüm dosyaları dener — eski davranış korunur', () => {
    const plan = okumaPlani(null, 'kiosk/')
    expect(plan.every((k) => k.varMi)).toBe(true)
  })

  it('ön eki normalize eder: `kiosk` ile `kiosk/` aynı sonucu verir', () => {
    const anahtarlar = ['kiosk/ayarlar.json']
    expect(okumaPlani(anahtarlar, 'kiosk')).toEqual(okumaPlani(anahtarlar, 'kiosk/'))
  })
})
