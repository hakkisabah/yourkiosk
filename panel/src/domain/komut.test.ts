import { describe, expect, it } from 'vitest'

import { IZINLI_KOMUTLAR, hedefMetni, komutOzeti, komutYasiSaat } from './komut'

const SIMDI = new Date('2026-10-25T12:00:00.000Z')

describe('komutOzeti — panelde son uzaktan komut', () => {
  it('geçerli imzalı komutu uyarısız gösterir', () => {
    const ozet = komutOzeti(
      {
        id: 'k-1',
        komut: 'ekrani-yenile',
        cihazId: '',
        zaman: '2026-10-25T11:55:00.000Z',
        imza: 'abc123',
      },
      'cihaz-7',
      SIMDI,
    )
    expect(ozet.varMi).toBe(true)
    expect(ozet.komut).toBe('ekrani-yenile')
    expect(ozet.hedef).toBe('')
    expect(ozet.imzali).toBe(true)
    expect(ozet.uyarilar).toEqual([])
    expect(ozet.engelYok).toBe(true)
  })

  it('dosya yoksa/nesne değilse varMi=false ve açıklama döner', () => {
    for (const ham of [null, undefined, [], 'metin']) {
      const ozet = komutOzeti(ham, '', SIMDI)
      expect(ozet.varMi).toBe(false)
      expect(ozet.uyarilar.length).toBe(1)
    }
  })

  it('beyaz liste dışı komutu, imzasız komutu ve kimliksizi uyarı olarak işaretler', () => {
    const ozet = komutOzeti({ komut: 'rm -rf /', zaman: '2026-10-25T11:00:00.000Z' }, '', SIMDI)
    expect(ozet.uyarilar.join(' | ')).toContain('beyaz listede değil')
    expect(ozet.uyarilar.join(' | ')).toContain('kimliği (id) yok')
    expect(ozet.uyarilar.join(' | ')).toContain('imza alanı yok')
    expect(ozet.engelYok).toBe(false)
  })

  it('başka cihaza gönderilmiş komutu bu cihaz için engelli gösterir', () => {
    const ozet = komutOzeti(
      { id: 'k-2', komut: 'uygulamayi-yeniden-baslat', cihazId: 'baska-cihaz', imza: 'x', zaman: '2026-10-25T11:00:00.000Z' },
      'cihaz-7',
      SIMDI,
    )
    expect(ozet.uyarilar.join(' | ')).toContain('başka cihaz için')
    expect(ozet.uyarilar.join(' | ')).not.toContain('tüm cihazlar')
  })

  it('yıldız hedef tüm cihazlar sayılır ve uyarı üretmez', () => {
    const ozet = komutOzeti(
      { id: 'k-3', komut: 'ekrani-yenile', cihazId: '*', imza: 'x', zaman: '2026-10-25T11:00:00.000Z' },
      'cihaz-7',
      SIMDI,
    )
    expect(ozet.uyarilar).toEqual([])
    expect(hedefMetni(ozet.hedef)).toBe('tüm cihazlar')
  })

  it('24 saatten eski komutu "eski" diye işaretler (cihaz tek seferlik uygular)', () => {
    const ozet = komutOzeti(
      { id: 'k-4', komut: 'ekrani-yenile', imza: 'x', zaman: '2026-10-23T10:00:00.000Z' },
      '',
      SIMDI,
    )
    expect(ozet.uyarilar.join(' | ')).toContain('saat önce gönderilmiş')
  })

  it('komut adı büyük harf/boşluklu yazılsa da normalize edilir', () => {
    const ozet = komutOzeti(
      { id: ' k-5 ', komut: ' Ekrani-Yenile ', imza: 'x', zaman: '2026-10-25T11:00:00.000Z' },
      '',
      SIMDI,
    )
    expect(ozet.komut).toBe('ekrani-yenile')
    expect(ozet.id).toBe('k-5')
    expect(ozet.uyarilar).toEqual([])
  })

  it('komut listesi cihazın beyaz listesiyle aynı', () => {
    expect([...IZINLI_KOMUTLAR]).toEqual(['yeniden-baslat', 'uygulamayi-yeniden-baslat', 'ekrani-yenile'])
  })
})

describe('komutYasiSaat', () => {
  it('geçmiş zamanı saat cinsinden verir, gelecekte 0 döner, bozuk zamanı null', () => {
    expect(komutYasiSaat('2026-10-25T10:00:00.000Z', SIMDI)).toBeCloseTo(2, 5)
    expect(komutYasiSaat('2026-10-26T10:00:00.000Z', SIMDI)).toBe(0)
    expect(komutYasiSaat('bozuk', SIMDI)).toBeNull()
  })
})
