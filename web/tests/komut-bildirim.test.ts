// @vitest-environment jsdom
/**
 * `/komut-bildirim` istemcisi testleri (i5 bulgusu: yoklama istemci tarafı testsizdi).
 *
 * XSS testi GERÇEK mekanizmayı kanıtlar: metin `App.vue`da enterpolasyonla (`{{ }}`) basılır,
 * `v-html` KULLANILMAZ. Önceki test yalnız "dize döndü" diyordu — iddiasını kanıtlamıyordu.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import {
  bildirimMetni,
  komutBildiriminiOku,
  VARSAYILAN_BILDIRIM,
} from '@/veri/komutBildirim'

function yanit(govde: unknown, ok = true, kod = 200): Response {
  return {
    ok,
    status: kod,
    json: async () => govde,
  } as unknown as Response
}

describe('bildirimMetni', () => {
  it('aktif bildirimde sunucunun metnini döner', () => {
    expect(bildirimMetni({ aktif: true, metin: 'Cihaz yeniden başlatılıyor…' })).toBe(
      'Cihaz yeniden başlatılıyor…',
    )
  })

  it('aktif değilse boş dize (ekranda yazı kalmaz)', () => {
    expect(bildirimMetni({ aktif: false, metin: 'yok sayılmalı' })).toBe('')
    expect(bildirimMetni(null)).toBe('')
    expect(bildirimMetni(undefined)).toBe('')
  })

  it('aktif ama metin boşsa güvenli varsayılana düşer', () => {
    expect(bildirimMetni({ aktif: true })).toBe(VARSAYILAN_BILDIRIM)
    expect(bildirimMetni({ aktif: true, metin: '   ' })).toBe(VARSAYILAN_BILDIRIM)
  })

  it('metni HTML olarak yorumlamaz — şablon enterpolasyon kullanır, `v-html` YOK', () => {
    // 1) Dize katmanı: gelen metin OLDUĞU GİBİ taşınır (kaçış yapılmaz), çünkü güvenlik
    //    basıldığı yerde Vue enterpolasyonundadır — burada HTML'e çevrilmez.
    const metin = bildirimMetni({ aktif: true, metin: '<img src=x onerror=alert(1)>' })
    expect(metin).toBe('<img src=x onerror=alert(1)>')

    // 2) Gerçek DOM: enterpolasyonla basılan metin ELEMAN ÜRETMEZ (textContent semantiği).
    const kap = document.createElement('div')
    kap.textContent = metin
    document.body.appendChild(kap)
    expect(kap.querySelector('img')).toBeNull()
    expect(kap.childElementCount).toBe(0)
    expect(kap.textContent).toBe('<img src=x onerror=alert(1)>')
    kap.remove()

    // 3) Şablon kanıtı: App.vue bildirimi çift süslü parantezle basıyor, v-html geçmiyor.
    // (jsdom ortamında `import.meta.url` file: şemasında değil → cwd'den okunur.)
    const sablon = readFileSync(resolve(process.cwd(), 'src/App.vue'), 'utf-8')
    expect(sablon).toContain('{{ komutBildirimi }}')
    expect(sablon).not.toContain('v-html')
  })
})

describe('komutBildiriminiOku', () => {
  it('/komut-bildirim adresini no-store ile sorar', async () => {
    const getir = vi.fn(async () => yanit({ aktif: true, metin: 'Cihaz yeniden başlatılıyor…' }))
    const metin = await komutBildiriminiOku(getir as unknown as typeof fetch)
    expect(metin).toBe('Cihaz yeniden başlatılıyor…')
    expect(getir).toHaveBeenCalledWith('/komut-bildirim', { cache: 'no-store' })
  })

  it('uç yoksa (404/503) sessizce boş döner', async () => {
    for (const kod of [404, 503]) {
      const getir = vi.fn(async () => yanit({}, false, kod))
      await expect(komutBildiriminiOku(getir as unknown as typeof fetch)).resolves.toBe('')
    }
  })

  it('ağ hatasında ekranı bozmaz (boş dize)', async () => {
    const getir = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    await expect(komutBildiriminiOku(getir as unknown as typeof fetch)).resolves.toBe('')
  })

  it('bozuk JSON gövdesinde de boş döner', async () => {
    const getir = vi.fn(async () => {
      return {
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('beklenmeyen belirteç')
        },
      } as unknown as Response
    })
    await expect(komutBildiriminiOku(getir as unknown as typeof fetch)).resolves.toBe('')
  })
})
