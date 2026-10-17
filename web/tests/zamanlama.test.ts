/**
 * ZAMANLAMA ve GEÇİŞ testleri — tarayıcı modunda "zamanlama hatası / geçişte takılı kalma"
 * sınıfını kilitler. Qt tarafı tek bir `cycle_timer`'ı her fazda yeniden kurar
 * (`show_current_broadcast` → `start(duration)`, `stop_broadcast_mode` → `start(CYCLE)`);
 * burada aynı davranış sahte zamanlayıcılarla doğrulanır.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createKiosk } from '@/kiosk'
import { Onbellek, type OnbellekDeposu, type Yanit } from '@/veri/onbellek'

const ZAMAN = (): Date => new Date(2026, 9, 15, 12, 0, 0) // 15.10.2026 12:00

const nobet = (eczane: string, bolge: string) => ({
  eczane,
  tel: '02623251335',
  adres: 'ADRES',
  bolge,
  ilce: 'ÇAYIROVA',
  bolgeId: bolge,
  ilceId: 'I1',
  start: '15/10/2026 08:30',
  end: '16/10/2026 08:30',
})

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

function kur(eczaneler: string[], yayin?: Record<string, unknown>) {
  const cagrilar: string[] = []
  const kaynak = {
    secenekler: { clientID: 'C1', veri: 'yerel' as const, taban: '' },
    lastupdate: async (): Promise<string> => 'D1',
    sistemVerisi: async (): Promise<Record<string, unknown>> => ({
      Nobetler: { T20261015: { I1: eczaneler.map((ad, i) => ({ [`B${i + 1}`]: [nobet(ad, `B${i + 1}`)] })) } },
      Yayinlar: yayin ? { '1': yayin } : {},
    }),
    match: async (): Promise<Record<string, unknown>> => ({ I1: [{ B1: ['C1'] }] }),
    ayarBelgesi: async (): Promise<Record<string, unknown> | null> => null,
    gorsel: async (url: string): Promise<ArrayBuffer | null> => {
      cagrilar.push(url)
      return new ArrayBuffer(8)
    },
  }
  const kiosk = createKiosk({ kaynak: kaynak as never, onbellek: new Onbellek(2, new BosDepo()), zaman: ZAMAN })
  return { kiosk, cagrilar }
}

const uzunYayin = {
  start: '2026-10-15T10:00:00',
  end: '2026-10-15T13:00:00',
  contentUrl: 'https://ornek.example/uzun.png',
  duration: '30',
}

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

describe('zamanlama — tek döngü zamanlayıcısı (Qt cycle_timer)', () => {
  it('yayın SÜRESİ DOLMADAN atlanmaz (eski kodda 10 sn`lik nöbet intervali atlıyordu)', async () => {
    const { kiosk } = kur(['A', 'B'], uzunYayin)
    await kiosk.yukle()
    await kiosk.yayinaGec()
    expect(kiosk.durum.yayinModu).toBe(true)
    expect(kiosk.durum.gorselUrl).toBe(uzunYayin.contentUrl)

    // 10.1 sn: eski kurguda sabit 10 sn'lik döngü burada yayını atlatırdı
    await vi.advanceTimersByTimeAsync(10_100)
    expect(kiosk.durum.yayinModu).toBe(true)
    expect(kiosk.durum.yayinIndex).toBe(0)
    expect(kiosk.durum.gorselUrl).toBe(uzunYayin.contentUrl)

    // 30 sn dolunca liste biter → yayın modundan çıkılır (Qt: cycle_timer 10 sn'ye döner)
    await vi.advanceTimersByTimeAsync(20_000)
    expect(kiosk.durum.yayinModu).toBe(false)
    expect(kiosk.durum.gorselUrl).toBe('')
  })

  it('nöbet adımı CYCLE_INTERVAL_MS ile döner', async () => {
    const { kiosk } = kur(['A', 'B', 'C'])
    await kiosk.yukle()
    void kiosk.dongu() // ilk adım
    expect(kiosk.durum.index).toBe(1)
    await vi.advanceTimersByTimeAsync(10_100)
    expect(kiosk.durum.index).toBe(2)
    // liste bitti, aktif yayın yok → başa döner ve döngü DEVAM eder
    await vi.advanceTimersByTimeAsync(10_100)
    expect(kiosk.durum.index).toBe(0)
    await vi.advanceTimersByTimeAsync(10_100)
    expect(kiosk.durum.index).toBe(1)
  })

  it('yayından çıkışta durum temizlenir ve döngü nöbet kadansına döner', async () => {
    const { kiosk, cagrilar } = kur(['A', 'B'], uzunYayin)
    await kiosk.yukle()
    await kiosk.yayinaGec()
    expect(cagrilar).toHaveLength(1) // yayın görseli bir kez alındı

    kiosk.yayindanCik() // listedeki görseller alınamadı / liste bitti
    expect(kiosk.durum.yayinModu).toBe(false)
    expect(kiosk.durum.gorselUrl).toBe('')
    expect(kiosk.durum.kusak.gorunur).toBe(false)

    const oncekiIndex = kiosk.durum.index
    await vi.advanceTimersByTimeAsync(9_000) // yayın 30 sn'ydi: bu aralıkta HİÇBİR yayın adımı olmamalı
    expect(kiosk.durum.gorselUrl).toBe('')
    expect(cagrilar).toHaveLength(1)
    expect(kiosk.durum.index).toBe(oncekiIndex)

    await vi.advanceTimersByTimeAsync(1_200) // 10.2 sn: nöbet kadansı (CYCLE_INTERVAL_MS)
    expect(kiosk.durum.index).toBe((oncekiIndex + 1) % kiosk.durum.kayitlar.length)
  })
})

describe('geçişler — takılı kalma koruması', () => {
  it('requestAnimationFrame duraklatılsa bile geçiş HEDEFE ulaşır', async () => {
    vi.stubGlobal('requestAnimationFrame', () => 1) // kare hiç çalışmaz (occluded/arka plan)
    const { kiosk } = kur(['A', 'B'])
    await kiosk.yukle()
    const ilk = kiosk.durum.aktifBlok
    kiosk.durum.index = 1
    kiosk.goster(true)
    expect(kiosk.durum.aktifBlok).toBe(ilk) // henüz hedefe geçmedi
    await vi.advanceTimersByTimeAsync(100) // yedek zaman aşımı
    expect(kiosk.durum.aktifBlok).not.toBe(ilk)
    expect(kiosk.durum.konumlar[kiosk.durum.aktifBlok]).toBe(0)
  })

  it('saatlik yenileme MEVCUT kaydı korur (sol ↔ orta panel desenkron olmaz)', async () => {
    const { kiosk } = kur(['A', 'B', 'C'])
    await kiosk.yukle()
    kiosk.durum.index = 2
    kiosk.goster(false)
    await kiosk.yukle() // REFRESH_INTERVAL_MS turu
    expect(kiosk.durum.index).toBe(2)
    expect(kiosk.durum.bloklar[kiosk.durum.aktifBlok]?.eczane).toBe(kiosk.durum.kayitlar[2].eczane)
  })
})
