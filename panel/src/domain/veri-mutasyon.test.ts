/**
 * REGRESYON: `tumKayitlar` store verisini MUTASYONA UĞRATMAMALI.
 *
 * Gerçek hata: kayıt içinde `ilceId` yoksa ağaç anahtarı kayda YAZILIYORDU. Bu fonksiyon store
 * verisiyle de çağrıldığı için derin watcher tetikleniyor, panelin düzenleme TASLAĞI sıfırlanıyordu.
 * Sonuç: kullanıcı alanı düzenliyor, "Kaydet" ESKİ içeriği yazıyor → "değişiklik uygulanmadı".
 */
import { describe, expect, it } from 'vitest'

import { tumKayitlar } from './veri'
import type { SistemVerisi } from './veri'

/** Kayıtlarında ilceId/bolgeId OLMAYAN veri (ağaç anahtarları kimliği taşır). */
function anahtarsiz() {
  return {
    Nobetler: {
      T1: { I1: [{ B1: [{ eczane: 'A', adres: 'eski' }] }] },
    },
  } as unknown as SistemVerisi
}

describe('tumKayitlar mutasyonsuz çalışır', () => {
  it('girdi belgesi DEĞİŞMEZ (deep-equal)', () => {
    const veri = anahtarsiz()
    const onceki = JSON.stringify(veri)
    const kayitlar = tumKayitlar(veri)
    expect(JSON.stringify(veri)).toBe(onceki)
    expect(kayitlar).toHaveLength(1)
    expect(kayitlar[0].adres).toBe('eski')
  })

  it('kimlik gerektiğinde KOPYA döner (girdi kirlenmez)', () => {
    const veri = anahtarsiz()
    const [kayit] = tumKayitlar(veri)
    expect(kayit.ilceId).toBe('I1')
    expect(kayit.bolgeId).toBe('B1')
    // orijinal kayıt hâlâ kimliksiz → mutasyon yok
    const ham = veri as unknown as {
      Nobetler: { T1: { I1: Array<{ B1: Array<Record<string, unknown>> }> } }
    }
    expect(ham.Nobetler.T1.I1[0].B1[0].ilceId).toBeUndefined()
  })

  it('kimliği olan kayıt AYNI referansla döner (gereksiz kopya yok)', () => {
    const kayit = { eczane: 'A', ilceId: 'I1', bolgeId: 'B1' }
    const veri = { Nobetler: { T1: { I1: [{ B1: [kayit] }] } } } as unknown as SistemVerisi
    expect(tumKayitlar(veri)[0]).toBe(kayit)
  })
})
