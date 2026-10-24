/**
 * REGRESYON: `DOSYALAR` (dosya adları) ile store STATE anahtarları ayrışmamalı.
 *
 * Gerçek hata: `DOSYALAR.durum` eklendi ama state'e karşılığı konmadı →
 * `hepsiniYukle` `this['durum'].veri = null` yazdı →
 * "Cannot set properties of undefined (setting 'veri')" ve panel açılışta bozuldu.
 *
 * Bu test iki tarafın birebir eşleştiğini kilitler; yeni dosya eklenince state de eklenmek zorunda.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DOSYALAR } from '@/aws/config'

const yazilanlar: Array<{ ad: string; veri: unknown }> = []
const okunanlar: string[] = []

vi.mock('./baglanti', () => ({
  useBaglanti: () => ({
    kaynak: {
      yaz: async (ad: string, veri: unknown) => {
        yazilanlar.push({ ad, veri })
        return { etag: `e${yazilanlar.length}`, anahtar: `kiosk/${ad}` }
      },
      oku: async (ad: string) => {
        okunanlar.push(ad)
        return { veri: { örnek: true }, etag: 'e0' }
      },
      liste: async () => Object.values(DOSYALAR).map((ad) => ({ anahtar: `kiosk/${ad}` })),
      silDesteklenir: true,
    },
    onEk: 'kiosk/',
    kova: 'test-kova',
    hataAyikla: (hata: unknown) => String(hata),
  }),
}))

vi.mock('@/domain/push', () => ({ mqttBildir: vi.fn(async () => ({ gonderildi: true })) }))

import { useDosyalar } from './dosyalar'

describe('DOSYALAR ↔ store state tutarlılığı', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    yazilanlar.length = 0
    okunanlar.length = 0
  })

  it('DOSYALAR içindeki HER anahtar store state içinde tanımlı', () => {
    const d = useDosyalar()
    for (const anahtar of Object.keys(DOSYALAR)) {
      expect(d.$state, `state'te '${anahtar}' yok — DOSYALAR ile eşleşmiyor`).toHaveProperty(anahtar)
      expect((d.$state as unknown as Record<string, unknown>)[anahtar]).toMatchObject({ yuklendi: false })
    }
  })

  it('hepsiniYukle undefined state anahtarına yazmaya çalışmaz', async () => {
    const d = useDosyalar()
    await expect(d.hepsiniYukle()).resolves.toBeUndefined()
    expect(d.sonUyari).toBeNull()
  })

  it('durum.json panelde OKUNMAZ (cihaz tüketir), yazılır', async () => {
    const d = useDosyalar()
    await d.hepsiniYukle()
    expect(okunanlar).not.toContain(DOSYALAR.durum)

    await d.kaydet('sistem', DOSYALAR.sistem, { Nobetler: {} })
    const adlar = yazilanlar.map((y) => y.ad)
    expect(adlar).toContain(DOSYALAR.durum)
  })

  it('kaydet: lastupdate + durum.json AYNI damgayı taşır', async () => {
    const d = useDosyalar()
    await d.kaydet('sistem', DOSYALAR.sistem, { Nobetler: {} })
    const damga = yazilanlar.find((y) => y.ad === DOSYALAR.lastupdate)?.veri as Record<string, unknown>
    const durum = yazilanlar.find((y) => y.ad === DOSYALAR.durum)?.veri as Record<string, unknown>
    expect(durum.lastupdate).toBe(damga.lastupdate)
    expect(durum.tetik).toMatchObject({ ilceId: '' })
  })
})
