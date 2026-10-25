/**
 * İzleme oturumu testleri — bağlantı, abonelik reddi (ACL), kopma.
 *
 * i5 bulgusu: `izlemeBaslat` testsizdi; abonelik reddi (granted qos=128) sessizce yutuluyor,
 * `offline/close/error` olayları dinlenmiyordu. Bu testler o yolları kilitler.
 */
import { describe, expect, it, vi } from 'vitest'

import {
  izlemeBaslat,
  type BaglantiDurumu,
  type MqttIstemci,
} from './cihazIzleme'

class SahteIstemci implements MqttIstemci {
  dinleyiciler: Record<string, Array<(...args: never[]) => void>> = {}
  abonelikler: Array<{ konu: string; geriCagri?: (hata: Error | null, granted?: Array<{ topic: string; qos: number }>) => void }> = []
  kapatildi = false

  on(olay: string, dinleyici: (...args: never[]) => void): this {
    ;(this.dinleyiciler[olay] ??= []).push(dinleyici)
    return this
  }

  subscribe(
    konu: string,
    _secenekler?: Record<string, unknown>,
    geriCagri?: (hata: Error | null, granted?: Array<{ topic: string; qos: number }>) => void,
  ): this {
    this.abonelikler.push({ konu, geriCagri })
    return this
  }

  end(): void {
    this.kapatildi = true
  }

  yay(olay: string, ...args: never[]): void {
    for (const d of this.dinleyiciler[olay] ?? []) d(...args)
  }
}

function kur(istemci = new SahteIstemci()) {
  const durumlar: Array<[BaglantiDurumu, string | undefined]> = []
  const mesajlar: Array<{ cihazId: string; alindi: number }> = []
  return {
    istemci,
    durumlar,
    mesajlar,
    baslat: () =>
      izlemeBaslat(
        (d) => mesajlar.push({ cihazId: d.cihazId, alindi: d.alindi }),
        { url: 'wss://broker.test:8084/mqtt', konu: 'yourkiosk/yayin', kullanici: 'panel-izleme', parola: 'x' },
        {
          durum: (d, a) => durumlar.push([d, a]),
          baglan: () => istemci,
        },
      ),
  }
}

describe('izlemeBaslat', () => {
  it('adres yoksa null döner (izleme kapalı, panel çalışır)', async () => {
    const oturum = await izlemeBaslat(() => undefined, { url: '', kullanici: 'a', parola: 'b' })
    expect(oturum).toBeNull()
  })

  it('kimliği istemciye geçirir (parola env’den DEĞİL, çalışma anından)', async () => {
    const istemci = new SahteIstemci()
    const secenekler: Record<string, unknown>[] = []
    await izlemeBaslat(
      () => undefined,
      { url: 'wss://b:8084/mqtt', kullanici: 'panel-izleme', parola: 'gizli' },
      { baglan: (_u, s) => (secenekler.push(s), istemci) },
    )
    expect(secenekler[0]).toMatchObject({ username: 'panel-izleme', password: 'gizli' })
  })

  it('bağlanınca durum konusuna abone olur ve "bağlı" bildirir', async () => {
    const k = kur()
    await k.baslat()
    k.istemci.yay('connect' as never)
    expect(k.istemci.abonelikler[0]?.konu).toBe('yourkiosk/durum/+')
    k.istemci.abonelikler[0]?.geriCagri?.(null, [{ topic: 'yourkiosk/durum/+', qos: 1 }])
    expect(k.durumlar.at(-1)?.[0]).toBe('bagli')
  })

  it('abonelik ACL ile reddedilirse "hata" (granted qos=128)', async () => {
    const k = kur()
    await k.baslat()
    k.istemci.yay('connect' as never)
    k.istemci.abonelikler[0]?.geriCagri?.(null, [{ topic: 'yourkiosk/durum/+', qos: 128 }])
    expect(k.durumlar.at(-1)?.[0]).toBe('hata')
    expect(k.durumlar.at(-1)?.[1]).toContain('reddedildi')
  })

  it('abonelik hatası da "hata" olarak raporlanır', async () => {
    const k = kur()
    await k.baslat()
    k.istemci.yay('connect' as never)
    k.istemci.abonelikler[0]?.geriCagri?.(new Error('yetkisiz'))
    expect(k.durumlar.at(-1)?.[0]).toBe('hata')
    expect(k.durumlar.at(-1)?.[1]).toContain('yetkisiz')
  })

  it('kopma (offline/close) ve bağlantı hatası bildirilir', async () => {
    const k = kur()
    await k.baslat()
    k.istemci.yay('offline' as never)
    expect(k.durumlar.at(-1)?.[0]).toBe('koptu')
    k.istemci.yay('close' as never)
    expect(k.durumlar.at(-1)?.[0]).toBe('koptu')
    k.istemci.yay('error' as never, new Error('TLS') as never)
    expect(k.durumlar.at(-1)).toEqual(['hata', 'TLS'])
  })

  it('gelen mesajı geliş anı damgasıyla iletir', async () => {
    const k = kur()
    await k.baslat()
    k.istemci.yay(
      'message' as never,
      'yourkiosk/durum/C1' as never,
      new TextEncoder().encode('{"cevrimici":true,"zaman":"2020-01-01T00:00:00Z"}') as never,
    )
    expect(k.mesajlar).toHaveLength(1)
    expect(k.mesajlar[0].cihazId).toBe('C1')
    expect(Math.abs(Date.now() - k.mesajlar[0].alindi)).toBeLessThan(5000)
  })

  it('durdur istemciyi kapatır', async () => {
    const k = kur()
    const oturum = await k.baslat()
    oturum?.durdur()
    expect(k.istemci.kapatildi).toBe(true)
  })
})

describe('izlemeKimligi', () => {
  it('kimliği sessionStorage’a yazar/okur/siler', async () => {
    const depo = new Map<string, string>()
    const sahte = {
      getItem: (k: string) => depo.get(k) ?? null,
      setItem: (k: string, v: string) => void depo.set(k, v),
      removeItem: (k: string) => void depo.delete(k),
    } as unknown as Storage
    const { kimligiOku, kimligiSil, kimligiYaz } = await import('./izlemeKimligi')
    expect(kimligiOku(sahte)).toBeNull()
    kimligiYaz({ kullanici: 'panel-izleme', parola: 'p' }, sahte)
    expect(kimligiOku(sahte)).toEqual({ kullanici: 'panel-izleme', parola: 'p' })
    kimligiSil(sahte)
    expect(kimligiOku(sahte)).toBeNull()
  })

  it('bozuk kayıt okunmaz (elle kurcalanmış storage)', async () => {
    const { kimligiOku } = await import('./izlemeKimligi')
    const sahte = { getItem: () => '{bozuk', removeItem: () => undefined } as unknown as Storage
    expect(kimligiOku(sahte)).toBeNull()
  })

  it('parola .env’den okunmaz: izlemeAdresi yalnız URL verir', async () => {
    const { izlemeAdresi, izlemeKonusu } = await import('./izlemeKimligi')
    expect(izlemeAdresi({ VITE_MQTT_URL: 'wss://b:8084/mqtt', VITE_MQTT_PAROLA: 'sizmasin' })).toBe(
      'wss://b:8084/mqtt',
    )
    expect(izlemeKonusu({})).toBe('yourkiosk/yayin')
  })
})
