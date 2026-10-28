/**
 * REGRESYON: "Bildir" KAYDEDİLMEMİŞ değişikliği önce YAZMALI.
 *
 * Gerçek olay: kullanıcı nöbet alanını düzenleyip **Bildir**'e bastı; buton yalnız `tetikle.json`
 * yazıp "gönderildi" diyordu → kiosk aynı veriyi yeniden yükledi, ekranda hiçbir şey değişmedi
 * ("bildir dediğim halde değişmedi"). Bildir, kaydedilmemiş değişiklik varsa önce kaydetmeli.
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
type Kayitlar = { Nobetler: { T20261024: { I1: Array<Record<string, Kayit[]>> } } }

function dugme(wrapper: ReturnType<typeof mount>, metin: string) {
  return wrapper
    .findAll('button')
    .find((b: { text: () => string }) => (b.text() ?? '').includes(metin))
}

describe('VeriView: Bildir akışı', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    yazilanlar.length = 0
    for (const k of Object.keys(DEPO)) delete DEPO[k]
    const d = useDosyalar()
    d.sistem.veri = JSON.parse(JSON.stringify(VERI))
    d.sistem.yuklendi = true
    DEPO['lastSystemData.json'] = JSON.parse(JSON.stringify(VERI))
  })

  it('kaydedilmemiş düzenleme varsa Bildir ÖNCE veriyi yazar', async () => {
    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 20))

    const adres = wrapper
      .findAll('input')
      .find((g: { element: Element }) => (g.element as HTMLInputElement).value === 'ESKİ ADRES')
    expect(adres, 'adres alanı bulunamadı').toBeTruthy()
    await adres!.setValue('BİLDİR İLE YENİ')
    await wrapper.vm.$nextTick()

    const bildir = dugme(wrapper as never, 'Bildir')
    expect(bildir, 'Bildir düğmesi yok').toBeTruthy()
    await bildir!.trigger('click')
    await new Promise((r) => setTimeout(r, 80))

    const sistem = yazilanlar.find((y) => y.ad === 'lastSystemData.json')
    expect(sistem, 'Bildir veriyi KAYDETMEDİ (eski hata)').toBeTruthy()
    const kayit: Kayit = (sistem!.veri as Kayitlar).Nobetler.T20261024.I1[0].B1[0]
    expect(kayit.adres).toBe('BİLDİR İLE YENİ')

    // ve tetikleyici de yazılmalı
    expect(yazilanlar.some((y) => y.ad === 'tetikle.json')).toBe(true)
    wrapper.unmount()
  })

  it('değişiklik yoksa Bildir yalnız tetikleyici yazar (veri yazmaz)', async () => {
    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 20))

    await dugme(wrapper as never, 'Bildir')!.trigger('click')
    await new Promise((r) => setTimeout(r, 60))

    expect(yazilanlar.filter((y) => y.ad === 'lastSystemData.json')).toHaveLength(0)
    expect(yazilanlar.some((y) => y.ad === 'tetikle.json')).toBe(true)
    wrapper.unmount()
  })

  /**
   * REGRESYON: cihaz `durum.json` VARSA `tetikle.json`u indirmez (tek istek maliyet kararı).
   * Bildir yalnız `tetikle.json` yazdığı için Qt kiosk "Bildir"e hiç tepki vermiyordu.
   */
  it('Bildir tetikleyiciyi durum.json içine de yazar (cihaz tek istekle görsün)', async () => {
    const d = useDosyalar()
    d.lastupdate.veri = { lastupdate: '2026-10-24 09:00:00' }
    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 20))

    await dugme(wrapper as never, 'Bildir')!.trigger('click')
    await new Promise((r) => setTimeout(r, 80))

    const durum = yazilanlar.find((y) => y.ad === 'durum.json')
    expect(durum, 'durum.json yazılmadı → cihaz tetiği hiç görmez').toBeTruthy()
    const belge = durum!.veri as { lastupdate: string; tetik: { zaman: string; ilceId: string } }
    expect(belge.tetik?.zaman, 'durum.json tetik zamanı yok').toBeTruthy()
    expect(belge.tetik?.ilceId).toBe('')
    expect(belge.lastupdate, 'mevcut damga korunmalı').toBe('2026-10-24 09:00:00')

    const tetik = yazilanlar.find((y) => y.ad === 'tetikle.json')!.veri as { zaman: string }
    expect(tetik.zaman).toBe(belge.tetik.zaman)
    wrapper.unmount()
  })

  /**
   * REGRESYON (i5 bulgusu, PR #78): `durum.json`a yazılan `lastupdate` panelin BELLEKTEKİ
   * değerinden alınıyordu. "Düzenle + Kaydet + Bildir" akışında `kaydet()` sunucuya TAZE damga
   * yazıyor, ardından Bildir bellekteki ESKİ damgayı `durum.json`a yazıp damgayı GERİ sarıyordu →
   * cihazlar her turda gereksiz `lastupdate.json` çekiyordu.
   */
  it('Bildir durum.json damgasını sunucudaki TAZE değerden alır (damga geri sarılmaz)', async () => {
    const d = useDosyalar()
    d.lastupdate.veri = { lastupdate: '2026-10-24 09:00:00' } // bellek: eski
    DEPO['lastupdate.json'] = { lastupdate: '2026-10-24 10:30:00' } // sunucu: taze
    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 20))

    await dugme(wrapper as never, 'Bildir')!.trigger('click')
    await new Promise((r) => setTimeout(r, 80))

    const durum = yazilanlar.find((y) => y.ad === 'durum.json')
    expect(durum, 'durum.json yazılmadı').toBeTruthy()
    const belge = durum!.veri as { lastupdate: string }
    expect(belge.lastupdate, 'bellekteki ESKİ damga yazıldı → damga geri sardı').toBe('2026-10-24 10:30:00')
    wrapper.unmount()
  })

  /**
   * REGRESYON (i5 bulgusu, PR #78): damga karşılaştırması biçim doğrulamıyordu. Sunucudan nesne
   * gelirse `String()` → `"[object Object]"` ve `"[" > "2"` olduğu için GEÇERLİ damga ezilirdi.
   */
  it('sunucudan çöp damga gelirse bellekteki geçerli damga korunur', async () => {
    const d = useDosyalar()
    d.lastupdate.veri = { lastupdate: '2026-10-24 09:00:00' }
    DEPO['lastupdate.json'] = { lastupdate: { beklenmeyen: true } }
    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 20))

    await dugme(wrapper as never, 'Bildir')!.trigger('click')
    await new Promise((r) => setTimeout(r, 80))

    const durum = yazilanlar.find((y) => y.ad === 'durum.json')
    expect(durum, 'durum.json yazılmadı').toBeTruthy()
    const belge = durum!.veri as { lastupdate: string }
    expect(belge.lastupdate, 'çöp değer geçerli damgayı ezdi').toBe('2026-10-24 09:00:00')
    wrapper.unmount()
  })
})

describe('VeriView: yayın FAIL-CLOSED görünür (27 Ekim i5 bulgusu)', () => {
  // Vuetify diyaloğu jsdom'da `visualViewport` ister (tarayıcıda var, jsdom'da yok) →
  // diyalog açılınca ReferenceError. Yayın kimliği diyaloğu FAIL-CLOSED akışın parçası
  // olduğu için bu testte asgari bir taklit kurulur.
  beforeEach(() => {
    ;(globalThis as unknown as { visualViewport: unknown }).visualViewport = {
      width: 1024,
      height: 768,
      offsetLeft: 0,
      offsetTop: 0,
      scale: 1,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }
  })

  it('yayın gitmezse kullanıcı görür ve kimlik diyaloğu açılır', async () => {
    const { mqttBildir } = await import('@/domain/push')
    const sahte = vi.mocked(mqttBildir)
    sahte.mockResolvedValueOnce({ gonderildi: false, hata: 'yayın kimliği yok — yayın parolası bu oturumda girilmedi' })
    setActivePinia(createPinia())
    yazilanlar.length = 0
    for (const k of Object.keys(DEPO)) delete DEPO[k]
    sessionStorage.clear()
    const d = useDosyalar()
    d.sistem.veri = JSON.parse(JSON.stringify(VERI))
    d.sistem.yuklendi = true
    DEPO['lastSystemData.json'] = JSON.parse(JSON.stringify(VERI))

    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 20))

    const bildir = dugme(wrapper as never, 'Bildir')
    await bildir!.trigger('click')
    await new Promise((r) => setTimeout(r, 80))
    await wrapper.vm.$nextTick()

    const metin = document.body.textContent ?? ''
    expect(metin, 'başarısız yayın sessizce yutuldu').toContain("yayın broker'a gitmedi")
    expect(metin, 'kimlik isteme yolu yok').toContain('Yayın parolasını gir')
    // kimlik diyaloğu AÇILDI (fail-closed akışın çıkışı: kullanıcı parolayı girer)
    expect(metin).toContain('Yayın kimliği')
    wrapper.unmount()
  })

  it('yayın giderse uyarı kalmaz', async () => {
    const { mqttBildir } = await import('@/domain/push')
    vi.mocked(mqttBildir).mockResolvedValue({ gonderildi: true })
    setActivePinia(createPinia())
    yazilanlar.length = 0
    for (const k of Object.keys(DEPO)) delete DEPO[k]
    sessionStorage.clear()
    const d = useDosyalar()
    d.sistem.veri = JSON.parse(JSON.stringify(VERI))
    d.sistem.yuklendi = true
    DEPO['lastSystemData.json'] = JSON.parse(JSON.stringify(VERI))

    const wrapper = mount(VeriView, { global: { plugins: [createVuetify()] }, attachTo: document.body })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 20))
    await dugme(wrapper as never, 'Bildir')!.trigger('click')
    await new Promise((r) => setTimeout(r, 80))
    expect(document.body.textContent ?? '').not.toContain("yayın broker'a gitmedi")
    wrapper.unmount()
  })
})
