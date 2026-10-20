// @vitest-environment jsdom
/**
 * GERÇEK RENDER TESTİ (jsdom) — arayüz, cihazdaki GERÇEK veriyle açılıyor mu?
 *
 * Neden gerekli: tarayıcı modunda "beyaz ekran" yaşandı. Sebep, kaynak klasörün
 * sunulmasıydı (`index.html` → `/src/main.ts`, tarayıcı `.ts` çalıştıramaz). Bu test
 * uygulamayı jsdom'da gerçekten **mount eder** ve DOM'da nöbetçi listesi, orta panel
 * metinleri ve saat/tarih etiketlerini arar — yani beyaz ekran olmadığını kanıtlar.
 *
 * Veri kaynağı: `kiosk/` klasöründeki gerçek dosyalar (lastSystemData.json, match.json,
 * lastupdate.json, makinebilgileri.json). Ağ ve Cache Storage taklit edilir.
 */
import { createApp } from 'vue'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { cssDegiskenleriniUygula } from '@/stiller/olcu'
import { bulunanDosyalar, cihazDosyasi, cihazVerisiVar } from './yardimci/cihaz-verisi'

/* Veri: `kiosk/` klasöründeki GERÇEK dosyalar — ÇALIŞMA ANINDA okunur (import.meta.glob).
   Cihaz verisi depoya girmediği için derleme zamanında `import` EDİLEMEZ (temiz klonda TS2307).
   Dosyalar yoksa gerçek-veri testleri atlanır; sahte veriyle koşan testler etkilenmez. */
const sistem = (await cihazDosyasi<Record<string, unknown>>('lastSystemData.json')) ?? { Nobetler: {}, Yayinlar: {} }
const match = (await cihazDosyasi<Record<string, unknown>>('match.json')) ?? {}
const lastupdate = (await cihazDosyasi<Record<string, unknown>>('lastupdate.json')) ?? { lastupdate: '' }
const makine = await cihazDosyasi<{ clientID?: string }>('makinebilgileri.json')
const KIMLIK = String(makine?.clientID ?? '')

if (!cihazVerisiVar) {
  // Görünür bilgi: test çıktısında neden atlandığı anlaşılsın
  console.warn(
    '[render.test] Cihaz verisi bulunamadı; gerçek veriyle koşan testler atlanacak.\n' +
      '  Beklenen: kiosk/lastSystemData.json, match.json, lastupdate.json, makinebilgileri.json\n' +
      `  Bulunan kiosk JSON: ${bulunanDosyalar.join(', ') || '(yok)'}`,
  )
}

class BellekDeposu {
  kayitlar = new Map<string, Response>()
  async match(s: string): Promise<Response | undefined> {
    const y = this.kayitlar.get(s)
    return y ? (y.clone() as unknown as Response) : undefined
  }
  async put(s: string, y: Response): Promise<void> {
    this.kayitlar.set(s, y.clone() as unknown as Response)
  }
  async delete(s: string): Promise<boolean> {
    return this.kayitlar.delete(s)
  }
  async keys(): Promise<readonly string[]> {
    return [...this.kayitlar.keys()]
  }
}

let uygulama: ReturnType<typeof createApp> | null = null

beforeAll(() => {
  // SAAT DONDURULUR: nöbet penceresi (blok tarihi 08:30 → ertesi gün 08:30) ve gün bloğu
  // seçimi zamana bağlıdır; gerçek saatle koşarsa test gün içinde 1↔2 satır arasında oynar
  // (veri seti 14–29 Ekim 2026). Yalnızca `Date` taklit edilir; zamanlayıcılar gerçek kalır.
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-17T10:00:00+03:00'))
  // CSS değişkenleri GERÇEK `<html>`e de uygulanır (uygulama `main.ts`te böyle yapar):
  // bu, "birimsiz ölçü → height:auto → siyah ekran" hatasının bu testte de görünmesini sağlar.
  const degiskenler = cssDegiskenleriniUygula(document.documentElement)
  expect(document.documentElement.style.getPropertyValue('--ekran-y')).toBe(degiskenler['--ekran-y'])
  expect(degiskenler['--ekran-y']).toMatch(/^\d+px$/)
  // Ağ taklidi: istenen dosyayı adına göre ver (URL: /lastSystemData.json vb.)
  vi.stubGlobal('fetch', async (girdi: unknown) => {
    const ad = String(girdi).split('?')[0].split('/').pop() ?? ''
    const kayitlar: Record<string, unknown> = {
      'lastupdate.json': lastupdate,
      'lastSystemData.json': sistem,
      'match.json': match,
      'ayarlar.json': null,
      'kapsam-ayarlari.json': null,
    }
    if (!(ad in kayitlar) || kayitlar[ad] === null) return new Response('yok', { status: 404 })
    return new Response(JSON.stringify(kayitlar[ad]), { headers: { 'Content-Type': 'application/json' } })
  })

  // Cache Storage taklidi (önbellek açık/kapalı senaryoları aynı kodla çalışsın)
  const depo = new BellekDeposu()
  vi.stubGlobal('caches', {
    open: async () => depo,
    delete: async () => true,
    keys: async () => [],
  })

  document.body.innerHTML = '<div id="uygulama"></div>'
})

afterEach(() => {
  uygulama?.unmount()
  uygulama = null
})

describe.skipIf(!cihazVerisiVar)('arayüz gerçek veriyle açılıyor (beyaz ekran yok)', () => {
  it('nöbetçi listesi, orta panel ve saat DOM\'da görünür', async () => {
    // URL: yalnızca cihaz kimliği + veri modu (gerçek kullanımdaki gibi)
    Object.defineProperty(window, 'location', {
      value: {
        search: KIMLIK ? `?clientID=${encodeURIComponent(KIMLIK)}&veri=yerel` : '?veri=yerel',
        href: 'http://127.0.0.1:8090/',
      },
      writable: true,
    })
    const { default: App } = await import('@/App.vue')
    uygulama = createApp(App)
    uygulama.mount('#uygulama')

    if (!KIMLIK) {
      // cihaz kimliği dosyası yoksa bile beyaz ekran olmamalı: okunabilir hata kartı
      await vi.waitFor(() => expect(document.querySelector('.hata-kart')).not.toBeNull())
      return
    }

    // veri yükleme + ilk çizim
    await vi.waitFor(() => {
      expect(document.querySelectorAll('.satir').length).toBeGreaterThan(0)
    })

    const metin = document.body.textContent ?? ''
    // orta panel: eczane adı (büyük harf + " ECZANESİ") ve tarih aralığı etiketi
    expect(metin).toContain('ECZANESİ')
    expect(metin).toContain('TARİHLER ARASI NÖBETÇİ!')
    // hata kartı GÖSTERİLMEMELİ (veri gerçekten yüklendi)
    expect(document.querySelector('.hata-kart')).toBeNull()
    // sol panel satırları: cihazın bölgesindeki kayıt sayısı (Çayırova 2.Bölge → 2)
    expect(document.querySelectorAll('.satir').length).toBe(2)
    // saat/tarih
    const saat = document.querySelector('.saat-kutu .saat')?.textContent ?? ''
    expect(saat).toMatch(/^\d{2}:\d{2}$/)
    expect(document.querySelector('.saat-kutu .gun')?.textContent ?? '').not.toBe('')
    // nöbet ekranında kuşak yoktur (yalnızca yayın görünümünde)
    expect(document.querySelector('.kusak')).toBeNull()
    // orta panel yerleşimi: serit + viewport + iki blok
    expect(document.querySelectorAll('.orta-panel .blok').length).toBe(2)
  })
})

describe('eksik/bozuk başlatma parametreleri', () => {
  it('cihaz kimliği yoksa beyaz ekran yerine okunabilir hata kartı çıkar', async () => {
    Object.defineProperty(window, 'location', {
      value: { search: '?veri=yerel', href: 'http://127.0.0.1:8090/' },
      writable: true,
    })
    const { default: App } = await import('@/App.vue')
    uygulama = createApp(App)
    uygulama.mount('#uygulama')
    await vi.waitFor(() => {
      expect(document.querySelector('.hata-kart')).not.toBeNull()
    })
    const metin = document.querySelector('.hata-kart')?.textContent ?? ''
    expect(metin).toContain('bulunamadı')
    expect(metin).toContain('index.html?clientID=')
  })
})

/**
 * 5'TEN FAZLA NÖBETÇİ (kaydırmalı sol panel) — DOM düzeyinde doğrulama.
 *
 * Cihazın gerçek verisinde günde 1 kayıt olduğu için kaydırma görülmez. Cihazda denemek için
 * `kiosk/tools/gecici_coklu_test.py --adet 8` kullanılır; burada aynı senaryo sahte veriyle
 * (8 kayıt, 1080p) çizilir: tüm satırlar DOM'da olmalı, satır yüksekliği Qt ile aynı olmalı ve
 * liste 5 satırdan fazlasında kaydırılabilir olmalı.
 */
describe('sol panel: 5`ten fazla nöbetçi (kaydırmalı)', () => {
  const ILCE = '30607352906750376'
  const BOLGE = '73154087615041151'

  afterEach(() => {
    uygulama?.unmount()
    uygulama = null
    document.body.innerHTML = ''
  })

  it('8 kayıt çizilir, satır yüksekliği 208 px ve liste kaydırılabilir olur', async () => {
    const CIHAZ = 'CIHAZ-8'
    Object.defineProperty(window, 'location', {
      value: { search: `?clientID=${CIHAZ}&veri=yerel`, href: 'http://127.0.0.1:8090/' },
      writable: true,
    })
    const kayitlar = Array.from({ length: 8 }, (_, i) => ({
      eczane: `ECZANE ${i + 1}`,
      tel: '02623251335',
      adres: `ADRES ${i + 1}`,
      bolge: 'Çayırova 2.Bölge',
      ilce: 'ÇAYIROVA',
      bolgeId: BOLGE,
      ilceId: ILCE,
      start: '17/10/2026 08:30',
      end: '18/10/2026 08:30',
    }))
    vi.stubGlobal('fetch', async (girdi: unknown) => {
      const ad = String(girdi).split('?')[0].split('/').pop() ?? ''
      if (ad === 'lastupdate.json') {
        return new Response(JSON.stringify({ lastupdate: 'C8' }), { status: 200 })
      }
      if (ad === 'lastSystemData.json') {
        return new Response(JSON.stringify({ Nobetler: { T20261017: { [ILCE]: [{ [BOLGE]: kayitlar }] } }, Yayinlar: {} }), {
          status: 200,
        })
      }
      if (ad === 'match.json') {
        return new Response(JSON.stringify({ [ILCE]: [{ [BOLGE]: [CIHAZ] }] }), { status: 200 })
      }
      return new Response('yok', { status: 404 })
    })
    const { default: App } = await import('@/App.vue')
    uygulama = createApp(App)
    uygulama.mount('#uygulama')

    await vi.waitFor(() => {
      expect(document.querySelectorAll('.satir').length).toBe(8)
    })
    // satır yüksekliği Qt referansıyla aynı (1040/5 = 208 px) ve liste kaydırılabilir
    expect(
      window.getComputedStyle(document.documentElement).getPropertyValue('--satir-yuksekligi').trim(),
    ).toBe('208px')
    const liste = document.querySelector('.sol-panel .liste')
    expect(liste).not.toBeNull()
    expect(document.querySelector('.sol-panel')?.classList.contains('kaydirmasiz')).toBe(false)
    // ilk satır aktif (beyaz zemin görseli Qt'deki activeBox.png)
    expect(document.querySelector('.satir.aktif')).not.toBeNull()
    // ekranda 8 kaydın hepsi DOM'da: kaydırma hedefleri kiosk.test.ts'te Qt değerleriyle kilitli
    expect(document.querySelector('.orta-panel')?.textContent).toContain('ECZANE 1')
  })
})
