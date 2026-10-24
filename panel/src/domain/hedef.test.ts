/**
 * Hedef seçimi yardımcıları + DTO doğrulama testleri.
 *
 * Kapsam kuralları `kiosk/core/model.py` ile aynı olmalı; bu testler ayrışmayı yakalar.
 */
import { describe, expect, it } from 'vitest'

import { adIndeksi, cihazSecenekleri, hedefEtiketi, ilceSecenekleri, matchAgaci } from './hedef'
import { KAPSAM_ACIKLAMASI, kapsamiYaz, yayinDogrula, yayinAlanlari, model, type YayinDto } from './model'
import type { SistemVerisi } from './veri'

const MATCH = {
  lastUpdate: '2026-10-24 10:00:00',
  I1: [{ B1: ['C1', 'C2'] }, { B2: ['C3'] }],
  I2: [{ B3: ['C4'] }],
} as unknown as Record<string, unknown>

const VERI = {
  Nobetler: {
    T20261024: {
      I1: [{ B1: [{ eczane: 'A', ilce: 'Çayırova', bolge: '1. Bölge', ilceId: 'I1', bolgeId: 'B1' }] }],
      I2: [{ B3: [{ eczane: 'B', ilce: 'Gebze', bolge: '3. Bölge', ilceId: 'I2', bolgeId: 'B3' }] }],
    },
  },
} as unknown as SistemVerisi

describe('matchAgaci', () => {
  it('ilçe/bölge/cihazları düzleştirir, lastUpdate anahtarını atlar', () => {
    const agac = matchAgaci(MATCH)
    expect(agac.ilceler.sort()).toEqual(['I1', 'I2'])
    expect(agac.bolgeler.get('I1')).toEqual(['B1', 'B2'])
    expect(agac.cihazlar.get('I1/B1')).toEqual(['C1', 'C2'])
  })

  it('bozuk girdide çökmez', () => {
    expect(matchAgaci(null).ilceler).toEqual([])
    expect(matchAgaci({ I1: 'bozuk' } as unknown as Record<string, unknown>).ilceler).toEqual([])
  })
})

describe('seçenek listeleri', () => {
  it('ilçe adı + kimlik birlikte gösterilir', () => {
    const s = ilceSecenekleri(MATCH, VERI)
    expect(s.find((x) => x.deger === 'I1')?.baslik).toBe('Çayırova (I1)')
  })

  it('bölge ve cihaz seçenekleri bağlıdır', () => {
    expect(ilceSecenekleri(MATCH, VERI).length).toBe(2)
    expect(cihazSecenekleri(MATCH, 'I1', 'B1').map((c) => c.deger)).toEqual(['C1', 'C2'])
    expect(cihazSecenekleri(MATCH, 'I1', '').length).toBe(0)
  })
})

describe('hedefEtiketi', () => {
  it('boş kapsam = tüm cihazlar', () => {
    expect(hedefEtiketi({}, VERI, MATCH)).toBe('Tüm cihazlar')
  })

  it('ilçe adı + cihaz sayısı', () => {
    const etiket = hedefEtiketi({ ilceId: 'I1' }, VERI, MATCH)
    expect(etiket).toContain('Çayırova')
    expect(etiket).toContain('3 cihaz')
  })

  it('cihaz seçiliyse kimliği yazar', () => {
    expect(hedefEtiketi({ ilceId: 'I1', bolgeId: 'B1', cihazId: 'C2' }, VERI, MATCH)).toContain('cihaz C2')
  })
})

describe('adIndeksi', () => {
  it('kayıtta ilceId/bolgeId YOKSA ağaç anahtarından türetir', () => {
    const anahtarsiz = {
      Nobetler: { T1: { I1: [{ B1: [{ eczane: 'A', ilce: 'Çayırova', bolge: '1. Bölge' }] }] } },
    } as unknown as SistemVerisi
    const { ilce, bolge } = adIndeksi(anahtarsiz)
    expect(ilce.get('I1')).toBe('Çayırova')
    expect(bolge.get('B1')).toBe('1. Bölge')
    expect(ilceSecenekleri(MATCH, anahtarsiz).find((s) => s.deger === 'I1')?.baslik).toBe('Çayırova (I1)')
  })

  it('ilçe/bölge adlarını toplar', () => {
    const { ilce, bolge } = adIndeksi(VERI)
    expect(ilce.get('I1')).toBe('Çayırova')
    expect(bolge.get('B3')).toBe('3. Bölge')
  })
})

describe('model (DTO tek kaynak)', () => {
  it('model dosyası yayın alanlarını taşır (üretilmiş dosya)', () => {
    expect(model.surum).toBeGreaterThan(0)
    expect(yayinAlanlari.map((a) => a.ad)).toContain('ilceId')
    expect(yayinAlanlari.map((a) => a.ad)).toContain('cihazId')
    expect(model.kapsam_kurallari.coklu_alan).toBe('VE')
    expect(KAPSAM_ACIKLAMASI).toContain('TÜM cihazlarda')
  })

  it('geçerli yayın hatasız', () => {
    const y: YayinDto = {
      start: '2026-10-24T08:30:00',
      end: '2026-10-24T23:59:00',
      contentUrl: 'https://ornek.example/a.webp',
      duration: 30,
    }
    expect(yayinDogrula(y)).toEqual([])
  })

  it('https olmayan adres reddedilir', () => {
    const hata = yayinDogrula({ start: '2026-10-24T08:30:00', end: '2026-10-24T23:59:00', contentUrl: 'http://x/a.png' })
    expect(hata.join(' ')).toContain('https')
  })

  it('bitiş başlangıçtan önce olamaz', () => {
    const hata = yayinDogrula({
      start: '2026-10-24T23:00:00',
      end: '2026-10-24T08:00:00',
      contentUrl: 'https://x/a.png',
    })
    expect(hata.join(' ')).toContain('Bitiş')
  })

  it('boş kapsam alanları kayıttan SİLİNİR', () => {
    const y = kapsamiYaz({ contentUrl: 'https://x/a.png', ilceId: 'I1' }, { ilceId: 'I1', bolgeId: '', cihazId: '' })
    expect(y.ilceId).toBe('I1')
    expect('bolgeId' in y).toBe(false)
    expect('cihazId' in y).toBe(false)
  })

  it('kapsam yazıldıktan sonra doğrulama geçer', () => {
    const y = kapsamiYaz(
      { start: '2026-10-24T08:30:00', end: '2026-10-24T23:59:00', contentUrl: 'https://x/a.png' },
      { ilceId: 'I1', bolgeId: 'B1', cihazId: 'C1' },
    )
    expect(yayinDogrula(y)).toEqual([])
  })
})
