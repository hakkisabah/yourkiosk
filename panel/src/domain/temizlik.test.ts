/**
 * Süresi geçen yayınların temizliği (S3 + cihaz) — kural testleri.
 *
 * Sözleşme:
 *  • `end` (son gösterim tarihi) geçen kayıt silinir,
 *  • `end` okunamayan kayda DOKUNULMAZ (canlı yayın silinmesin),
 *  • güvenlik payı (varsayılan 2 saat) `end`ten SONRA eklenir,
 *  • yalnızca KENDİ kovamızdaki adresler için S3 anahtarı üretilir.
 */
import { describe, expect, it } from 'vitest'

import {
  silinecekYayinlar,
  s3NesneAnahtari,
  yayinAdresi,
  yayinBitisTarihi,
  zamanDamgasi,
  VARSAYILAN_EK_SAAT,
} from './temizlik'
import type { SistemVerisi } from './veri'

const AN = new Date(2026, 9, 15, 12, 0, 0) // 15.10.2026 12:00 (yerel)

const veri = (yayinlar: Record<string, unknown>): SistemVerisi => ({
  Nobetler: { T20261015: {} },
  Yayinlar: yayinlar,
  BolgeIdleri: { 1: 'x' },
})

describe('yayinBitisTarihi / yayinAdresi', () => {
  it('end alanını okur (ISO ve Türkçe biçim)', () => {
    expect(yayinBitisTarihi({ end: '2026-10-14T15:33:00.468' })?.getDate()).toBe(14)
    expect(yayinBitisTarihi({ end: '14/10/2026 15:33' })?.getHours()).toBe(15)
  })

  it('alternatif alan adlarını da kabul eder', () => {
    expect(yayinBitisTarihi({ bitis: '14/10/2026 08:30' })).not.toBeNull()
    expect(yayinBitisTarihi({ sonGosterim: '2026-10-14T08:30:00' })).not.toBeNull()
  })

  it('tarih yoksa/bozuksa null döner', () => {
    expect(yayinBitisTarihi({})).toBeNull()
    expect(yayinBitisTarihi({ end: 'bilinmiyor' })).toBeNull()
    expect(yayinBitisTarihi(null)).toBeNull()
    expect(yayinBitisTarihi([1, 2])).toBeNull()
  })

  it('görsel adresini okur, yoksa boş döner', () => {
    expect(yayinAdresi({ contentUrl: ' https://x/y.png ' })).toBe('https://x/y.png')
    expect(yayinAdresi({ contentURL: 'https://x/z.png' })).toBe('https://x/z.png')
    expect(yayinAdresi({ url: 'https://x/w.png' })).toBe('https://x/w.png')
    expect(yayinAdresi({})).toBe('')
  })
})

describe('s3NesneAnahtari', () => {
  it('sanal host adresinden anahtarı çıkarır', () => {
    expect(s3NesneAnahtari('https://yourkiosk-veri.s3.eu-central-1.amazonaws.com/yayin/a.png', 'yourkiosk-veri')).toBe(
      'yayin/a.png',
    )
    expect(s3NesneAnahtari('https://yourkiosk-veri.s3.amazonaws.com/yayin/a.png', 'yourkiosk-veri')).toBe('yayin/a.png')
  })

  it('yol biçimi adreslerden anahtarı çıkarır', () => {
    expect(s3NesneAnahtari('https://s3.eu-central-1.amazonaws.com/yourkiosk-veri/yayin/b.png', 'yourkiosk-veri')).toBe(
      'yayin/b.png',
    )
  })

  it('başka kovanın/alan adının adresleri için null döner (nesne bizim değil)', () => {
    expect(s3NesneAnahtari('https://hakkisabah.com/api/havuzlu-bahce.png', 'yourkiosk-veri')).toBeNull()
    expect(s3NesneAnahtari('https://baska-kova.s3.eu-central-1.amazonaws.com/a.png', 'yourkiosk-veri')).toBeNull()
    expect(s3NesneAnahtari('https://s3.eu-central-1.amazonaws.com/baska-kova/a.png', 'yourkiosk-veri')).toBeNull()
    expect(s3NesneAnahtari('http://yourkiosk-veri.s3.amazonaws.com/a.png', 'yourkiosk-veri')).toBeNull()
    expect(s3NesneAnahtari('', 'yourkiosk-veri')).toBeNull()
  })

  it('ön ek dışındaki anahtarları silme kapsamına almaz', () => {
    expect(s3NesneAnahtari('https://yourkiosk-veri.s3.amazonaws.com/disi/a.png', 'yourkiosk-veri', 'kiosk/')).toBeNull()
    expect(s3NesneAnahtari('https://yourkiosk-veri.s3.amazonaws.com/kiosk/a.png', 'yourkiosk-veri', 'kiosk/')).toBe(
      'kiosk/a.png',
    )
  })
})

describe('silinecekYayinlar', () => {
  it('süresi geçenleri ayırır, diğer veriyi KORUR', () => {
    const sonuc = silinecekYayinlar(
      veri({
        1: { start: '2026-10-13T10:00:00', end: '2026-10-13T11:00:00', contentUrl: 'https://x/eski.png' },
        2: { start: '2026-10-15T11:00:00', end: '2026-10-15T23:59:00', contentUrl: 'https://x/yeni.png' },
      }),
      AN,
    )
    expect(sonuc.silinenler.map((y) => y.id)).toEqual(['1'])
    expect(Object.keys(sonuc.kalanlar.Yayinlar as object)).toEqual(['2'])
    expect(sonuc.kalanlar.Nobetler).toEqual({ T20261015: {} })
    expect(sonuc.kalanlar.BolgeIdleri).toEqual({ 1: 'x' })
    expect(sonuc.toplam).toBe(2)
  })

  it('güvenlik payı kadar bekler (end + ek saat)', () => {
    // 10:30'da biten yayın, 12:00'de pay 2 saat ise HENÜZ silinmez
    const veriTek = veri({ 1: { end: '2026-10-15T10:30:00' } })
    expect(silinecekYayinlar(veriTek, AN).silinenler).toHaveLength(0)
    // pay 1 saat olsa silinirdi
    expect(silinecekYayinlar(veriTek, AN, 1).silinenler).toHaveLength(1)
  })

  it('son gösterim tarihi okunamayan kayda dokunmaz (atlanan)', () => {
    const sonuc = silinecekYayinlar(veri({ 1: { contentUrl: 'https://x/a.png' }, 2: { end: 'yok' } }), AN)
    expect(sonuc.silinenler).toHaveLength(0)
    expect(sonuc.atlananlar).toBe(2)
    expect(Object.keys(sonuc.kalanlar.Yayinlar as object).sort()).toEqual(['1', '2'])
  })

  it('kendi kovamızdaki adresler için S3 anahtarı üretir, dış adreslerde null', () => {
    const sonuc = silinecekYayinlar(
      veri({
        1: { end: '2026-10-01T10:00:00', contentUrl: 'https://yourkiosk-veri.s3.eu-central-1.amazonaws.com/kiosk/yayin/a.png' },
        2: { end: '2026-10-01T10:00:00', contentUrl: 'https://hakkisabah.com/api/b.png' },
      }),
      AN,
      VARSAYILAN_EK_SAAT,
      'yourkiosk-veri',
      'kiosk/',
    )
    expect(sonuc.silinenler[0].anahtar).toBe('kiosk/yayin/a.png')
    expect(sonuc.silinenler[1].anahtar).toBeNull()
  })

  it('Yayinlar yoksa/boşsa güvenle çalışır', () => {
    expect(silinecekYayinlar({ Nobetler: {} }, AN).silinenler).toHaveLength(0)
    expect(silinecekYayinlar({ Yayinlar: {} }, AN).toplam).toBe(0)
    expect(silinecekYayinlar(null, AN).silinenler).toHaveLength(0)
    expect(silinecekYayinlar({ Yayinlar: [1, 2] } as unknown as SistemVerisi, AN).silinenler).toHaveLength(0)
  })

  it('girdiyi değiştirmez (saf fonksiyon)', () => {
    const girdi = veri({ 1: { end: '2026-10-01T10:00:00' } })
    const kopya = JSON.parse(JSON.stringify(girdi))
    silinecekYayinlar(girdi, AN)
    expect(girdi).toEqual(kopya)
  })
})

describe('zamanDamgasi', () => {
  it('kiosk lastupdate biçimini üretir', () => {
    expect(zamanDamgasi(new Date(2026, 9, 15, 2, 45, 40))).toBe('2026-10-15 02:45:40')
  })
})
