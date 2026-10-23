/**
 * Regresyon: panel bir veri dosyasını kaydedince `lastupdate.json` damgası da tazelenmeli.
 *
 * NEDEN: cihaz yoklaması damgayı karşılaştırır (`lastupdate`). Damga değişmezse cihaz "veri aynı"
 * sanıp ÖNBELLEKTEN eski gövdeyi gösterir; MQTT/push ulaşmadığında güncelleme hiç görünmez.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const yazilanlar: Array<{ ad: string; veri: unknown }> = []

vi.mock('./baglanti', () => ({
  useBaglanti: () => ({
    kaynak: {
      yaz: async (ad: string, veri: unknown) => {
        yazilanlar.push({ ad, veri })
        return { etag: `etag-${yazilanlar.length}`, anahtar: `kiosk/${ad}` }
      },
      silDesteklenir: true,
    },
    hataAyikla: (hata: unknown) => String(hata),
  }),
}))

vi.mock('@/domain/push', () => ({ mqttBildir: vi.fn(async () => ({ gonderildi: true })) }))

import { useDosyalar } from './dosyalar'

describe('kaydet → lastupdate damgası', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    yazilanlar.length = 0
  })

  it('sistem verisi kaydından sonra lastupdate.json ve tetikle.json yazılır', async () => {
    const d = useDosyalar()
    const oldu = await d.kaydet('sistem', 'lastSystemData.json', { Nobetler: {} })
    expect(oldu).toBe(true)

    const adlar = yazilanlar.map((y) => y.ad)
    expect(adlar).toContain('lastSystemData.json')
    expect(adlar).toContain('lastupdate.json')
    expect(adlar).toContain('tetikle.json')

    const damga = yazilanlar.find((y) => y.ad === 'lastupdate.json')?.veri as Record<string, unknown>
    expect(String(damga.lastupdate ?? '')).not.toBe('')
  })

  it('cihazın tüketmediği dosya (makinebilgileri) damga/tetik üretmez', async () => {
    const d = useDosyalar()
    await d.kaydet('makine', 'makinebilgileri.json', { clientID: '1' })
    const adlar = yazilanlar.map((y) => y.ad)
    expect(adlar).toEqual(['makinebilgileri.json'])
  })
})
