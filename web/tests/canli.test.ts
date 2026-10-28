/**
 * CANLI NÖBET DEĞİŞİKLİĞİ testleri — "değişiklik gösterim sırasında yansıyor mu" sorusunu kilitler.
 *
 * İki yol vardır:
 *  1) ANLIK (uzun yoklama `/degisiklik`): imza değiştiği an bildirim → yenileme (tipik <1 sn),
 *  2) YOKLAMA (`DAMGA_KONTROL_MS`, push BAĞLI **120 sn** / kopuk **30 sn** — anlıklık push/uzun
 *     yoklamayla gelir; 20 sn'lik süre 600 cihazda ~$268/ay istek maliyeti demekti):
 *     `lastupdate.json` + `tetikle.json`.
 * Ayrıca panelin yazdığı TETİKLEYİCİ yalnızca ilgili ilçenin cihazında hemen uygulanır.
 *
 * SÜRE KAYNAĞI (26 Ekim i5 bulgusu): `YOKLAMA_MS` burada ELLE YAZILMAZ. Eskiden `300_000` sabiti
 * vardı; gerçek varsayılan 120 sn olduğu hâlde test 300 sn ilerlettiği için *her* değerde yeşil
 * kalıyordu (yani bu dosya "süreler koddan türetilir" iddiasını doğrulamıyordu). Artık değer
 * `yerlesim.json`dan (`kiosk/config.py` → `tools/web_disa_aktar.py`) okunur ve iki yön kilitlidir:
 * `kiosk.ts` yedeği ile eşitlik + yoklamanın aralıktan ÖNCE atmaması.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** Damga yoklaması periyodu — üretilmiş sabitten (`yerlesim.json`); yedek yalnız güvenlik ağı. */
const YOKLAMA_MS = sabit('DAMGA_KONTROL_MS', 120_000)

import { createKiosk, tetikUygulanmali } from '@/kiosk'
import { sabit, sabitler } from '@/stiller/olcu'
import { Onbellek, type OnbellekDeposu, type Yanit } from '@/veri/onbellek'
import type { TetikBilgisi } from '@/veri/kaynak'

class BosDepo implements OnbellekDeposu {
  async match(): Promise<Yanit | undefined> {
    return undefined
  }
  async put(): Promise<void> {}
  async delete(): Promise<boolean> {
    return false
  }
  async keys(): Promise<readonly unknown[]> {
    return []
  }
}

const ZAMAN = (): Date => new Date(2026, 9, 17, 10, 0, 0)

const nobet = (eczane: string, bolge: string) => ({
  eczane,
  tel: '02623251335',
  adres: 'ADRES',
  bolge,
  ilce: 'ÇAYIROVA',
  bolgeId: bolge,
  ilceId: 'I1',
  start: '17/10/2026 08:30',
  end: '18/10/2026 08:30',
})

interface SahteDurum {
  damga: string
  eczane: string
  bildirim?: { degisti: boolean; imza: string; damga: string; tetik: TetikBilgisi | null } | null
  tetik?: TetikBilgisi | null
  yuklemeSayisi: number
}

function kur(durum: SahteDurum) {
  const kaynak = {
    secenekler: { clientID: 'C1', veri: 'yerel' as const, taban: '' },
    lastupdate: async (): Promise<string> => durum.damga,
    async sistemVerisi(): Promise<Record<string, unknown>> {
      durum.yuklemeSayisi += 1
      return {
        Nobetler: { T20261017: { I1: [{ B1: [nobet(durum.eczane, 'B1')] }] } },
        Yayinlar: {},
      }
    },
    match: async (): Promise<Record<string, unknown>> => ({ I1: [{ B1: ['C1'] }] }),
    ayarBelgesi: async (): Promise<Record<string, unknown> | null> => null,
    gorsel: async (): Promise<ArrayBuffer | null> => null,
    tetikleyici: async (): Promise<TetikBilgisi | null> => durum.tetik ?? null,
    degisiklikBekle: async (): Promise<typeof durum.bildirim> => durum.bildirim ?? null,
  }
  const kiosk = createKiosk({ kaynak: kaynak as never, onbellek: new Onbellek(2, new BosDepo()), zaman: ZAMAN })
  return { kiosk }
}

const tetik = (zaman: string, ilceId = '', bolgeId = ''): TetikBilgisi => ({
  zaman,
  ilceId,
  bolgeId,
  aciklama: '',
})

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('requestAnimationFrame', (cb: () => void) => {
    cb()
    return 1
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('tetikUygulanmali — ilçe bazlı tetikleyici kuralı', () => {
  const konum = { ilceId: 'I1', bolgeId: 'B1' }

  it('boş/"*" ilçe → tüm cihazlar', () => {
    expect(tetikUygulanmali(tetik('2026-10-17T09:00:00', ''), konum, '')).toBe(true)
    expect(tetikUygulanmali(tetik('2026-10-17T09:00:00', '*'), konum, '')).toBe(true)
  })

  it('kendi ilçesi/bölgesi → uygulanır; başka ilçe → uygulanmaz', () => {
    expect(tetikUygulanmali(tetik('2026-10-17T09:00:00', 'I1'), konum, '')).toBe(true)
    expect(tetikUygulanmali(tetik('2026-10-17T09:00:00', '', 'B1'), konum, '')).toBe(true)
    expect(tetikUygulanmali(tetik('2026-10-17T09:00:00', 'I9'), konum, '')).toBe(false)
    expect(tetikUygulanmali(tetik('2026-10-17T09:00:00', 'I9', 'B9'), konum, '')).toBe(false)
  })

  it('aynı/eski tetikleyici tekrar uygulanmaz', () => {
    expect(tetikUygulanmali(tetik('2026-10-17T09:00:00'), konum, '2026-10-17T09:00:00')).toBe(false)
    expect(tetikUygulanmali(tetik('2026-10-17T08:00:00'), konum, '2026-10-17T09:00:00')).toBe(false)
    expect(tetikUygulanmali(tetik('2026-10-17T10:00:00'), konum, '2026-10-17T09:00:00')).toBe(true)
  })

  it('tetikleyici yoksa/boşsa uygulanmaz', () => {
    expect(tetikUygulanmali(null, konum, '')).toBe(false)
    expect(tetikUygulanmali(tetik(''), konum, '')).toBe(false)
  })
})

describe('canlı değişiklik — yansıma', () => {
  it('damga değişince (yoklama turu) gösterim yenilenir', async () => {
    const durum: SahteDurum = { damga: 'D1', eczane: 'ESKİ', yuklemeSayisi: 0 }
    const { kiosk } = kur(durum)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)
    expect(kiosk.durum.damga).toBe('D1')
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('ESKİ')

    // nöbet değişikliği: sunucudaki damga + veri değişti
    durum.damga = 'D2'
    durum.eczane = 'YENİ'
    await vi.advanceTimersByTimeAsync(YOKLAMA_MS + 100) // DAMGA_KONTROL_MS
    expect(kiosk.durum.damga).toBe('D2')
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('YENİ')
    expect(kiosk.durum.gunluk.some((s) => s.includes('nöbet verisi değişti'))).toBe(true)
    kiosk.durdur()
  })

  it('uzun yoklama anlık bildirim verince beklemeden yenilenir', async () => {
    const durum: SahteDurum = {
      damga: 'D1',
      eczane: 'ESKİ',
      yuklemeSayisi: 0,
      bildirim: { degisti: true, imza: 'İMZA1', damga: 'D1', tetik: null },
    }
    const { kiosk } = kur(durum)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)
    expect(kiosk.durum.damga).toBe('D1')

    // sunucu "değişti" bildirir (damga D2), arayüz ANINDA yeniler.
    // (Uzun yoklama turu: imza değişmedikçe 800 ms nefes verir; yani en kötü ~1 sn,
    //  damga yoklamasını beklemez.)
    durum.damga = 'D2'
    durum.eczane = 'YENİ'
    durum.bildirim = { degisti: true, imza: 'İMZA2', damga: 'D2', tetik: null }
    await vi.advanceTimersByTimeAsync(1_000)
    expect(kiosk.durum.damga).toBe('D2')
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('YENİ')
    kiosk.durdur()
  })

  it('kendi ilçesinin tetikleyicisi hemen uygulanır, başka ilçeninki uygulanmaz', async () => {
    const durum: SahteDurum = { damga: 'D1', eczane: 'ESKİ', yuklemeSayisi: 0, tetik: null }
    const { kiosk } = kur(durum)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)

    // başka ilçe: hemen yenilenmemeli
    durum.tetik = tetik('2026-10-17T09:00:00', 'I9')
    durum.eczane = 'YENİ'
    await vi.advanceTimersByTimeAsync(YOKLAMA_MS + 100)
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('ESKİ')

    // kendi ilçesi: yenilenmeli
    durum.tetik = tetik('2026-10-17T09:30:00', 'I1')
    await vi.advanceTimersByTimeAsync(YOKLAMA_MS + 100)
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('YENİ')
    expect(kiosk.durum.gunluk.some((s) => s.includes('tetikleyici'))).toBe(true)
    kiosk.durdur()
  })

  it('damga AYNI olsa da anlık bildirim gelince tazelenir (panel/araç değişikliği)', async () => {
    // Eski kurgu yalnız damga değişince yeniliyordu → `lastupdate` tazelenmemiş yerel
    // değişiklik (panel kaydı, geçici test verisi) ekranda hiç görünmüyordu.
    const durum: SahteDurum = {
      damga: 'D1',
      eczane: 'ESKİ',
      yuklemeSayisi: 0,
      bildirim: { degisti: true, imza: 'İMZA1', damga: 'D1', tetik: null },
    }
    const { kiosk } = kur(durum)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)

    durum.eczane = 'YENİ' // veri değişti, damga değişmedi
    durum.bildirim = { degisti: true, imza: 'İMZA2', damga: 'D1', tetik: null }
    await vi.advanceTimersByTimeAsync(1_000)
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('YENİ')
    // Davranış: bildirim gelince önbellek ATLANIR (metin değişebilir, kural değişmez)
    expect(kiosk.durum.gunluk.some((s) => s.includes('anlık bildirim'))).toBe(true)
    expect(kiosk.durum.gunluk.some((s) => s.includes('önbellek atlanıp'))).toBe(true)
    kiosk.durdur()
  })

  it('yenileme gösterimi bozmaz: sıradaki adım ve kuşak durumu korunur', async () => {
    const durum: SahteDurum = { damga: 'D1', eczane: 'A', yuklemeSayisi: 0 }
    const kaynakSistem = {
      Nobetler: {
        T20261017: {
          I1: [{ B1: [nobet('A', 'B1')] }, { B2: [nobet('B', 'B2')] }, { B3: [nobet('C', 'B3')] }],
        },
      },
      Yayinlar: {},
    }
    void kaynakSistem
    const { kiosk } = kur(durum)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)
    const indexOnce = kiosk.durum.index
    durum.damga = 'D2'
    await vi.advanceTimersByTimeAsync(YOKLAMA_MS + 100)
    expect(kiosk.durum.hazir).toBe(true)
    expect(kiosk.durum.hata).toBe('')
    expect(kiosk.durum.index).toBe(indexOnce) // yenileme indeksi sıfırlamaz
    expect(kiosk.durum.aktifBlok).toBeGreaterThanOrEqual(0)
    kiosk.durdur()
  })
})

describe('yoklama aralığı — koddan türetilir (26 Ekim i5 bulgusu)', () => {
  /** `web/src/kiosk.ts` kaynağı (yedek değer + bayat yorum denetimi). */
  const kioskKaynagi = (): string => readFileSync(resolve(process.cwd(), 'src/kiosk.ts'), 'utf-8')

  it('üretilen sabit ile kiosk.ts yedeği aynı (sapma kilidi)', () => {
    // yerlesim.json → kiosk/config.py'den üretilir; test ondan okur, elle yazmaz.
    expect(sabitler.DAMGA_KONTROL_MS).toBe(YOKLAMA_MS)
    const m = kioskKaynagi().match(/sabit\('DAMGA_KONTROL_MS',\s*([\d_]+)\)/)
    expect(m, "kiosk.ts içinde sabit('DAMGA_KONTROL_MS', …) çağrısı bulunamadı").not.toBeNull()
    expect(Number((m as RegExpMatchArray)[1].replace(/_/g, ''))).toBe(YOKLAMA_MS)
  })

  it('kiosk.ts bayat varsayılan iddia etmez (belge kayması kilidi)', () => {
    // Eski yorum "varsayılan 300 sn" diyordu, kod 120 sn idi. Artık her "varsayılan N sn"
    // iddiası ölçülen değeri yazmak zorunda; ayrıca 300 sn'lik bayat iddia tamamen yasak.
    const kaynak = kioskKaynagi()
    expect(kaynak).not.toMatch(/varsayılan\s+300\s*sn/i)
    for (const satir of kaynak.split('\n').filter((s) => s.trimStart().startsWith('*'))) {
      const m = satir.match(/varsayılan\s+(\d+)\s*sn/i)
      if (m) expect(Number(m[1]) * 1000).toBe(YOKLAMA_MS)
    }
  })

  it('yoklama aralıktan ÖNCE çalışmaz, aralık dolunca çalışır', async () => {
    const durum: SahteDurum = { damga: 'D1', eczane: 'ESKİ', yuklemeSayisi: 0 }
    const { kiosk } = kur(durum)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('ESKİ')

    durum.damga = 'D2'
    durum.eczane = 'YENİ'
    // aralığın 1 sn öncesi: damga yoklaması HENÜZ atmamalı — eski test yalnız üst sınırı
    // sınadığı için yanlış (büyük) bir sabitle de yeşil kalıyordu.
    await vi.advanceTimersByTimeAsync(YOKLAMA_MS - 1_050)
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('ESKİ')

    // aralık dolunca yenilenmeli
    await vi.advanceTimersByTimeAsync(1_200)
    expect(kiosk.durum.kayitlar[0]?.eczane).toBe('YENİ')
    kiosk.durdur()
  })
})
