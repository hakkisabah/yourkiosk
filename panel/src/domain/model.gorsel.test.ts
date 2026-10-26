/**
 * YAYIN GÖRSELİ (contentUrl) doğrulama + yazma — panelde alan düzenlenebilir olmalı.
 *
 * NEDEN: kullanıcı "Yayınlar sekmesinde değiştirebileceğim alan yok" dedi; alan yalnız
 * görüntüleniyordu. Görsel adresi panelden düzenlenebilir hâle geldi; bu test hem biçim
 * kurallarını (cihazın GERÇEK kuralları: https + kimlik bilgisi yok + 443 + içerik türü) hem de
 * yazma davranışını kilitler.
 */
import { readFileSync } from 'node:fs'

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

  it('cihazın gösteremeyeceği biçimler reddedilir (gif/svg/pdf)', () => {
    for (const adres of [
      'https://ornek.test/a.gif',
      'https://ornek.test/a.svg',
      'https://ornek.test/a.pdf',
      'https://ornek.test/gorsel.png.exe',
    ]) {
      const hatalar = gorselUrlHatalari(adres)
      expect(hatalar.length, adres).toBeGreaterThan(0)
      expect(hatalar[0], adres).toContain('png/jpeg/webp')
    }
  })

  it('UZANTISIZ adres kabul edilir (cihaz içerik türüne bakar, dosya adına bakmaz)', () => {
    // i3 bulgusu: panel uzantısız https adresini reddediyordu; cihaz kabul ediyor → doğru adres engelleniyordu.
    for (const adres of ['https://ornek.test/a', 'https://ornek.test/api/gorsel?id=3']) {
      expect(gorselUrlHatalari(adres), adres).toEqual([])
    }
  })

  it('kullanıcı bilgisi ve 443 dışı port reddedilir (cihaz reddeder — sessiz kalmayalım)', () => {
    for (const adres of [
      'https://kullanici:parola@ornek.test/a.png',
      'https://ornek.test:8443/a.png',
      'https://ornek.test:80/a.png',
    ]) {
      expect(gorselUrlHatalari(adres).length, adres).toBeGreaterThan(0)
    }
    expect(gorselUrlHatalari('https://ornek.test:443/a.png')).toEqual([])
  })

  it('hata metni adresi geri basmaz (kimlik bilgisi ekrana sızmasın)', () => {
    const parola = 'cok-gizli-parola'
    const hatalar = gorselUrlHatalari(`https://kullanici:${parola}@ornek.test/a.png`)
    expect(hatalar.join(' ')).not.toContain(parola)
    expect(hatalar.join(' ')).not.toContain('kullanici:')
  })

  it('yerel/özel host reddedilir (cihaz herkese açık host ister — 26 Ekim i5 bulgusu)', () => {
    for (const adres of [
      'https://127.0.0.1/a.png',
      'https://localhost/a.png',
      'https://10.0.0.5/a.png',
      'https://172.16.0.9/a.png',
      'https://192.168.1.20/a.png',
      'https://169.254.1.1/a.png',
      'https://[::1]/a.png',
      'https://[fd00::1]/a.png',
      'https://kiosk.local/a.png',
      'https://sunucu/a.png',          // nokta yok → yerel ad
      'https://nas.internal/a.png',
      // Sondaki nokta: cihaz `rstrip('.')` uygular, panel uygulamazsa parite bozulur (i3 bulgusu).
      'https://localhost./a.png',
      'https://127.0.0.1./a.png',
      'https://kiosk.local./a.png',
      // Ayrılmış aralıklar ve IPv4-mapped IPv6 loopback (i5 bilgi bulgusu).
      'https://192.0.0.8/a.png',
      'https://198.18.0.1/a.png',
      'https://198.51.100.7/a.png',
      'https://203.0.113.9/a.png',
      'https://100.64.0.1/a.png',
      'https://[::ffff:127.0.0.1]/a.png',
    ]) {
      const hatalar = gorselUrlHatalari(adres)
      expect(hatalar.length, adres).toBeGreaterThan(0)
      expect(hatalar[0], adres).toContain('herkese açık')
    }
  })

  it('genel adresler ve genel IP host denetiminden geçer', () => {
    for (const adres of [
      GECERLI,
      'https://ornek.test/a.png',
      'https://8.8.8.8/a.png',
      'https://172.32.0.1/a.png',      // 172.16/12 DIŞINDA → genel
      'https://[2a00:1450:4001::1]/a.png',
    ]) {
      expect(gorselUrlHatalari(adres), adres).toEqual([])
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

  it('eski ALIAS’ların HEPSİ (contentURL/url/gorsel) temizlenir', () => {
    // i3 bulgusu: dördüncü alias `gorsel` kayıtta kalıyordu; belge "eski alias'lar temizlenir" diyordu.
    const eski = {
      ...kayit,
      contentURL: 'https://ornek.test/alias.png',
      url: 'https://ornek.test/url.png',
      gorsel: 'https://ornek.test/gorsel.png',
    } as YayinDto
    const yeni = gorselUrlYaz(eski, GECERLI)
    expect(yeni.contentURL).toBeUndefined()
    expect(yeni.url).toBeUndefined()
    expect((yeni as Record<string, unknown>)['gorsel']).toBeUndefined()
    expect(yeni.contentUrl).toBe(GECERLI)
  })

  it('yazılan kayıt model doğrulamasından geçer', () => {
    expect(yayinDogrula(gorselUrlYaz(kayit, GECERLI))).toEqual([])
  })

  it('boşluklar kırpılır', () => {
    expect(gorselUrlYaz(kayit, `  ${GECERLI}  `).contentUrl).toBe(GECERLI)
  })
})

describe('docstring ↔ tüketici paritesi (i3 bulgusu)', () => {
  // i3: "cihaz url alanını HİÇ okumaz" yanlışı belgeden silinmişti ama model.ts yorumunda duruyordu;
  // yeni kiosk testi yalnız belgeyi koruyordu. Bu test YORUMU tüketici listesine bağlar:
  // tarayıcı modu `url`ü okuyorsa panel yorumu bunu yazmak zorunda.
  const oku = (yol: string) => readFileSync(new URL(yol, import.meta.url), 'utf8')

  it('model.ts yorumu url alanını "hiç okunmaz" diye nitelemez', () => {
    const kaynak = oku('./model.ts')
    expect(kaynak).not.toMatch(/url`?\s*ve\s*`?gorsel`?\s*alanlarını cihaz\s+HİÇ okumaz/)
    expect(kaynak).toMatch(/`?url`?[^\n]*ÜÇÜNCÜ yedek/)
  })

  it('tarayıcı modu adres alanları yorumda anlatılanla aynı', () => {
    const kaynak = oku('./model.ts')
    const yayin = oku('../../../web/src/veri/yayin.ts')
    const alanlar = /ADRES_ALANLARI\s*=\s*\[([^\]]+)\]/.exec(yayin)?.[1] ?? ''
    // web tarafında `url` varsa panel yorumu tarayıcı sırasını yazmalı
    if (alanlar.includes("'url'")) {
      expect(kaynak).toContain('contentUrl → contentURL → url')
    }
  })

  it('belgedeki MQTT↔yoklama süre eşlemesi ters değil (i5 bulgusu)', () => {
    const belge = oku('../../../docs/GORSEL-MIMARISI.md')
    // Doğru eşleme: MQTT YOK → 30 sn yoklama; MQTT BAĞLI → 120 sn emniyet ağı (anlıklık push'tan).
    if (belge.includes('MQTT yoksa')) {
      expect(belge).toContain('en geç **30 sn**')
      expect(belge).toContain("120 sn'lik emniyet ağı")
      expect(belge).not.toContain('30–120 sn')
    }
  })
})
