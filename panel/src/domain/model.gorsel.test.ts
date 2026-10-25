/**
 * YAYIN GÖRSELİ (contentUrl) doğrulama + yazma — panelde alan düzenlenebilir olmalı.
 *
 * NEDEN: kullanıcı "Yayınlar sekmesinde değiştirebileceğim alan yok" dedi; alan yalnız
 * görüntüleniyordu. Görsel adresi panelden düzenlenebilir hâle geldi; bu test hem biçim
 * kurallarını (kiosk ile aynı uzantı listesi) hem de yazma davranışını kilitler.
 */
import { describe, expect, it } from 'vitest'

import {
  GORSEL_URL_AZAMI,
  gorselUrlHatalari,
  gorselUrlYaz,
  yayinDogrula,
  type YayinDto,
} from '@/domain/model'

const GECERLI = 'https://d2dnrvsx5eevod.cloudfront.net/yayin-gorselleri/1aef5f57384bad53.webp'

describe('gorselUrlHatalari', () => {
  it('https + desteklenen uzantı geçer', () => {
    for (const adres of [
      GECERLI,
      'https://ornek.test/a.png',
      'https://ornek.test/a.JPG',
      'https://ornek.test/a.jpeg',
      'https://ornek.test/a.webp?v=2',
      '  https://ornek.test/bosluklu.png  ',
    ]) {
      expect(gorselUrlHatalari(adres), adres).toEqual([])
    }
  })

  it('http, javascript:, data:, file: reddedilir (kiosk https indirir)', () => {
    for (const adres of [
      'http://ornek.test/a.png',
      'javascript:alert(1)//a.png',
      'data:image/png;base64,AAAA',
      'file:///etc/passwd.png',
      'ftp://ornek.test/a.png',
    ]) {
      const hatalar = gorselUrlHatalari(adres)
      expect(hatalar.length, adres).toBeGreaterThan(0)
      expect(hatalar[0]).toContain('https')
    }
  })

  it('kiosk desteklemeyen uzantılar reddedilir (gif/svg/pdf/uzantısız)', () => {
    for (const adres of [
      'https://ornek.test/a.gif',
      'https://ornek.test/a.svg',
      'https://ornek.test/a.pdf',
      'https://ornek.test/a',
      'https://ornek.test/gorsel.png.exe',
    ]) {
      const hatalar = gorselUrlHatalari(adres)
      expect(hatalar.length, adres).toBeGreaterThan(0)
      expect(hatalar[0]).toContain('webp')
    }
  })

  it('boş ve aşırı uzun adres reddedilir', () => {
    expect(gorselUrlHatalari('')[0]).toContain('boş')
    expect(gorselUrlHatalari('   ')[0]).toContain('boş')
    const uzun = 'https://ornek.test/' + 'a'.repeat(GORSEL_URL_AZAMI) + '.png'
    expect(gorselUrlHatalari(uzun)[0]).toContain('uzun')
  })
})

describe('gorselUrlYaz', () => {
  const kayit: YayinDto = {
    start: '2026-10-24T08:30:00',
    end: '2026-10-24T23:59:00',
    contentUrl: 'https://ornek.test/eski.png',
    duration: 15,
    ilceId: 'I1',
  }

  it('contentUrl güncellenir, diğer alanlar korunur', () => {
    const yeni = gorselUrlYaz(kayit, GECERLI)
    expect(yeni.contentUrl).toBe(GECERLI)
    expect(yeni.start).toBe(kayit.start)
    expect(yeni.end).toBe(kayit.end)
    expect(yeni.duration).toBe(15)
    expect(yeni.ilceId).toBe('I1')
  })

  it('eski ALIAS’lar (contentURL/url) temizlenir', () => {
    const eski: YayinDto = { ...kayit, contentURL: 'https://ornek.test/alias.png', url: 'https://ornek.test/url.png' }
    const yeni = gorselUrlYaz(eski, GECERLI)
    expect(yeni.contentURL).toBeUndefined()
    expect(yeni.url).toBeUndefined()
    expect(yeni.contentUrl).toBe(GECERLI)
  })

  it('yazılan kayıt model doğrulamasından geçer', () => {
    expect(yayinDogrula(gorselUrlYaz(kayit, GECERLI))).toEqual([])
  })

  it('boşluklar kırpılır', () => {
    expect(gorselUrlYaz(kayit, `  ${GECERLI}  `).contentUrl).toBe(GECERLI)
  })
})
