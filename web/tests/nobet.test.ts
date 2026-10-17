/**
 * Nöbet penceresi kuralları — kiosk (`core/sync.py`) ile aynı beklentiler.
 * Çayırova senaryosu: aynı günde bir nöbet 08:30'da, diğeri 23:59'da bitiyor.
 */
import { describe, expect, it } from 'vitest'

import {
  aktifKayitlar,
  gosterilecekKayitlar,
  gunEtiketi,
  gunPencereleri,
  gunSec,
  ilceBolgeFiltrele,
  kayitAktifMi,
  konumAdlariniBul,
  ozetle,
  tarihCoz,
  tarihMetni,
  tumKayitlar,
  type CihazKonumu,
  type NobetKaydi,
  type SistemVerisi,
} from '@/veri/nobet'

const kayit = (bolge: string, bolgeId: string, bas: string, bit: string, eczane = 'ECZANE'): NobetKaydi => ({
  eczane,
  tel: '0262 000 00 00',
  adres: 'TEST',
  adres_tarifi: '',
  bolge,
  ilce: 'ÇAYIROVA',
  bolgeId,
  ilceId: '1001',
  start: bas,
  end: bit,
})

const veri = (gunler: Record<string, NobetKaydi[]>): SistemVerisi => {
  const nobetler: Record<string, unknown> = {}
  for (const [anahtar, kayitlar] of Object.entries(gunler)) {
    nobetler[anahtar] = {
      '1001': kayitlar.map((k) => ({ [String(k.bolgeId)]: [k] })),
    }
  }
  return { Nobetler: nobetler, Yayinlar: {} }
}

const CAYIROVA = veri({
  T20261014: [
    kayit('Çayırova 1.Bölge', '2001', '14/10/2026 08:30', '15/10/2026 08:30', 'İBRAHİM'),
    kayit('Çayırova 2.Bölge', '2002', '14/10/2026 08:30', '14/10/2026 23:59', 'YÜKSEL'),
  ],
})

const konum: CihazKonumu = { ilceId: '1001', bolgeId: '2002', bulundu: true }
const an = (metin: string) => tarihCoz(metin)!

describe('tarihCoz / tarihMetni', () => {
  it('kiosk biçimini ve ISO biçimini çözer', () => {
    expect(tarihMetni('14/10/2026 08:30:00')).toBe('14.10.26 08:30:00')
    expect(tarihMetni('2026-10-14T08:30:00')).toBe('14.10.26 08:30:00')
    expect(tarihCoz('bozuk')).toBeNull()
    expect(tarihCoz('')).toBeNull()
    expect(tarihCoz(undefined)).toBeNull()
  })
})

describe('biten nöbet listeden düşer (kullanıcı bildirimi)', () => {
  const beklentiler: Array<[string, string[]]> = [
    ['2026-10-14T08:30', ['Çayırova 1.Bölge', 'Çayırova 2.Bölge']],
    ['2026-10-14T22:00', ['Çayırova 1.Bölge', 'Çayırova 2.Bölge']],
    ['2026-10-14T23:58', ['Çayırova 1.Bölge', 'Çayırova 2.Bölge']],
    ['2026-10-14T23:59', ['Çayırova 1.Bölge']], // 23:59'da biten nöbet düştü
    ['2026-10-15T00:30', ['Çayırova 1.Bölge']], // gece: 08:30'a kadar süren nöbet
    ['2026-10-15T08:29', ['Çayırova 1.Bölge']],
  ]
  it.each(beklentiler)('%s → %j', (zaman, beklenen) => {
    const sonuc = gosterilecekKayitlar(CAYIROVA, konum, an(zaman))
    expect(sonuc.kayitlar.map((k) => k.bolge)).toEqual(beklenen)
  })

  it('penceresi okunamayan kayıt gizlenmez', () => {
    expect(kayitAktifMi({ eczane: 'X' }, an('2026-10-15T02:00'))).toBe(true)
    expect(kayitAktifMi({ start: 'bozuk', end: 'bozuk' }, an('2026-10-15T02:00'))).toBe(true)
  })

  it('hiç aktif kayıt kalmazsa blok olduğu gibi gösterilir', () => {
    const kayitlar = [kayit('B', '9', '01/01/2020 08:30', '02/01/2020 08:30')]
    expect(aktifKayitlar(kayitlar, an('2026-10-15T02:00'))).toEqual(kayitlar)
  })
})

describe('blok penceresi = birleşim', () => {
  it('kısa nöbet bloğun tamamını temsil etmez', () => {
    const p = gunPencereleri(CAYIROVA)[0]
    expect(p.bas?.getHours()).toBe(8)
    expect(p.bit?.getDate()).toBe(15) // 15/10 08:30 (en geç bitiş)
  })

  it('ilk kayıt kısa olsa da gün bloğu doğru seçilir', () => {
    const ters = veri({
      T20261014: [
        kayit('Kısa', '2001', '14/10/2026 08:30', '14/10/2026 23:59'),
        kayit('Uzun', '2002', '14/10/2026 08:30', '15/10/2026 08:30'),
      ],
    })
    const secim = gunSec(ters, an('2026-10-15T02:00'))
    expect(secim.anahtar).toBe('T20261014')
    expect(secim.kaynak).toBe('aktif pencere')
  })
})

describe('gün seçimi geri düşme yolları', () => {
  const gecmis = veri({ T20261010: [kayit('B', '2001', '10/10/2026 08:30', '11/10/2026 08:30')] })
  const gelecek = veri({ T20261020: [kayit('B', '2001', '20/10/2026 08:30', '21/10/2026 08:30')] })

  it('şu anki pencere yoksa en son biten gün gösterilir (yanlış güne atlanmaz)', () => {
    const secim = gunSec(gecmis, an('2026-10-15T02:00'))
    expect(secim.anahtar).toBe('T20261010')
    expect(secim.kaynak).toContain('en son biten')
  })

  it('hepsi gelecekteyse en yakın başlayacak gün gösterilir', () => {
    const secim = gunSec(gelecek, an('2026-10-15T02:00'))
    expect(secim.anahtar).toBe('T20261020')
    expect(secim.kaynak).toBe('henüz başlamamış')
  })

  it('veri yoksa boş döner', () => {
    expect(gunSec({}, new Date()).anahtar).toBe('')
    expect(gunSec(null, new Date()).anahtar).toBe('')
  })
})

describe('kapsam (ilçe/bölge) ve yardımcılar', () => {
  it('ilçe kapsamı ilçedeki tüm bölgeleri getirir, bölge kapsamı yalnızca kendini', () => {
    const blok = (CAYIROVA.Nobetler as Record<string, unknown>).T20261014
    expect(ilceBolgeFiltrele(blok, konum, 'ilce').length).toBe(2)
    const tek = ilceBolgeFiltrele(blok, konum, 'bolge')
    expect(tek.map((k) => k.bolge)).toEqual(['Çayırova 2.Bölge'])
  })

  it('konum adları veriden bulunur', () => {
    const bulunan = konumAdlariniBul(CAYIROVA, konum)
    expect(bulunan.ilce).toBe('ÇAYIROVA')
    expect(bulunan.bolge).toBe('Çayırova 2.Bölge')
    expect(bulunan.bulundu).toBe(true)
  })

  it('veri özeti ve gün etiketi', () => {
    const ozet = ozetle(CAYIROVA)
    expect(ozet.gunSayisi).toBe(1)
    expect(ozet.kayitSayisi).toBe(2)
    expect(ozet.ilceSayisi).toBe(1)
    expect(ozet.bolgeSayisi).toBe(2)
    expect(ozet.geciciMi).toBe(false)
    expect(gunEtiketi('T20261015')).toBe('15.10.2026')
    expect(gunEtiketi('bilinmeyen')).toBe('bilinmeyen')
  })

  it('tüm kayıtlar ağaçtan toplanır', () => {
    expect(tumKayitlar(CAYIROVA).map((k) => k.eczane)).toEqual(['İBRAHİM', 'YÜKSEL'])
  })
})
