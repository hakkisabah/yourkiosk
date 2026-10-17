/**
 * Kapsam çözümlemesi — kiosk (Python) ile AYNI test verisi ve AYNI beklentiler.
 * Ortak veri: kiosk/tests/veri/kapsam_ornek.json
 * Python tarafı: kiosk/tests/test_kapsam_ayarlari.py
 */
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { kapsamCoz, kapsamSatirlari, kapsamSil, kapsamYaz, kapsamKimlikleri, type KapsamBelgesi } from './kapsam'

const oku = (yol: string): KapsamBelgesi =>
  JSON.parse(readFileSync(new URL(yol, import.meta.url), 'utf8')) as KapsamBelgesi

const ORNEK = oku('../../../kiosk/tests/veri/kapsam_ornek.json')

describe('kapsamCoz — çözümleme sırası', () => {
  it('varsayılan kapsam uygulanır', () => {
    const { belge, kaynak } = kapsamCoz(ORNEK)
    expect(belge.ozellikler.kayan_yazi).toBe(true)
    expect(belge.kusak.yazi_punto).toBe(36)
    expect(kaynak['kusak.yazi_punto']).toBe('varsayilan')
  })

  it('ilçe değeri, bölge tarafından geçersiz kılınır', () => {
    const { belge, kaynak } = kapsamCoz(ORNEK, { ilceId: '1001', bolgeId: '2002' })
    expect(belge.ozellikler.kayan_yazi).toBe(true) // ilçe false dedi, bölge true ile kazandı
    expect(kaynak['ozellikler.kayan_yazi']).toBe('bolge:2002')
  })

  it('ilçe kapsamı, cihaz kaydı yokken geçerli olur; punto varsayılandan gelir', () => {
    const { belge } = kapsamCoz(ORNEK, { ilceId: '1001', bolgeId: '2999', clientId: 'YOK-0001' })
    expect(belge.ozellikler.kayan_yazi).toBe(false) // ilçe kazandı
    expect(belge.kusak.yazi_punto).toBe(36) // varsayılan
  })

  it('cihaz kapsamı en özel: hem varsayılanı hem bölgeyi geçer', () => {
    const { belge, kaynak } = kapsamCoz(ORNEK, { ilceId: '1001', bolgeId: '2002', clientId: 'ORNEK-CIHAZ-0001' })
    expect(belge.kusak.yazi_punto).toBe(28)
    expect(kaynak['kusak.yazi_punto']).toBe('cihaz:ORNEK-CIHAZ-0001')
    expect(kaynak['ozellikler.kayan_yazi']).toBe('bolge:2002')
    expect(belge.ozellikler.saat_tarih).toBe(true)
  })

  it('kapsam dosyası yoksa/boşsa hiçbir şey uygulanmaz', () => {
    expect(kapsamCoz(null).belge).toEqual({})
    expect(kapsamCoz({}, { ilceId: '1001' }).belge).toEqual({})
  })

  it('bilinmeyen grup, kapsam grupları dışındaki grup ve _ ile başlayan anahtarlar yok sayılır', () => {
    const ham: KapsamBelgesi = {
      varsayilan: { veri: { kaynak: 'https' }, ozellikler: { _yorum: 'x', yayinlar: false } } as never,
      ilceler: { '1': { yok: { a: 1 } } as never },
    }
    const { belge } = kapsamCoz(ham, { ilceId: '1' })
    expect(belge.ozellikler?.yayinlar).toBe(false)
    expect(belge.veri).toBeUndefined() // 'veri' grubu kapsam bazında yönetilmez
    expect(belge.yok).toBeUndefined()
    expect(belge.ozellikler?._yorum).toBeUndefined()
  })
})

describe('kapsamSatirlari — etkin değer + kaynak', () => {
  it('her anahtar için kaynağı ve etkin değeri verir', () => {
    const satirlar = kapsamSatirlari(ORNEK, { ilceId: '1001', bolgeId: '2002', clientId: 'ORNEK-CIHAZ-0001' })
    const punto = satirlar.find((s) => s.tam === 'kusak.yazi_punto')
    expect(punto?.etkin).toBe(28)
    expect(punto?.kaynak).toBe('cihaz:ORNEK-CIHAZ-0001')
    expect(punto?.gecersizMi).toBe(false)
    expect(satirlar.every((s) => !s.gecersizMi)).toBe(true)
  })

  it('aralık dışı değeri geçersiz olarak işaretler (kiosk yok sayar, panel uyarır)', () => {
    const ham: KapsamBelgesi = { varsayilan: { kusak: { yazi_punto: 9999 } } }
    const satir = kapsamSatirlari(ham).find((s) => s.tam === 'kusak.yazi_punto')
    expect(satir?.gecersizMi).toBe(true)
    expect(satir?.hata).toContain('üst sınırın üstünde')
    expect(satir?.etkin).toBe(36) // varsayılana düşer
  })
})

describe('kapsamYaz / kapsamSil — düzenleme', () => {
  it('değer yazar ve üst kapsama geri alma çalışır', () => {
    const yeni = kapsamYaz({}, 'bolgeler', '2002', { 'ozellikler.kayan_yazi': false, 'kusak.yazi_punto': 30 })
    expect(yeni.bolgeler?.['2002'].ozellikler.kayan_yazi).toBe(false)
    const temiz = kapsamSil(yeni, 'bolgeler', '2002', ['kusak.yazi_punto'])
    expect(temiz.bolgeler?.['2002'].kusak).toBeUndefined() // boş grup atıldı
    expect(temiz.bolgeler?.['2002'].ozellikler.kayan_yazi).toBe(false)
  })

  it('kapsam grupları dışındaki anahtarı yazmaz', () => {
    const yeni = kapsamYaz({}, 'varsayilan', '', { 'veri.kaynak': 'https', 'ozellikler.saat_tarih': false })
    expect(yeni.varsayilan?.veri).toBeUndefined()
    expect(yeni.varsayilan?.ozellikler.saat_tarih).toBe(false)
  })

  it('girdi belgesini değiştirmez (immutable)', () => {
    const girdi: KapsamBelgesi = { varsayilan: { kusak: { yazi_punto: 36 } } }
    kapsamYaz(girdi, 'ilceler', '1001', { 'kusak.yazi_punto': 20 })
    expect(girdi.ilceler).toBeUndefined()
  })

  it('kapsam kimliklerini listeler', () => {
    expect(kapsamKimlikleri(ORNEK)).toEqual({
      varsayilan: [''],
      ilceler: ['1001'],
      bolgeler: ['2002'],
      cihazlar: ['ORNEK-CIHAZ-0001'],
    })
  })
})
