/**
 * Yayın hedefleme (ilçe/bölge/cihaz) — Qt `core/yayin_kapsam.py` ile BİREBİR aynı kurallar.
 *
 * Alanlar isteğe bağlı; boş = kısıt yok (mevcut veri böyle çalışmaya devam eder).
 * Eşleşmeyen cihaz yayını havuzuna bile almaz → indirmez, önbelleğe almaz.
 */
import { describe, expect, it } from 'vitest'

import { aktifYayinlar, kapsamUygun, yayinKapsami, type YayinKaydi } from '@/veri/yayin'

const ILCE = '30607352906750376'
const BOLGE = '73154087615041151'
const CIHAZ = '98273648723468273'

const yayin = (ek: Partial<YayinKaydi> = {}): YayinKaydi => ({
  start: '2026-10-24T08:30:00',
  end: '2026-10-24T23:59:00',
  contentUrl: 'https://ornek.example/a.webp',
  duration: 30,
  ...ek,
})

describe('yayinKapsami', () => {
  it('alias alanları okur', () => {
    expect(yayinKapsami({ ilce_id: 'X' }).ilceId).toBe('X')
    expect(yayinKapsami({ clientID: 'Y' }).cihazId).toBe('Y')
  })

  it('boş kayıt → kısıt yok', () => {
    expect(yayinKapsami({})).toEqual({ ilceId: '', bolgeId: '', cihazId: '' })
    expect(yayinKapsami(null)).toEqual({ ilceId: '', bolgeId: '', cihazId: '' })
  })
})

describe('kapsamUygun', () => {
  const cihaz = { ilceId: ILCE, bolgeId: BOLGE, cihazId: CIHAZ }

  it('kapsamsız yayın her cihazda', () => {
    expect(kapsamUygun(yayin(), cihaz)).toBe(true)
    expect(kapsamUygun(yayin(), { ilceId: 'x', bolgeId: 'y', cihazId: 'z' })).toBe(true)
  })

  it('ilçe eşleşmesi', () => {
    expect(kapsamUygun(yayin({ ilceId: ILCE }), cihaz)).toBe(true)
    expect(kapsamUygun(yayin({ ilceId: 'diger' }), cihaz)).toBe(false)
  })

  it('bölge eşleşmesi', () => {
    expect(kapsamUygun(yayin({ bolgeId: BOLGE }), cihaz)).toBe(true)
    expect(kapsamUygun(yayin({ bolgeId: 'diger' }), cihaz)).toBe(false)
  })

  it('cihaz en dar kapsam', () => {
    expect(kapsamUygun(yayin({ cihazId: CIHAZ }), cihaz)).toBe(true)
    expect(kapsamUygun(yayin({ cihazId: 'baska' }), cihaz)).toBe(false)
  })

  it('birden fazla alan → VE', () => {
    const y = yayin({ ilceId: ILCE, bolgeId: BOLGE })
    expect(kapsamUygun(y, cihaz)).toBe(true)
    expect(kapsamUygun(y, { ...cihaz, bolgeId: 'diger' })).toBe(false)
  })

  it('boş/whitespace alan kısıt saymaz', () => {
    expect(kapsamUygun(yayin({ ilceId: '  ', bolgeId: '' }), cihaz)).toBe(true)
  })
})

describe('aktifYayinlar + kapsam', () => {
  const veri = {
    Yayinlar: {
      '1': yayin({ contentUrl: 'https://ornek.example/genel.webp' }),
      '2': yayin({ contentUrl: 'https://ornek.example/ilce.webp', ilceId: ILCE }),
      '3': yayin({ contentUrl: 'https://ornek.example/baska.webp', ilceId: '999' }),
      '4': yayin({ contentUrl: 'https://ornek.example/cihaz.webp', cihazId: CIHAZ }),
    },
  }
  const an = new Date(2026, 9, 24, 12, 0, 0)

  it('bu cihazın göreceği yayınlar', () => {
    const aktif = aktifYayinlar(veri, an, 20, { ilceId: ILCE, bolgeId: BOLGE, cihazId: CIHAZ })
    expect(aktif.map((y) => y.contentUrl)).toEqual([
      'https://ornek.example/genel.webp',
      'https://ornek.example/ilce.webp',
      'https://ornek.example/cihaz.webp',
    ])
  })

  it('başka ilçe cihazı kendi yayınını görür, ilçe-1 yayınını görmez', () => {
    const aktif = aktifYayinlar(veri, an, 20, { ilceId: '999', bolgeId: 'b', cihazId: 'c' })
    expect(aktif.map((y) => y.contentUrl)).toEqual([
      'https://ornek.example/genel.webp',
      'https://ornek.example/baska.webp',
    ])
  })

  it('kapsam bilinmiyorsa hedefli yayınlar GÖSTERİLMEZ (fail-closed)', () => {
    // Cihaz ilçesini okuyamadıysa (match.json yok) yanlış bölgenin afişini basmaktansa hiç basmamak
    // doğrudur; yalnız kapsamsız ("tüm cihazlar") yayın görünür.
    const aktif = aktifYayinlar(veri, an, 20)
    expect(aktif.map((y) => y.contentUrl)).toEqual(['https://ornek.example/genel.webp'])
  })
})
