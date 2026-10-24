/**
 * CANLI DÖNGÜ DAYANIKLILIĞI — "tarayıcı kiosk değişikliği göstermiyor" sınıfına karşı kilit.
 *
 * ÖLÇÜLEN GERÇEK HATA (tarayıcıda, gerçek sayfada):
 *   `/degisiklik` yalnız **BİR kez** çağrıldı (`imza=&sure=30`, 10 ms'de döndü) ve döngü öldü.
 *   Ardından 40+45 sn boyunca panel tetiği yazılmasına rağmen ekran güncellenmedi.
 *   Qt kiosk aynı anda sorunsuz güncelliyordu → hata tarayıcı tarafındaydı.
 *
 * İki ayrı hata sınıfı kilitlenir:
 *   1. `degisiklikBekle` null dönerse döngü `return` edip TAMAMEN bitiyordu,
 *   2. `ilkTur` bayrağı İLK gerçek bildirimi yutuyordu ("ilk değişiklik kayboldu").
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createKiosk } from '@/kiosk'
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

const ZAMAN = (): Date => new Date(2026, 9, 24, 10, 0, 0)

const nobet = (eczane: string) => ({
  eczane,
  tel: '02623251335',
  adres: 'ADRES',
  bolge: 'B1',
  ilce: 'ÇAYIROVA',
  bolgeId: 'B1',
  ilceId: 'I1',
  start: '24/10/2026 08:30',
  end: '25/10/2026 08:30',
})

interface Sahte {
  eczane: string
  /** sırayla dönecek yanıtlar: null = uç yok, 'HATA' = istisna */
  kuyruk: Array<'bildirim' | null | 'HATA'>
  cagri: number
}

function kur(s: Sahte) {
  const kaynak = {
    secenekler: { clientID: 'C1', veri: 'yerel' as const, taban: '' },
    lastupdate: async (): Promise<string> => 'D1',
    async sistemVerisi(): Promise<Record<string, unknown>> {
      return {
        Nobetler: { T20261024: { I1: [{ B1: [nobet(s.eczane)] }] } },
        Yayinlar: {},
      }
    },
    match: async (): Promise<Record<string, unknown>> => ({ I1: [{ B1: ['C1'] }] }),
    ayarBelgesi: async (): Promise<Record<string, unknown> | null> => null,
    gorsel: async (): Promise<ArrayBuffer | null> => null,
    tetikleyici: async (): Promise<TetikBilgisi | null> => null,
    async degisiklikBekle(imza: string): Promise<{
      degisti: boolean
      imza: string
      damga: string
      tetik: TetikBilgisi | null
    } | null> {
      s.cagri += 1
      const siradaki = s.kuyruk.length > 0 ? s.kuyruk.shift()! : null
      if (siradaki === 'HATA') throw new Error('ağ hatası')
      if (siradaki === null) return null
      return { degisti: true, imza: `${imza}y${s.cagri}`, damga: 'D1', tetik: null }
    },
  }
  return createKiosk({ kaynak: kaynak as never, onbellek: new Onbellek(2, new BosDepo()), zaman: ZAMAN })
}

describe('canlı döngü dayanıklılığı', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('null yanıtta ÖLMEZ: sonraki turda yeniden dener', async () => {
    const s: Sahte = { eczane: 'ESKİ', kuyruk: [null, null], cagri: 0 }
    const kiosk = kur(s)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)

    // iki boş yanıt → 3 sn nefes → üçüncü çağrı yapılmalı
    await vi.advanceTimersByTimeAsync(10_000)
    expect(s.cagri, 'döngü null yanıttan sonra durdu (eski hata)').toBeGreaterThanOrEqual(3)
    kiosk.durdur()
  })

  it('istisna döngüyü öldürmez', async () => {
    const s: Sahte = { eczane: 'ESKİ', kuyruk: ['HATA', 'HATA'], cagri: 0 }
    const kiosk = kur(s)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)
    await vi.advanceTimersByTimeAsync(20_000)
    expect(s.cagri, 'istisna sonrası yeniden denenmedi').toBeGreaterThanOrEqual(3)
    kiosk.durdur()
  })

  it('İLK bildirim yutulmaz (ilk değişiklik ekrana gelir)', async () => {
    // tek bir GERÇEK bildirim: ondan sonra uç boş döner
    const s: Sahte = { eczane: 'ESKİ', kuyruk: ['bildirim'], cagri: 0 }
    const kiosk = kur(s)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)

    // İLK bildirim gelir gelmez veri değişti → ekran güncellenmeli (ilkTur yutması yok)
    s.eczane = 'YENİ'
    await vi.advanceTimersByTimeAsync(1_000)
    expect(kiosk.durum.kayitlar[0]?.eczane, 'ilk bildirim yutuldu').toBe('YENİ')
    kiosk.durdur()
  })

  it('durdur() döngüyü gerçekten kapatır (yeni istek atılmaz)', async () => {
    const s: Sahte = { eczane: 'ESKİ', kuyruk: [], cagri: 0 }
    const kiosk = kur(s)
    kiosk.baslat()
    await vi.advanceTimersByTimeAsync(50)
    const once = s.cagri
    kiosk.durdur()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(s.cagri).toBe(once)
  })
})
