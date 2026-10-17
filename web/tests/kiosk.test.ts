/**
 * KIOSK DURUM MAKİNESİ testleri — Qt `pharmacy_app.py` akışıyla birebir.
 *
 * Bu testler tarayıcı GEREKTİRMEZ: döngü, yayın sırası, kaydırma hedefi ve özellik
 * bayrakları sahte veri kaynağıyla doğrulanır (tarayıcıda görsel doğrulama ayrıca yapılır).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createKiosk } from '@/kiosk'
import { Onbellek, type OnbellekDeposu, type Yanit } from '@/veri/onbellek'

// ------------------------------------------------------------------ sahteler
class SahteDepo implements OnbellekDeposu {
  kayitlar = new Map<string, Yanit>()
  async match(s: string): Promise<Yanit | undefined> {
    return this.kayitlar.get(s)
  }
  async put(s: string, y: Yanit): Promise<void> {
    const basliklar = new Map<string, string>()
    for (const ad of ['x-url', 'x-alindi', 'x-son-gosterim', 'x-gosterim', 'x-sha256', 'content-type', 'x-damga']) {
      const d = y.headers.get(ad)
      if (d !== null) basliklar.set(ad, d)
    }
    const govde = await y.arrayBuffer()
    this.kayitlar.set(s, {
      headers: { get: (ad: string) => basliklar.get(ad.toLowerCase()) ?? null },
      arrayBuffer: async () => govde,
      text: async () => new TextDecoder().decode(govde),
      ok: true,
      status: 200,
    })
  }
  async delete(s: string): Promise<boolean> {
    return this.kayitlar.delete(s)
  }
  async keys(): Promise<readonly string[]> {
    return [...this.kayitlar.keys()]
  }
}

interface SahteKaynakAyarlari {
  sistem?: Record<string, unknown>
  match?: Record<string, unknown>
  ayarlar?: Record<string, unknown>
  kapsam?: Record<string, unknown>
  gorselVar?: boolean
  clientID?: string
}

function sahteKaynak(a: SahteKaynakAyarlari = {}) {
  const cagrilar: string[] = []
  return {
    cagrilar,
    kaynak: {
      secenekler: { clientID: a.clientID ?? 'C1', veri: 'yerel' as const, taban: '' },
      async lastupdate() {
        return 'D1'
      },
      async sistemVerisi() {
        return a.sistem ?? null
      },
      async match() {
        return a.match ?? null
      },
      async ayarBelgesi(ad: string) {
        return ad === 'ayarlar.json' ? (a.ayarlar ?? null) : (a.kapsam ?? null)
      },
      async gorsel(url: string) {
        cagrilar.push(url)
        return a.gorselVar === false ? null : new ArrayBuffer(8)
      },
    } as never,
  }
}

function nobetKaydi(eczane: string, bolge: string, start: string, end: string) {
  return { eczane, tel: '02623251335', adres: 'ADRES', bolge, ilce: 'ÇAYIROVA', bolgeId: bolge, ilceId: 'I1', start, end }
}

const ZAMAN = () => new Date(2026, 9, 15, 12, 0, 0) // 15.10.2026 12:00

function kur(a: SahteKaynakAyarlari = {}) {
  const depo = new SahteDepo()
  const onbellek = new Onbellek(2, depo)
  const sahte = sahteKaynak(a)
  const kiosk = createKiosk({ kaynak: sahte.kaynak, onbellek, zaman: ZAMAN })
  return { kiosk, depo, onbellek, sahte }
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (cb: () => void) => {
    cb()
    return 1
  })
  vi.stubGlobal('cancelAnimationFrame', () => 0)
})

// ------------------------------------------------------------------ veri yükleme
describe('yukle — cihazın bölgesi ve sıralama', () => {
  const sistem = {
    Nobetler: {
      T20261015: {
        I1: [
          {
            B2: [nobetKaydi('ZEYNEP', 'Çayırova 2.Bölge', '15/10/2026 08:30', '16/10/2026 08:30')],
          },
          {
            B1: [nobetKaydi('DEVA', 'Çayırova 1.Bölge', '15/10/2026 08:30', '16/10/2026 08:30')],
          },
        ],
        I2: [{ B9: [nobetKaydi('BAŞKA', 'Diğer', '15/10/2026 08:30', '16/10/2026 08:30')] }],
      },
    },
    Yayinlar: {},
  }

  it('cihazın ilçesindeki kayıtları yükler, bölge+eczane sırasına dizer', async () => {
    const { kiosk } = kur({ sistem, match: { I1: [{ B2: ['C1'] }] } })
    expect(await kiosk.yukle()).toBe(true)
    expect(kiosk.durum.kayitlar.map((k) => k.eczane)).toEqual(['DEVA', 'ZEYNEP'])
    expect(kiosk.durum.gunAnahtari).toBe('T20261015')
    expect(kiosk.durum.hazir).toBe(true)
  })

  it('cihaz kimliği match.json içinde yoksa hata verir', async () => {
    const { kiosk } = kur({ sistem, match: { I1: [{ B2: ['BAŞKA'] }] } })
    expect(await kiosk.yukle()).toBe(false)
    expect(kiosk.durum.hata).toContain('bulunamadı')
  })

  it('pentersiz kayıt gösterilir (veriyi yargılayamıyorsak gizlemeyiz)', async () => {
    const { kiosk } = kur({
      sistem: { Nobetler: { T20261015: { I1: [{ B1: [{ eczane: 'X', bolge: 'B1', ilceId: 'I1', bolgeId: 'B1' }] }] } } },
      match: { I1: [{ B1: ['C1'] }] },
    })
    await kiosk.yukle()
    expect(kiosk.durum.kayitlar).toHaveLength(1)
  })
})

// ------------------------------------------------------------------ döngü
describe('dongu — nöbet ↔ yayın akışı (Qt manage_loop)', () => {
  const aktifYayin = {
    start: '2026-10-15T10:00:00',
    end: '2026-10-15T13:00:00',
    contentUrl: 'https://ornek.example/a.png',
    duration: '5',
  }
  const sistem = {
    Nobetler: {
      T20261015: {
        I1: [
          { B1: [nobetKaydi('A', 'B1', '15/10/2026 08:30', '16/10/2026 08:30')] },
          { B2: [nobetKaydi('B', 'B2', '15/10/2026 08:30', '16/10/2026 08:30')] },
        ],
      },
    },
    Yayinlar: { '1': aktifYayin },
  }

  it('liste bitince aktif yayın varsa yayın moduna geçer', async () => {
    const { kiosk } = kur({ sistem, match: { I1: [{ B1: ['C1'] }] } })
    await kiosk.yukle()
    expect(kiosk.durum.index).toBe(0)
    kiosk.dongu() // 0 → 1
    expect(kiosk.durum.index).toBe(1)
    expect(kiosk.durum.yayinModu).toBe(false)
    kiosk.dongu() // liste bitti → yayın
    await vi.waitFor(() => expect(kiosk.durum.yayinModu).toBe(true))
    expect(kiosk.durum.gorselUrl).toBe('https://ornek.example/a.png')
  })

  it('aktif yayın yoksa liste bitince başa döner (yayına geçilmez)', async () => {
    const { kiosk } = kur({ sistem: { ...sistem, Yayinlar: {} }, match: { I1: [{ B1: ['C1'] }] } })
    await kiosk.yukle()
    kiosk.dongu()
    kiosk.dongu()
    expect(kiosk.durum.yayinModu).toBe(false)
    expect(kiosk.durum.index).toBe(0)
  })

  it('yayınlar kapalıysa yalnızca nöbet listesi döner', async () => {
    const { kiosk } = kur({
      sistem,
      match: { I1: [{ B1: ['C1'] }] },
      ayarlar: { ozellikler: { yayinlar: false } },
    })
    await kiosk.yukle()
    expect(kiosk.durum.ozellikler.yayinlar).toBe(false)
    kiosk.dongu()
    kiosk.dongu()
    kiosk.dongu()
    expect(kiosk.durum.yayinModu).toBe(false)
    expect(kiosk.durum.index).toBe(1) // 0→1→0→1
  })

  it('yayında liste bitince nöbet ekranına döner', async () => {
    const { kiosk } = kur({ sistem, match: { I1: [{ B1: ['C1'] }] } })
    await kiosk.yukle()
    await kiosk.yayinaGec()
    expect(kiosk.durum.yayinModu).toBe(true)
    await kiosk.sonrakiYayin() // tek yayın → liste bitti
    expect(kiosk.durum.yayinModu).toBe(false)
    expect(kiosk.durum.index).toBe(0)
  })

  it('görsel alınamazsa yayın atlanır ve mod bitmezse sıradakine geçilir', async () => {
    const { kiosk } = kur({ sistem, match: { I1: [{ B1: ['C1'] }] }, gorselVar: false })
    await kiosk.yukle()
    await kiosk.yayinaGec()
    expect(kiosk.durum.yayinModu).toBe(false) // tek yayın atlandı → çıkış
    expect(kiosk.durum.gorselUrl).toBe('')
  })

  it('nöbet listesi kapalıyken yalnız-yayın döngüsü çalışır', async () => {
    const { kiosk } = kur({
      sistem,
      match: { I1: [{ B1: ['C1'] }] },
      ayarlar: { ozellikler: { nobet_listesi: false } },
    })
    await kiosk.yukle()
    expect(kiosk.durum.ozellikler.nobet_listesi).toBe(false)
    kiosk.dongu()
    await vi.waitFor(() => expect(kiosk.durum.yayinModu).toBe(true))
  })
})

// ------------------------------------------------------------------ kaydırma + saat
describe('sol panel kaydırma hedefi (Qt belgelenmiş değerler)', () => {
  it('8 kayıtta hedefler [0,0,0,0,0,218,436,654]', async () => {
    const kayitlar = Array.from({ length: 8 }, (_, i) => nobetKaydi(`E${i}`, 'B1', '15/10/2026 08:30', '16/10/2026 08:30'))
    const { kiosk } = kur({
      sistem: { Nobetler: { T20261015: { I1: [{ B1: kayitlar }] } } },
      match: { I1: [{ B1: ['C1'] }] },
    })
    await kiosk.yukle()
    const hedefler: number[] = []
    for (let i = 0; i < 8; i += 1) {
      kiosk.durum.index = i
      kiosk.goster(false)
      hedefler.push(kiosk.durum.kaydirma)
    }
    expect(hedefler).toEqual([0, 0, 0, 0, 0, 218, 436, 654])
  })

  it('5 ve daha az kayıtta kaydırma hiç değişmez', async () => {
    const kayitlar = Array.from({ length: 5 }, (_, i) => nobetKaydi(`E${i}`, 'B1', '15/10/2026 08:30', '16/10/2026 08:30'))
    const { kiosk } = kur({
      sistem: { Nobetler: { T20261015: { I1: [{ B1: kayitlar }] } } },
      match: { I1: [{ B1: ['C1'] }] },
    })
    await kiosk.yukle()
    for (let i = 0; i < 5; i += 1) {
      kiosk.durum.index = i
      kiosk.goster(false)
      expect(kiosk.durum.kaydirma).toBe(0)
    }
  })
})

describe('saat/tarih/gün ve özellik bayrağı', () => {
  it('HH:mm · gg.aa.yyyy · Türkçe gün adı (büyük harfle başlar)', async () => {
    const { kiosk } = kur({})
    kiosk.saatGuncelle()
    expect(kiosk.durum.saat.saat).toBe('12:00')
    expect(kiosk.durum.saat.tarih).toBe('15.10.2026')
    expect(kiosk.durum.saat.gun).toBe('Perşembe')
  })

  it('saat_tarih kapalıysa etiketler boşaltılır', async () => {
    const { kiosk } = kur({
      sistem: { Nobetler: { T20261015: { I1: [{ B1: [nobetKaydi('A', 'B1', '15/10/2026 08:30', '16/10/2026 08:30')] }] } } },
      match: { I1: [{ B1: ['C1'] }] },
      ayarlar: { ozellikler: { saat_tarih: false } },
    })
    await kiosk.yukle()
    kiosk.saatGuncelle()
    expect(kiosk.durum.saat).toEqual({ saat: '', tarih: '', gun: '' })
  })

  it('nöbet + yayın birlikte kapalı olamaz (nöbet zorla açılır)', async () => {
    const { kiosk } = kur({
      sistem: { Nobetler: { T20261015: { I1: [{ B1: [nobetKaydi('A', 'B1', '15/10/2026 08:30', '16/10/2026 08:30')] }] } } },
      match: { I1: [{ B1: ['C1'] }] },
      ayarlar: { ozellikler: { nobet_listesi: false, yayinlar: false } },
    })
    await kiosk.yukle()
    expect(kiosk.durum.ozellikler.nobet_listesi).toBe(true)
  })
})

// ------------------------------------------------------------------ kuşak
describe('kayan yazı kuşağı', () => {
  const sistem = {
    Nobetler: {
      T20261015: {
        I1: [
          { B1: [nobetKaydi('A', 'B1', '15/10/2026 08:30', '16/10/2026 08:30')] },
          { B2: [nobetKaydi('B', 'B2', '15/10/2026 08:30', '16/10/2026 08:30')] },
        ],
      },
    },
    Yayinlar: {
      '1': { start: '2026-10-15T10:00:00', end: '2026-10-15T13:00:00', contentUrl: 'https://x/a.png', duration: '60' },
    },
  }

  it('yayın modunda kuşak görünür ve öğeler kayıt sırasına göre üretilir', async () => {
    const { kiosk } = kur({ sistem, match: { I1: [{ B1: ['C1'] }] } })
    await kiosk.yukle()
    expect(kiosk.durum.kusak.ogeler).toEqual(['A - 0262 325 13 35', 'B - 0262 325 13 35'])
    await kiosk.yayinaGec()
    expect(kiosk.durum.kusak.gorunur).toBe(true)
    expect(kiosk.durum.kusak.metin).toBe('A - 0262 325 13 35')
  })

  it('kayan_yazi kapalıysa kuşak görünmez', async () => {
    const { kiosk } = kur({
      sistem,
      match: { I1: [{ B1: ['C1'] }] },
      ayarlar: { ozellikler: { kayan_yazi: false } },
    })
    await kiosk.yukle()
    await kiosk.yayinaGec()
    expect(kiosk.durum.kusak.gorunur).toBe(false)
  })

  it('kuşak adımı yayın modunda değilse konumu değiştirmez', async () => {
    const { kiosk } = kur({ sistem, match: { I1: [{ B1: ['C1'] }] } })
    await kiosk.yukle()
    const onceki = kiosk.durum.kusak.x
    kiosk.kusakAdimi()
    expect(kiosk.durum.kusak.x).toBe(onceki)
  })
})
