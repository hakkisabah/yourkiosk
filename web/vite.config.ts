/**
 * Kiosk web arayüzü (Chromium kiosk modu) — derleme yapılandırması.
 *
 * Çıktı `dist/` klasörüne yazılır; kiosk tarayıcı modunda `web/` klasörü yerel
 * sunucudan sunulur. Derleme zorunlu değildir: `index.html` + `src/` doğrudan da
 * çalışır (Vite geliştirme sunucusu ya da basit statik sunucu), ancak cihazda
 * `npm run build` ile derlenmiş sürüm kullanmak daha hızlı açılır.
 *
 * Not: göreli yol (`base: './'`) kullanılır ki arayüz hem `/` kökünden hem de
 * `dist/` alt klasöründen sunulabilsin.
 */
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  base: './',
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'chrome100',
    assetsInlineLimit: 0,
  },
  server: { host: '127.0.0.1', port: 5174, strictPort: false, fs: { allow: ['..'] } },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'tests/**/*.test.ts'],
  },
})
