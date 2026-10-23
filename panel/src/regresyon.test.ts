/**
 * "Beyaz ekran" regresyon kilitleri.
 *
 * Yaşanan iki gerçek olay:
 *  1. `amazon-cognito-identity-js` (crypto-js) Node'a özgü `global` nesnesini kullanıyor →
 *     tarayıcıda "Uncaught ReferenceError: global is not defined" → uygulama HİÇ mount
 *     olmuyor → bembeyaz ekran. Çözüm: `global` → `globalThis` (hem `define` hem
 *     `optimizeDeps.esbuildOptions.define`) + `index.html` içinde küçük bir güvenlik ağı.
 *  2. Vite, Vuetify bileşenlerini/AWS modüllerini ilk istekte keşfedip yeniden optimize
 *     ediyordu → sayfa kendini yeniliyordu (`504 Outdated Optimize Dep`). Çözüm:
 *     `optimizeDeps.include`/`exclude`.
 *
 * Bu testler yapılandırmanın sessizce bozulmasını engeller (dosyalar metin olarak okunur).
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const oku = (yol: string): string => readFileSync(new URL(yol, import.meta.url), 'utf8')

const VITE_CONFIG = oku('../vite.config.ts')
const INDEX_HTML = oku('../index.html')

describe('global shim (beyaz ekran koruması)', () => {
  it('vite.config uygulama kaynağı için global → globalThis tanımlar', () => {
    expect(VITE_CONFIG).toMatch(/define:\s*\{\s*global:\s*'globalThis'\s*\}/)
  })

  it('vite.config ön-derlenen bağımlılıklar için de tanımlar', () => {
    expect(VITE_CONFIG).toMatch(/esbuildOptions:\s*\{\s*define:\s*\{\s*global:\s*'globalThis'\s*\}\s*\}/)
  })

  it('index.html modül yüklenmeden ÖNCE global takma adını kurar', () => {
    const shimKonumu = INDEX_HTML.indexOf('window.global')
    const modulKonumu = INDEX_HTML.indexOf('type="module"')
    expect(shimKonumu).toBeGreaterThan(-1)
    expect(modulKonumu).toBeGreaterThan(shimKonumu)
  })
})

describe('optimizeDeps (yeniden optimizasyon koruması)', () => {
  it('Vuetify ön-derlemeden çıkarılmış (derin bileşen yolları reload tetikliyordu)', () => {
    expect(VITE_CONFIG).toMatch(/exclude:\s*\[\s*'vuetify',\s*'vuetify\/locale'\s*\]/)
  })

  it('Cognito/AWS bağımlılıkları ön-derlemeye dahil edilmiş', () => {
    for (const paket of ['amazon-cognito-identity-js', '@aws-sdk/client-s3', '@aws-sdk/client-cognito-identity']) {
      expect(VITE_CONFIG).toContain(paket)
    }
  })
})

describe('paket betikleri (dev modu)', () => {
  it('npm run dev NODE_ENV=development verir (üretim modunda dev çalışmasın)', () => {
    const pkg = JSON.parse(oku('../package.json')) as { scripts: Record<string, string> }
    expect(pkg.scripts.dev).toContain('NODE_ENV=development')
    expect(pkg.scripts.build).toContain('NODE_ENV=production')
  })
})

describe('üretim derlemesi (varsa)', () => {
  const dizin = fileURLToPath(new URL('../dist/assets', import.meta.url))

  it('HMR istemcisi, çıplak `global` ve WebSocket bulunmaz', () => {
    if (!existsSync(dizin)) return // derleme yapılmamış → atla (`npm run build`)
    const dosyalar = readdirSync(dizin).filter((ad) => ad.endsWith('.js'))
    expect(dosyalar.length).toBeGreaterThan(0)
    for (const ad of dosyalar) {
      const icerik = readFileSync(join(dizin, ad), 'utf8')
      expect(icerik, `${ad}: HMR istemcisi olmamalı`).not.toContain('@vite/client')
      // NOT: düz "WebSocket" aramak yanlış — MQTT push (wss://) meşru olarak WebSocket kullanır.
      // Aranan şey Vite'ın DEV HMR istemcisi; onu kendi işaretleriyle yakalarız.
      expect(icerik, `${ad}: dev HMR istemcisi olmamalı`).not.toContain('vite-hmr')
      expect(icerik, `${ad}: dev HMR ping'i olmamalı`).not.toContain('__vite_ping')
      expect(icerik, `${ad}: import.meta.hot kalmamalı`).not.toContain('import.meta.hot')
      const ciplakGlobal = icerik.match(/(^|[^A-Za-z0-9_$.])global\.[A-Za-z_$]/g)
      expect(ciplakGlobal, `${ad}: global globalThis'e çevrilmeli`).toBeNull()
    }
  })
})
