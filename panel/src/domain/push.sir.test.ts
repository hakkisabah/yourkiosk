/**
 * i5 BULGU 1 (statik kilit) — `VITE_MQTT_PAROLA` PANEL KAYNAK AĞACINA geri dönemez.
 *
 * NEDEN AYRI DOSYA: Vite `VITE_*` değişkenlerini derleme anında JS paketine LİTERAL yazar.
 * Panel paketi CloudFront'tan kimlik doğrulaması olmadan indirildiği için `VITE_MQTT_PAROLA`
 * kullanmak yayın parolasını herkese açık `index-*.js` içine gömmek demekti (deploy/README.md
 * §4 bunun YAPILMADIĞINI söylüyordu → belge/kod çelişkisi). Parola artık oturumda soruluyor
 * (`push.ts` → sessionStorage). Bu test, dosya taramasıyla paket kaynağında sır kalıntısı
 * bırakılmadığını kilitler; davranış testi `push.test.ts` içinde.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const PANEL_KOK = new URL('../..', import.meta.url).pathname

/** Kaynak ağacındaki metin dosyaları (node_modules/dist HARİÇ). */
function kaynakDosyalar(dizin: string): string[] {
  const bulunan: string[] = []
  for (const ad of readdirSync(dizin)) {
    if (ad === 'node_modules' || ad === 'dist' || ad === '.git') continue
    const yol = join(dizin, ad)
    if (statSync(yol).isDirectory()) {
      bulunan.push(...kaynakDosyalar(yol))
    } else if (/\.(ts|vue|js|html|sh)$/.test(ad) && !ad.endsWith('.test.ts')) {
      bulunan.push(yol)
    }
  }
  return bulunan
}

describe('i5/1 — paket kaynağında gömülü MQTT parolası yok', () => {
  it('src/ ve index.html içinde VITE_MQTT_PAROLA geçmez', () => {
    const dosyalar = [
      ...kaynakDosyalar(join(PANEL_KOK, 'src')),
      join(PANEL_KOK, 'index.html'),
      join(PANEL_KOK, '.env.ornek'),
    ]
    const kacak = dosyalar.filter((yol) => readFileSync(yol, 'utf-8').includes('VITE_MQTT_PAROLA'))
    expect(kacak).toEqual([])
  })

  it('parola kalıcı depoya yazılmıyor (localStorage geçmez)', () => {
    const metin = readFileSync(join(PANEL_KOK, 'src', 'domain', 'push.ts'), 'utf-8')
    expect(metin).not.toMatch(/localStorage\.setItem/)
    expect(metin).not.toMatch(/localStorage\[/)
    expect(metin).toContain('sessionStorage')
  })
})
