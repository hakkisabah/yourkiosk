/**
 * UÇTAN UCA (gerçek Vuetify bileşeni): Yayınlar sekmesinde GÖRSEL ADRESİ düzenlenebilmeli.
 *
 * NEDEN: kullanıcı "Yayınlar sekmesinde giriş yapabileceğim/değiştirebileceğim bir alan yok"
 * dedi — alan salt-okunur metindi. Bu test gerçek bileşenle akışı kilitler:
 * Görsel düğmesi → adres yaz → Uygula → Kaydet → S3'e giden içerikte YENİ adres olmalı.
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
// Vuetify v-overlay (v-dialog) jsdom'da `visualViewport` arıyor; yoksa diyalog açılışında
// ReferenceError atıp içerik hiç render edilmiyor.
;(globalThis as unknown as { visualViewport: unknown }).visualViewport = {
  width: 1024,
  height: 768,
  offsetTop: 0,
  offsetLeft: 0,
  scale: 1,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
}

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

const ESKI = 'https://ornek.test/yayin-gorselleri/eski.png'
const YENI = 'https://d2dnrvsx5eevod.cloudfront.net/yayin-gorselleri/1aef5f57384bad53.webp'

const VERI = {
  Nobetler: {},
  Yayinlar: {
    T20261024: {
      start: '2026-10-24T08:30:00',
      end: '2026-10-30T23:59:00',
      contentUrl: ESKI,
      duration: 15,
    },
  },
}

function dugme(metin: string): HTMLElement | undefined {
  const hepsi = Array.from(document.querySelectorAll('button'))
  return hepsi.find((b) => (b.textContent ?? '').includes(metin))
}

async function bekle(ms = 30): Promise<void> {
  await new Promise((r) => setTimeout(r, ms))
}

describe('VeriView: yayın görseli düzenle → kaydet', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    yazilanlar.length = 0
    for (const k of Object.keys(DEPO)) delete DEPO[k]
    const d = useDosyalar()
    d.sistem.veri = JSON.parse(JSON.stringify(VERI))
    d.sistem.yuklendi = true
    DEPO['lastSystemData.json'] = JSON.parse(JSON.stringify(VERI))
    document.body.innerHTML = ''
  })

  it('Yayınlar sekmesinde Görsel düğmesi var ve yeni adres kaydediliyor', async () => {
    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await bekle(20)

    // 1) Yayınlar sekmesine geç
    const sekme = dugme('Yayınlar')
    expect(sekme, 'Yayınlar sekmesi bulunamadı').toBeTruthy()
    sekme!.click()
    await bekle(30)

    // 2) Satırdaki Görsel düğmesi (salt-okunur metin değil, düzenleme girişi)
    const gorselDugme = dugme('Görsel')
    expect(gorselDugme, 'Yayınlar sekmesinde Görsel düğmesi YOK (alan düzenlenemiyor)').toBeTruthy()
    const butonlar = wrapper.findAll('button')
    const vt = butonlar.find((b) => (b.text() ?? '').includes('Görsel'))
    expect(vt, 'Görsel düğmesi VTU üzerinden bulunamadı').toBeTruthy()
    await vt!.trigger('click')
    await bekle(120)
    expect(
      String(document.body.textContent),
      'diyalog açılmadı · durum=' + JSON.stringify((wrapper.vm as unknown as { gorselDuzenlenen?: string }).gorselDuzenlenen),
    ).toContain('Yayın görseli')

    // 3) Diyalogdaki metin alanı eski adresle dolu gelmeli
    // NOT: v-dialog içeriği body'ye TELEPORT edilir → `wrapper.findAll` görmez, `document` görür.
    const girdiler = (): HTMLInputElement[] => Array.from(document.querySelectorAll('input'))
    const girdi = girdiler().find((i) => i.value === ESKI)
    expect(
      girdi,
      'görsel adresi alanı eski adresle dolmadı · inputlar=' +
        JSON.stringify(girdiler().map((i) => ({ v: i.value, p: i.placeholder }))),
    ).toBeTruthy()

    // 4) Yeni adresi yaz (v-model `input` olayını dinler)
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    setter.call(girdi, YENI)
    girdi!.dispatchEvent(new Event('input', { bubbles: true }))
    await bekle(20)

    // 5) Uygula → taslağa yazılır
    const uygula = dugme('Uygula')
    expect(uygula, 'Uygula düğmesi yok').toBeTruthy()
    uygula!.click()
    await bekle(60)

    // 6) Sayfadaki Kaydet → S3 payload'ı
    const kaydet = Array.from(wrapper.findAll('button')).find((b) => (b.text() ?? '').includes('Kaydet'))
    expect(kaydet, 'Kaydet düğmesi yok').toBeTruthy()
    await kaydet!.trigger('click')
    await bekle(80)

    const gonderilen = yazilanlar.find((y) => y.ad === 'lastSystemData.json')
    expect(gonderilen, 'sistem verisi yazılmadı').toBeTruthy()
    const yayin = (gonderilen!.veri as { Yayinlar: Record<string, { contentUrl?: string }> }).Yayinlar.T20261024
    expect(yayin.contentUrl, 'GÖRSEL ADRESİ KAYBOLDU (eski adres gitti)').toBe(YENI)
    wrapper.unmount()
  })

  it('geçersiz adres (http/gif) kaydedilmez, hata gösterilir', async () => {
    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await bekle(20)

    dugme('Yayınlar')!.click()
    await bekle(30)
    dugme('Görsel')!.click()
    await bekle(40)

    const girdi = Array.from(document.querySelectorAll('input')).find(
      (i) => (i as HTMLInputElement).value === ESKI,
    ) as HTMLInputElement | undefined
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    setter.call(girdi, 'http://ornek.test/a.gif')
    girdi!.dispatchEvent(new Event('input', { bubbles: true }))
    await bekle(20)

    dugme('Uygula')!.click()
    await bekle(40)

    expect(document.body.textContent, 'hata mesajı gösterilmedi').toContain('https')
    // Diyalog açık kalmalı (kullanıcı düzeltebilsin)
    expect(document.body.textContent).toContain('Yayın görseli')
    wrapper.unmount()
  })
})
