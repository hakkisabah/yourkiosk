/**
 * UÇTAN UCA (gerçek Vuetify bileşeni): nöbet kaydını düzenle → Kaydet → S3'e giden içerik
 * düzenlemeyi İÇERMELİ.
 *
 * Bu test "kaydettim ama değişmedi" sınıfını gerçek bileşenle kilitler (stub yok).
 */
// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createVuetify } from 'vuetify'
import { beforeEach, describe, expect, it, vi } from 'vitest'

class SahteResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = SahteResizeObserver
;(globalThis as unknown as { matchMedia: unknown }).matchMedia = () => ({
  matches: false,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
})

const yazilanlar: Array<{ ad: string; veri: unknown }> = []
const DEPO: Record<string, unknown> = {}

vi.mock('@/stores/baglanti', () => ({
  useBaglanti: () => ({
    kaynak: {
      yaz: async (ad: string, veri: unknown) => {
        yazilanlar.push({ ad, veri })
        DEPO[ad] = JSON.parse(JSON.stringify(veri))
        return { etag: `e${yazilanlar.length}`, anahtar: `kiosk/${ad}` }
      },
      oku: async (ad: string) => ({ veri: DEPO[ad] ?? null, etag: 'e' }),
      liste: async () => [],
      silDesteklenir: true,
    },
    kova: 'test-kova',
    onEk: 'kiosk/',
    baglanti: { hataAyikla: (e: unknown) => String(e) },
    yapilandirmaHatasi: null,
  }),
}))
vi.mock('@/domain/push', () => ({ mqttBildir: vi.fn(async () => ({ gonderildi: true })) }))

import VeriView from '@/views/VeriView.vue'
import { useDosyalar } from '@/stores/dosyalar'

const VERI = {
  Nobetler: {
    T20261024: {
      I1: [
        {
          B1: [
            {
              eczane: 'SEYMEN AKSA',
              tel: '123',
              adres: 'ESKİ ADRES',
              adres_tarifi: '',
              start: '2026-10-24T08:30:00',
              end: '2026-10-24T23:59:00',
              ilce: 'BAŞİSKELE',
              ilceId: 'I1',
              bolge: 'Başiskele',
              bolgeId: 'B1',
            },
          ],
        },
      ],
    },
  },
}

interface Kayit {
  adres: string
}
type Kayitlar = {
  Nobetler: { T20261024: { I1: Array<Record<string, Kayit[]>> } }
}

describe('VeriView: düzenle → kaydet', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    yazilanlar.length = 0
    for (const k of Object.keys(DEPO)) delete DEPO[k]
    const d = useDosyalar()
    d.sistem.veri = JSON.parse(JSON.stringify(VERI))
    d.sistem.yuklendi = true
    DEPO['lastSystemData.json'] = JSON.parse(JSON.stringify(VERI))
  })

  it('düzenlenen adres S3 payload’ında bulunur', async () => {
    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 20))

    const girdiler = wrapper.findAll('input')
    const adres = girdiler.find(
      (g: { element: Element }) => (g.element as HTMLInputElement).value === 'ESKİ ADRES',
    )
    expect(adres, 'adres alanı bulunamadı (input değerleri farklı)').toBeTruthy()

    await adres!.setValue('YENİ ADRES')
    await wrapper.vm.$nextTick()

    const kaydet = wrapper.findAll('button').find((b: { text: () => string }) =>
      (b.text() ?? '').includes('Kaydet'),
    )
    expect(kaydet, 'Kaydet düğmesi yok').toBeTruthy()
    await kaydet!.trigger('click')
    await new Promise((r) => setTimeout(r, 60))

    const gonderilen = yazilanlar.find((y) => y.ad === 'lastSystemData.json')
    expect(gonderilen, 'sistem verisi yazılmadı').toBeTruthy()
    const kayit: Kayit = (gonderilen!.veri as Kayitlar).Nobetler.T20261024.I1[0].B1[0]
    expect(kayit.adres, 'DÜZENLEME KAYBOLDU (kaydedilen içerikte yok)').toBe('YENİ ADRES')
    wrapper.unmount()
  })
})
