/**
 * MFA (TOTP) testleri — RFC 6238 vektörleriyle.
 *
 * NEDEN: iki adımlı doğrulama şimdilik KAPALI ama algoritma hazır bekliyor. Yanlış bir TOTP
 * uygulaması açıldığı gün herkesi kilitler; bu yüzden standart vektörlerle doğrulanır.
 */
import { describe, expect, it } from 'vitest'

import {
  base32Coz,
  base32Kodla,
  mfaAktifMi,
  otpauthAdresi,
  sabitZamanliEsit,
  tohumUret,
  totpDogrula,
  totpUret,
  VARSAYILAN_MFA_AKTIF,
} from './mfa'

// RFC 6238 Ek B: tohum "12345678901234567890" (ASCII) = base32 aşağıdaki gibi.
const RFC_TOHUM = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
const RFC_TOHUM_ASCII = '12345678901234567890'

describe('bayrak', () => {
  it('varsayılan KAPALI (sistem çalışırken açılacak)', () => {
    expect(VARSAYILAN_MFA_AKTIF).toBe(false)
    expect(mfaAktifMi({})).toBe(false)
    expect(mfaAktifMi({ VITE_MFA_AKTIF: '' })).toBe(false)
    expect(mfaAktifMi({ VITE_MFA_AKTIF: '0' })).toBe(false)
  })

  it('yalnız açık değerlerde true', () => {
    expect(mfaAktifMi({ VITE_MFA_AKTIF: '1' })).toBe(true)
    expect(mfaAktifMi({ VITE_MFA_AKTIF: 'true' })).toBe(true)
    expect(mfaAktifMi({ VITE_MFA_AKTIF: 'evet' })).toBe(true)
  })
})

describe('base32', () => {
  it('ASCII tohumu RFC vektöründeki base32 karşılığına çevirir', () => {
    expect(base32Kodla(new TextEncoder().encode(RFC_TOHUM_ASCII))).toBe(RFC_TOHUM)
  })

  it('gidiş-dönüş kayıpsız', () => {
    const veri = new Uint8Array([0, 1, 2, 250, 251, 255, 42])
    expect(Array.from(base32Coz(base32Kodla(veri)))).toEqual(Array.from(veri))
  })

  it('küçük harf, boşluk ve dolgu kabul edilir; geçersiz karakter hata verir', () => {
    expect(base32Kodla(base32Coz('gezd gnbv gy3t qojq gezd gnbv gy3t qojq===='))).toBe(RFC_TOHUM)
    expect(() => base32Coz('ABC1')).toThrow(/base32/)
  })
})

describe('totpUret — RFC 6238 vektörleri (SHA1, 8 hane)', () => {
  // [zaman (sn), beklenen 8 haneli kod]
  const vektorler: Array<[number, string]> = [
    [59, '94287082'],
    [1111111109, '07081804'],
    [1111111111, '14050471'],
    [1234567890, '89005924'],
    [2000000000, '69279037'],
    [20000000000, '65353130'],
  ]

  it.each(vektorler)('T=%i → %s', async (saniye, beklenen) => {
    const kod = await totpUret(RFC_TOHUM, saniye * 1000, { hane: 8 })
    expect(kod).toBe(beklenen)
  })

  it('6 hane varsayılanı: aynı vektörün son 6 hanesi', async () => {
    expect(await totpUret(RFC_TOHUM, 59_000, { hane: 6 })).toBe('287082')
  })
})

describe('totpDogrula — fail-closed', () => {
  const zaman = 59_000

  it('doğru kodu kabul eder', async () => {
    const kod = await totpUret(RFC_TOHUM, zaman)
    expect(await totpDogrula(RFC_TOHUM, kod, zaman)).toBe(true)
  })

  it('boşluklu girişi kabul eder (kullanıcı "123 456" yazabilir)', async () => {
    const kod = await totpUret(RFC_TOHUM, zaman)
    expect(await totpDogrula(RFC_TOHUM, `${kod.slice(0, 3)} ${kod.slice(3)}`, zaman)).toBe(true)
  })

  it('yanlış kodu reddeder', async () => {
    expect(await totpDogrula(RFC_TOHUM, '000000', zaman)).toBe(false)
  })

  it('boş/bozuk girdide false (asla true değil)', async () => {
    expect(await totpDogrula(RFC_TOHUM, '', zaman)).toBe(false)
    expect(await totpDogrula(RFC_TOHUM, 'abcdef', zaman)).toBe(false)
    expect(await totpDogrula(RFC_TOHUM, '12345', zaman)).toBe(false) // 5 hane
    expect(await totpDogrula(RFC_TOHUM, '1234567', zaman)).toBe(false) // 7 hane
    expect(await totpDogrula('', '123456', zaman)).toBe(false)
    expect(await totpDogrula('!!!!', '123456', zaman)).toBe(false)
  })

  it('±1 pencere toleransı (saat kayması)', async () => {
    const oncekiPencere = await totpUret(RFC_TOHUM, zaman - 30_000)
    const sonrakiPencere = await totpUret(RFC_TOHUM, zaman + 30_000)
    expect(await totpDogrula(RFC_TOHUM, oncekiPencere, zaman)).toBe(true)
    expect(await totpDogrula(RFC_TOHUM, sonrakiPencere, zaman)).toBe(true)
  })

  it('tolerans dışı pencere reddedilir', async () => {
    const eski = await totpUret(RFC_TOHUM, zaman - 120_000)
    expect(await totpDogrula(RFC_TOHUM, eski, zaman)).toBe(false)
  })
})

describe('sabitZamanliEsit', () => {
  it('eşit/eşit olmayan/farklı uzunluk', () => {
    expect(sabitZamanliEsit('123456', '123456')).toBe(true)
    expect(sabitZamanliEsit('123456', '123457')).toBe(false)
    expect(sabitZamanliEsit('123456', '12345')).toBe(false)
    expect(sabitZamanliEsit('', '')).toBe(true)
  })
})

describe('tohumUret', () => {
  it('20 bayt → 32 karakter base32, her çağrıda farklı', () => {
    const a = tohumUret()
    const b = tohumUret()
    expect(a).toMatch(/^[A-Z2-7]{32}$/)
    expect(a).not.toBe(b)
    expect(base32Coz(a).length).toBe(20)
  })
})

describe('otpauthAdresi', () => {
  it('Authenticator uygulamalarının beklediği alanları taşır', () => {
    const adres = new URL(otpauthAdresi(RFC_TOHUM, 'yonetici@ornek', 'YourKiosk'))
    expect(adres.protocol).toBe('otpauth:')
    expect(adres.searchParams.get('secret')).toBe(RFC_TOHUM)
    expect(adres.searchParams.get('issuer')).toBe('YourKiosk')
    expect(adres.searchParams.get('algorithm')).toBe('SHA1')
    expect(adres.searchParams.get('digits')).toBe('6')
    expect(adres.searchParams.get('period')).toBe('30')
    expect(decodeURIComponent(adres.pathname)).toBe('/YourKiosk:yonetici@ornek')
  })
})
