/**
 * YAYIN KİMLİĞİ — parola pakete GÖMÜLMEZ (27 Ekim i5 bulgusu, yüksek).
 *
 * Kilitlenen sözleşme:
 *  1) `mqttBildir` yayın parolasını `import.meta.env`ten OKUMAZ; kimliği çalışma anında
 *     `yayinKimligi` (sessionStorage) üzerinden alır.
 *  2) Kimlik yoksa FAIL-CLOSED: broker'a hiç bağlanılmaz, sonuç `gonderildi:false` + gerekçe.
 *  3) Kimlik varsa bağlantı o kullanıcı/parola ile kurulur (paket içinde sır yok).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const connect = vi.fn()

vi.mock('mqtt', () => ({ connect: (...arg: unknown[]) => connect(...arg) }))

/** mqtt.js istemcisinin testteki en küçük taklidi. */
function sahteIstemci(): Record<string, unknown> {
  const istemci: Record<string, unknown> = {
    publish: (_konu: string, _govde: string, _secenek: unknown, cb?: () => void) => cb?.(),
    end: vi.fn(),
    once: (olay: string, cb: (arg?: unknown) => void) => {
      if (olay === 'connect') setTimeout(cb, 0)
      return istemci
    },
  }
  return istemci
}

async function modulYukle(url?: string) {
  vi.resetModules()
  if (url === undefined) vi.stubEnv('VITE_MQTT_URL', '')
  else vi.stubEnv('VITE_MQTT_URL', url)
  vi.stubEnv('VITE_MQTT_KONU', 'yourkiosk/yayin')
  return await import('./push')
}

beforeEach(() => {
  connect.mockReset()
  connect.mockImplementation(() => sahteIstemci())
  sessionStorage.clear()
})

afterEach(() => {
  vi.unstubAllEnvs()
  sessionStorage.clear()
})

describe('mqttBildir — yayın kimliği çalışma anında', () => {
  it('kimlik yokken broker’a HİÇ bağlanmaz (fail-closed)', async () => {
    const { mqttBildir } = await modulYukle('wss://broker.test:8084/mqtt')
    const sonuc = await mqttBildir('test')
    expect(sonuc.gonderildi).toBe(false)
    expect(sonuc.hata).toContain('yayın kimliği yok')
    expect(connect).not.toHaveBeenCalled()
  })

  it('oturumdaki kimlikle bağlanır; kullanıcı/parola kimlikten gelir', async () => {
    const { mqttBildir } = await modulYukle('wss://broker.test:8084/mqtt')
    sessionStorage.setItem('yourkiosk.yayin', JSON.stringify({ kullanici: 'panel', parola: 'gizli' }))
    const sonuc = await mqttBildir('elle-bildirim', '2026-10-27T12:00:00.000Z')
    expect(sonuc).toEqual({ gonderildi: true })
    expect(connect).toHaveBeenCalledTimes(1)
    const [, secenek] = connect.mock.calls[0] as [string, Record<string, unknown>]
    expect(secenek.username).toBe('panel')
    expect(secenek.password).toBe('gizli')
  })

  it('VITE_MQTT_URL yoksa sessizce atlar (cihazlar yoklama ağıyla çalışır)', async () => {
    const { mqttBildir, mqttYapilandirildi } = await modulYukle()
    expect(mqttYapilandirildi()).toBe(false)
    const sonuc = await mqttBildir('test')
    expect(sonuc.gonderildi).toBe(false)
    expect(sonuc.hata).toContain('VITE_MQTT_URL')
  })
})

describe('kaynak taraması — parola derleme değişkeni YOK', () => {
  it('push.ts import.meta.env.VITE_MQTT_PAROLA okumaz', async () => {
    const { readFileSync } = await import('node:fs')
    const { fileURLToPath } = await import('node:url')
    const yol = fileURLToPath(new URL('./push.ts', import.meta.url))
    const kod = readFileSync(yol, 'utf8')
      // yalnız KOD satırları: yorumlar ayıklanır (i5: yorum satırı sızıntı sayılmamalı)
      .split('\n')
      .filter((satir) => !/^\s*(\*|\/\/|\/\*)/.test(satir))
      .join('\n')
    expect(kod).not.toContain('VITE_MQTT_PAROLA')
    expect(kod).not.toContain('VITE_MQTT_KULLANICI')
  })
})
