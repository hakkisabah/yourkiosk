/**
 * Şema testleri — panelin doğrulama kuralları kiosk ile aynı olmalı.
 * Şema `kiosk/ayarlar.py`'den üretilir (`kiosk/tools/sema_disa_aktar.py`).
 */
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { dogrula, gruplar, kapsamAnahtarlari, kapsamGruplari, tanim, tumAnahtarlar, varsayilanBelge } from './sema'

const okuJson = (yol: string): Record<string, unknown> =>
  JSON.parse(readFileSync(new URL(yol, import.meta.url), 'utf8')) as Record<string, unknown>

describe('sema', () => {
  it('kiosk şemasından üretilmiş ve dolu', () => {
    expect(gruplar.map((g) => g.ad)).toEqual(["ozellikler", "kusak", "gorunum", "veri", "ag", "gelismis", "onbellek", "tetik", "calistirma"])
    expect(tumAnahtarlar.length).toBeGreaterThanOrEqual(52)
    expect(kapsamGruplari).toEqual(["ozellikler", "kusak", "gorunum", "gelismis", "onbellek"])
  })

  it('kapsam anahtarları yalnızca kapsam gruplarından gelir', () => {
    expect(kapsamAnahtarlari.every((a) => kapsamGruplari.includes(a.tam.split('.')[0]))).toBe(true)
    expect(tanim('veri.kaynak')?.tip).toBe('secim')
    expect(tanim('ag.izinli_portlar')?.tip).toBe('sayi_listesi')
  })

  it('varsayılan belge config değerlerini taşır', () => {
    const belge = varsayilanBelge()
    expect(belge.kuşak ?? belge.kusak.yazi_punto).toBe(36)
    expect(belge.ozellikler.nobet_listesi).toBe(true)
    expect(belge.gelismis.max_json_bayt).toBe(4 * 1024 * 1024)
  })
})

describe('dogrula — kiosk/ayarlar.py::_deger_dogrula ile aynı kurallar', () => {
  it('mantıksal değer', () => {
    expect(dogrula('ozellikler.kayan_yazi', true).gecerli).toBe(true)
    expect(dogrula('ozellikler.kayan_yazi', 'evet').gecerli).toBe(false)
  })

  it('tam sayı ve aralık', () => {
    expect(dogrula('kusak.yazi_punto', 36).deger).toBe(36)
    expect(dogrula('kusak.yazi_punto', '36').deger).toBe(36) // metinden sayıya
    expect(dogrula('kusak.yazi_punto', 36.7).deger).toBe(36) // tam sayıya yuvarlanır
    expect(dogrula('kusak.yazi_punto', 9999).gecerli).toBe(false)
    expect(dogrula('kusak.yazi_punto', 9999).hata).toContain('üst sınırın üstünde')
    expect(dogrula('kusak.yazi_punto', 1).hata).toContain('alt sınırın altında')
    expect(dogrula('kusak.yazi_punto', 'abc').gecerli).toBe(false)
    expect(dogrula('kusak.yazi_punto', true).gecerli).toBe(false) // bool sayı değildir
  })

  it('metin uzunluğu', () => {
    expect(dogrula('veri.dosya_adresi', '').gecerli).toBe(true)
    expect(dogrula('veri.dosya_adresi', 'x'.repeat(3000)).gecerli).toBe(false)
  })

  it('seçim listesi', () => {
    expect(dogrula('veri.kaynak', 'dosya').gecerli).toBe(true)
    expect(dogrula('veri.kaynak', 'ftp').gecerli).toBe(false)
    expect(dogrula('veri.kaynak', 'ftp').hata).toContain('şunlardan biri olmalı')
  })

  it('metin listesi ve sayı listesi', () => {
    expect(dogrula('ag.izinli_hostlar', ['a.example', 'b.example']).gecerli).toBe(true)
    expect(dogrula('ag.izinli_hostlar', ['a', '']).gecerli).toBe(false)
    expect(dogrula('ag.izinli_portlar', [443]).gecerli).toBe(true)
    expect(dogrula('ag.izinli_portlar', [443, 0]).gecerli).toBe(false)
    expect(dogrula('ag.izinli_portlar', ['443']).deger).toEqual([443])
  })

  it('bilinmeyen anahtar reddedilir', () => {
    expect(dogrula('kusak.olmayan', 1).hata).toContain('bilinmeyen anahtar')
  })

  it('5 MB JSON sınırı varsayılanla reddedilir, gelişmiş ayarla kabul edilir (kullanıcı senaryosu)', () => {
    const varsayilan = tanim('gelismis.max_json_bayt')!.varsayilan as number
    expect(dogrula('gelismis.max_json_bayt', 5 * 1024 * 1024).gecerli).toBe(true) // sınır yükseltilebilir
    expect(varsayilan).toBe(4 * 1024 * 1024)
    expect(dogrula('gelismis.max_json_bayt', 33_554_432).deger).toBe(33_554_432) // 32 MB (20-30 MB senaryosu)
    expect(dogrula('gelismis.max_json_bayt', 1024 * 1024 * 1024).gecerli).toBe(false) // üst sınır 512 MB
  })
})

describe('örnek dosyalar panelden geçerli olmalı (kiosk ile aynı dosyalar)', () => {
  it('kiosk/ayarlar.ornek.json', () => {
    const ornek = okuJson('../../../kiosk/ayarlar.ornek.json')
    for (const [grup, icerik] of Object.entries(ornek)) {
      if (grup.startsWith('_') || typeof icerik !== 'object' || !icerik) continue
      for (const [anahtar, deger] of Object.entries(icerik as Record<string, unknown>)) {
        if (anahtar.startsWith('_')) continue // yorum anahtarları doğrulanmaz
        const sonuc = dogrula(`${grup}.${anahtar}`, deger)
        expect(sonuc.gecerli, `${grup}.${anahtar} → ${sonuc.hata ?? ''}`).toBe(true)
      }
    }
  })

  it('kiosk/kapsam-ayarlari.ornek.json', () => {
    const ornek = okuJson('../../../kiosk/kapsam-ayarlari.ornek.json')
    const kapsamlar: Array<Record<string, unknown>> = [
      ornek.varsayilan as Record<string, unknown>,
      ...Object.values((ornek.ilceler ?? {}) as Record<string, Record<string, unknown>>),
      ...Object.values((ornek.bolgeler ?? {}) as Record<string, Record<string, unknown>>),
      ...Object.values((ornek.cihazlar ?? {}) as Record<string, Record<string, unknown>>),
    ].filter(Boolean)
    for (const kapsam of kapsamlar) {
      for (const [grup, icerik] of Object.entries(kapsam)) {
        for (const [anahtar, deger] of Object.entries(icerik as Record<string, unknown>)) {
          const sonuc = dogrula(`${grup}.${anahtar}`, deger)
          expect(sonuc.gecerli, `${grup}.${anahtar} → ${sonuc.hata ?? ''}`).toBe(true)
        }
      }
    }
  })
})
