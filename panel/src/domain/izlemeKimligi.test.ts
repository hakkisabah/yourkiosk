import { describe, expect, it } from 'vitest'

import { guvenliAdresMi, izlemeAdresi, izlemeAdresiHatasi } from './izlemeKimligi'

/**
 * Broker adresi kapısı (26 Ekim i5 bulgusu).
 *
 * `izlemeAdresi` eskiden `.env`teki `VITE_MQTT_URL`i yalnız `trim` ediyordu: `ws://` yazılırsa
 * çalışma anında girilen izleme parolası DÜZ METİN giderdi; `http://` ise mqtt.js'te hiç
 * bağlanmaz ve izleme sessizce ölürdü. Kural: yalnız `wss://`; `ws://` yalnız yerel adlarda.
 */

describe('guvenliAdresMi', () => {
  it('wss:// her adreste güvenli', () => {
    expect(guvenliAdresMi('wss://yourkiosk.hakkisabah.com/mqtt')).toBe(true)
    expect(guvenliAdresMi('wss://10.0.0.5:8084/mqtt')).toBe(true)
  })

  it('ws:// yalnız yerel adlarda kabul edilir (geliştirme)', () => {
    expect(guvenliAdresMi('ws://localhost:8084')).toBe(true)
    expect(guvenliAdresMi('ws://127.0.0.1:8084')).toBe(true)
    expect(guvenliAdresMi('ws://[::1]:8084')).toBe(true)
    expect(guvenliAdresMi('ws://yourkiosk.hakkisabah.com:8084')).toBe(false)
    expect(guvenliAdresMi('ws://192.168.1.20:8084')).toBe(false)
  })

  it('http/https/boş/bozuk değerler reddedilir', () => {
    expect(guvenliAdresMi('http://yourkiosk.hakkisabah.com')).toBe(false)
    expect(guvenliAdresMi('https://yourkiosk.hakkisabah.com')).toBe(false)
    expect(guvenliAdresMi('')).toBe(false)
    expect(guvenliAdresMi('   ')).toBe(false)
    expect(guvenliAdresMi('yourkiosk.hakkisabah.com')).toBe(false)
  })
})

describe('izlemeAdresi / izlemeAdresiHatasi', () => {
  it('güvenli adres olduğu gibi geçer, hata metni boş', () => {
    const env = { VITE_MQTT_URL: ' wss://yourkiosk.hakkisabah.com/mqtt ' }
    expect(izlemeAdresi(env)).toBe('wss://yourkiosk.hakkisabah.com/mqtt')
    expect(izlemeAdresiHatasi(env)).toBe('')
  })

  it('güvensiz adres SESSİZCE geçmez: adres boşalır, yöneticiye hata döner', () => {
    const env = { VITE_MQTT_URL: 'ws://yourkiosk.hakkisabah.com:8084' }
    expect(izlemeAdresi(env)).toBe('')
    const hata = izlemeAdresiHatasi(env)
    expect(hata).toContain('güvenli değil')
    expect(hata).toContain('wss://')
  })

  it('tanımsız değer ne adres ne hata üretir (izleme kapalı sayılır)', () => {
    expect(izlemeAdresi({})).toBe('')
    expect(izlemeAdresiHatasi({})).toBe('')
  })
})
