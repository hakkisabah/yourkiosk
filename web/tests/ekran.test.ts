/**
 * Ekran biçimi + cihaz konumu testleri (Qt `data_handler`/`sync`/`utils` ile birebir).
 */
import { describe, expect, it } from 'vitest'

import {
  adresMetni,
  cihazKonumunuBul,
  kaydiEkranBicimineCevir,
  tarihAralikMetni,
  tarihMetni,
  temizMetin,
} from '@/veri/ekran'

describe('temizMetin', () => {
  it('satır sonlarını boşluğa çevirir, boşlukları sadeleştirir', () => {
    expect(temizMetin('  A\nB\t\tC  ')).toBe('A B C')
  })

  it('bidi/denetim karakterlerini atar', () => {
    expect(temizMetin('E\u202eCZANE\u200f')).toBe('E CZANE')
  })

  it('sınırı aşarsa "…" ile kısaltır', () => {
    const uzun = 'A'.repeat(100)
    const sonuc = temizMetin(uzun, 10)
    expect(sonuc.length).toBeLessThanOrEqual(10)
    expect(sonuc.endsWith('…')).toBe(true)
  })

  it('boş/eksik değerde boş metin döner', () => {
    expect(temizMetin(null)).toBe('')
    expect(temizMetin(undefined)).toBe('')
  })
})

describe('kaydiEkranBicimineCevir', () => {
  it('telefonu biçimler, alanları temizler', () => {
    const k = kaydiEkranBicimineCevir({
      eczane: ' Deva Eczanesi ',
      tel: '2623251335',
      adres: 'Ömerağa Mah.\nNo:3',
      adres_tarifi: 'BELSA SOK.',
      bolge: 'Çayırova 2.Bölge',
      start: '14/10/2026 08:30',
      end: '15/10/2026 08:30',
    })
    expect(k.eczane).toBe('Deva Eczanesi')
    expect(k.ikincil).toBe('0262 325 13 35')
    expect(k.adres).toBe('Ömerağa Mah. No:3')
    expect(adresMetni(k)).toBe('ÖMERAĞA MAH. NO:3\nBELSA SOK.')
  })

  it('telefon yoksa bölge adına düşer (EKSIK_TELEFON_YERINE_BOLGE)', () => {
    expect(kaydiEkranBicimineCevir({ tel: '', bolge: 'B1' }).ikincil).toBe('B1')
    expect(kaydiEkranBicimineCevir({ tel: '', bolge: 'B1' }, false).ikincil).toBe('-')
  })

  it('baslangic/bitis alternatif alan adlarını da okur', () => {
    const k = kaydiEkranBicimineCevir({ baslangic: '14/10/2026 08:30', bitis: '15/10/2026 08:30' })
    expect(k.start).toBe('14/10/2026 08:30')
    expect(k.end).toBe('15/10/2026 08:30')
  })
})

describe('tarih metinleri', () => {
  it('kiosk biçimini üretir (gg.aa.yy ss:dd:ss)', () => {
    expect(tarihMetni('14/10/2026 08:30')).toBe('14.10.26 08:30:00')
    expect(tarihMetni('2026-10-15T08:30:00')).toBe('15.10.26 08:30:00')
  })

  it('okunamayan tarihte "-"', () => {
    expect(tarihMetni('bilinmiyor')).toBe('-')
    expect(tarihAralikMetni({ start: 'yok', end: 'yok' })).toBe('-')
  })

  it('tarih aralığı etiketini üretir', () => {
    expect(tarihAralikMetni({ start: '14/10/2026 08:30', end: '15/10/2026 08:30' })).toBe(
      '14.10.26 08:30:00 - 15.10.26 08:30:00 TARİHLER ARASI NÖBETÇİ!',
    )
  })
})

describe('cihazKonumunuBul', () => {
  const match = {
    lastUpdate: 'x',
    I1: [{ B1: ['makine-1', 'makine-2'] }, { B2: ['makine-3'] }],
    I2: [{ B9: ['makine-9'] }],
  }

  it('cihaz kimliğine göre ilçe/bölge bulur', () => {
    expect(cihazKonumunuBul(match, 'makine-3')).toEqual({ ilceId: 'I1', bolgeId: 'B2', bulundu: true })
    expect(cihazKonumunuBul(match, 'makine-9')).toEqual({ ilceId: 'I2', bolgeId: 'B9', bulundu: true })
  })

  it('bulunamazsa bulundu=false', () => {
    expect(cihazKonumunuBul(match, 'yok').bulundu).toBe(false)
    expect(cihazKonumunuBul(null, 'makine-1').bulundu).toBe(false)
    expect(cihazKonumunuBul(match, '').bulundu).toBe(false)
  })

  it('lastupdate anahtarını cihaz listesi sanmaz', () => {
    expect(cihazKonumunuBul({ lastupdate: ['makine-1'] }, 'makine-1').bulundu).toBe(false)
  })
})
