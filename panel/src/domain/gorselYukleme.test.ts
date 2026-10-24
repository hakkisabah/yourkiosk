/**
 * Görsel yükleme hattı testleri — boyut/kalite/anahtar kuralları ve kazanç özeti.
 * Gerçek dönüştürme tarayıcıda (canvas) yapılır; burada politika ve anahtar üretimi kilitlenir.
 */
import { describe, expect, it } from 'vitest'

import {
  GORSEL_POLITIKA,
  girisDogrula,
  gorselAnahtari,
  gorselAnahtariYolu,
  gorselHazirla,
  hedefBoyut,
  kazancOzeti,
  type GorselDonusturucu,
} from './gorselYukleme'

describe('hedefBoyut', () => {
  it('büyük görseli en uzun kenara indirir, oranı korur', () => {
    expect(hedefBoyut({ genislik: 1916, yukseklik: 1080 })).toEqual({ genislik: 1916, yukseklik: 1080 })
    expect(hedefBoyut({ genislik: 3840, yukseklik: 2160 })).toEqual({ genislik: 1920, yukseklik: 1080 })
  })

  it('küçük görseli BÜYÜTMEZ', () => {
    expect(hedefBoyut({ genislik: 800, yukseklik: 600 })).toEqual({ genislik: 800, yukseklik: 600 })
  })

  it('dikey görselde yüksekliği sınırlar', () => {
    expect(hedefBoyut({ genislik: 1000, yukseklik: 4000 })).toEqual({ genislik: 480, yukseklik: 1920 })
  })

  it('bozuk boyutta çökmez', () => {
    expect(hedefBoyut({ genislik: 0, yukseklik: 0 })).toEqual({ genislik: 0, yukseklik: 0 })
  })
})

describe('girisDogrula', () => {
  it('png/jpeg/webp kabul', () => {
    for (const tur of ['image/png', 'image/jpeg', 'image/webp']) {
      expect(girisDogrula(tur, 1000)).toBeNull()
    }
  })

  it('svg ve pdf reddedilir (kiosk da kabul etmez)', () => {
    expect(girisDogrula('image/svg+xml', 1000)).toContain('desteklenmeyen tür')
    expect(girisDogrula('application/pdf', 1000)).toContain('desteklenmeyen tür')
  })

  it('boyut sınırı', () => {
    expect(girisDogrula('image/png', GORSEL_POLITIKA.maxGirisBayt + 1)).toContain('çok büyük')
    expect(girisDogrula('image/png', 0)).toBe('boş dosya')
  })
})

describe('içerik adlı anahtar', () => {
  it('aynı içerik → aynı anahtar (tekilleştirme)', async () => {
    const veri = new TextEncoder().encode('ayni-gorsel').buffer
    expect(await gorselAnahtari(veri)).toBe(await gorselAnahtari(veri))
  })

  it('farklı içerik → farklı anahtar', async () => {
    const a = await gorselAnahtari(new TextEncoder().encode('a').buffer)
    const b = await gorselAnahtari(new TextEncoder().encode('b').buffer)
    expect(a).not.toBe(b)
  })

  it('16 karakter hex', async () => {
    const k = await gorselAnahtari(new Uint8Array([1, 2, 3]).buffer)
    expect(k).toMatch(/^[0-9a-f]{16}$/)
  })

  it('yol: önek + anahtar + .webp', () => {
    expect(gorselAnahtariYolu('9f2c1ab34de5f607')).toBe('kiosk/yayin-gorselleri/9f2c1ab34de5f607.webp')
    expect(gorselAnahtariYolu('abc', 'kiosk/')).toBe('kiosk/abc.webp')
    expect(gorselAnahtariYolu('abc', '')).toBe('abc.webp')
  })
})

describe('kazancOzeti', () => {
  it('yüzde küçülme', () => {
    expect(kazancOzeti(2531968, 216000)).toContain('91')
    expect(kazancOzeti(100_000, 100_000)).toContain('%0')
  })
})

describe('gorselHazirla (tam hat)', () => {
  const sahte: GorselDonusturucu = {
    decode: async () => ({ genislik: 3840, yukseklik: 2160 }),
    encode: async (_g, hedef) => new Uint8Array(200_000 + hedef.genislik).buffer,
  }

  it('küçültür, webp anahtarı üretir, kazanç özetler', async () => {
    const sonuc = await gorselHazirla({ tur: 'image/png', govde: new Uint8Array(2_500_000).buffer }, sahte)
    expect(sonuc.boyut).toEqual({ genislik: 1920, yukseklik: 1080 })
    expect(sonuc.yol).toMatch(/^kiosk\/yayin-gorselleri\/[0-9a-f]{16}\.webp$/)
    expect(sonuc.ozet).toContain('küçüldü')
  })

  it('desteklenmeyen türde hata verir', async () => {
    await expect(
      gorselHazirla({ tur: 'image/svg+xml', govde: new ArrayBuffer(10) }, sahte),
    ).rejects.toThrow(/desteklenmeyen tür/)
  })
})
