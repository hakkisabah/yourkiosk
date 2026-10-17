/**
 * CSS ÖLÇÜ DEĞİŞKENLERİ testleri — "hiç hata vermeyen siyah ekran" sınıfını kilitler.
 *
 * KÖK NEDEN: `yerlesim.json` değerleri Qt'den **sayı** olarak gelir (1080, 208, 3…).
 * CSS'e birimsiz yazılırsa (`--ekran-y: 1080`) `height: var(--ekran-y)` **geçersiz**
 * olur ("invalid at computed-value time") ve özellik ilk değerine düşer → `height: auto`.
 * Sahnenin çocukları `position: absolute` olduğu için yükseklik **0** olur, arkadaki
 * siyah `body` görünür: konsolda hata YOK, ekran siyah. Bu test o hatayı imkânsız kılar.
 */
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { cssDegiskenleriniUygula } from '@/stiller/olcu'

/** `setProperty` çağrılarını toplayan sahte kök (node ortamı; DOM gerekmez). */
function sahteKok(): { kok: HTMLElement; yazilan: Record<string, string> } {
  const yazilan: Record<string, string> = {}
  const kok = {
    style: {
      setProperty: (ad: string, deger: string): void => {
        yazilan[ad] = deger
      },
    },
  } as unknown as HTMLElement
  return { kok, yazilan }
}

describe('CSS ölçü değişkenleri (birim zorunluluğu)', () => {
  const { kok, yazilan } = sahteKok()
  const uretilen = cssDegiskenleriniUygula(kok)

  it('üretilen değerler köke birebir yazılır', () => {
    expect(yazilan).toEqual(uretilen)
    expect(Object.keys(uretilen).length).toBeGreaterThan(30)
  })

  it('BİRİMSİZ sayı üretilmez (siyah ekranın kök nedeni)', () => {
    for (const [ad, deger] of Object.entries(uretilen)) {
      expect(deger, `${ad} birimsiz sayı: height/width geçersiz olur → siyah ekran`).not.toMatch(
        /^-?\d+(\.\d+)?$/,
      )
    }
  })

  it('uzunluk ve punto değişkenleri birim taşır', () => {
    const uzunluklar = [
      '--ekran-g',
      '--ekran-y',
      '--sol-genislik',
      '--sag-genislik',
      '--satir-yuksekligi',
      '--viewport-yuksekligi',
      '--logo-genislik',
      '--saat-kutusu',
      '--kusak-y',
      '--dikey-cizgi',
      '--satir-bosluk',
      '--sol-ic-bosluk',
      '--serit-yukseklik',
      '--tarih-aralik-yuksekligi',
      '--detay-yuksekligi',
      '--yatay-cizgi',
      '--alt-serit-yuksekligi',
      '--kusak-yukseklik',
      '--kaydirma-genislik',
      '--punto-sol-ad',
      '--punto-sol-ikincil',
      '--punto-orta-ad',
      '--punto-adres',
      '--punto-telefon',
      '--punto-saat',
      '--punto-tarih-aralik',
      '--kusak-punto',
    ]
    for (const ad of uzunluklar) {
      expect(uretilen[ad], `${ad} px ile bitmeli`).toMatch(/^-?\d+(\.\d+)?px$/)
    }
    // Qt referans değerleri (yerlesim.json → 1080p sahne, 5 satır × 208 px)
    expect(uretilen['--ekran-y']).toBe('1080px')
    expect(uretilen['--ekran-g']).toBe('1920px')
    expect(uretilen['--satir-yuksekligi']).toBe('208px')
    expect(uretilen['--sol-genislik']).toBe('499px')
    expect(uretilen['--dikey-cizgi']).toBe('3px')
    // süre ve renkler px almaz
    expect(uretilen['--animasyon-ms']).toBe('1800ms')
    expect(uretilen['--kirmizi']).toMatch(/^#/)
    expect(uretilen['--kutu-normal']).toMatch(/^url\('\/.+\.png'\)$/)
  })

  it('CSS`te kullanılan HER var(--x) üretiliyor (tanımsız değişken de height:auto yapar)', () => {
    const css = readFileSync(new URL('../src/stiller/kiosk.css', import.meta.url), 'utf8')
    const adlar = new Set([...css.matchAll(/var\((--[a-z0-9-]+)\)/g)].map((m) => m[1]))
    expect(adlar.size, 'CSS okunamadı ya da hiç değişken kullanılmıyor').toBeGreaterThan(20)
    for (const ad of adlar) {
      expect(uretilen[ad], `CSS'te var ama üretilmiyor: ${ad}`).toBeDefined()
    }
  })
})
