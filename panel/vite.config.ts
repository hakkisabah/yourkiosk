import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'
import vuetify from 'vite-plugin-vuetify'

// Vuetify bileşenleri (otomatik içe aktarma) ve AWS SDK modülleri ancak ilk istekte
// keşfedilir. Ön-derlemeye (optimizeDeps) alınmazsa Vite birkaç yüz ms sonra
// "optimized dependencies changed. reloading" der, sayfa kendini yeniden yükler ve
// tarayıcıda geçici olarak BOŞ (beyaz) ekran + `504 Outdated Optimize Dep` hataları
// görülür. Bu liste o davranışı önler; yeni bir bağımlılık eklerseniz buraya da ekleyin.
const ON_DERLEME = [
  'vue',
  'vue-router',
  'pinia',
  '@aws-sdk/client-s3',
  '@aws-sdk/client-cognito-identity',
  '@aws-sdk/credential-provider-cognito-identity',
  'amazon-cognito-identity-js',
]

export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // amazon-cognito-identity-js (crypto-js üzerinden) Node'a özgü `global` nesnesini
  // kullanır; tarayıcıda bulunmadığı için modül değerlendirilirken
  // "Uncaught ReferenceError: global is not defined" atar ve uygulama HİÇ mount olmaz
  // (belirti: bembeyaz ekran + konsolda /node_modules/.vite/deps/amazon-cognito-identity-js.js).
  // `global`'i tarayıcının `globalThis`ine eşliyoruz. İki tanım gerekir:
  //   • define                    → uygulama kaynağı ve ÜRETİM derlemesi için
  //   • optimizeDeps.esbuildOptions → ön-derlenen bağımlılıklar (dev) için
  define: { global: 'globalThis' },
  optimizeDeps: {
    include: ON_DERLEME,
    // Vuetify bileşenleri DERİN yollardan (`vuetify/components/VCard` gibi) ve istek
    // anında içe aktarılır; ön-derlemeye alınamadıkları için Vite her yeni bileşende
    // yeniden optimize edip sayfayı yeniliyordu (beyaz ekran + `504 Outdated Optimize Dep`).
    // Vuetify'ı ön-derlemeden çıkarınca bu döngü tamamen biter (kaynak ESM olarak servis edilir).
    // NOT: `include` içine vuetify'ın bir alt yolu yazılamaz (esbuild "entry point cannot be
    // marked as external" hatası verir) — bu yüzden hem 'vuetify' hem 'vuetify/locale' dışlanır.
    exclude: ['vuetify', 'vuetify/locale'],
    esbuildOptions: { define: { global: 'globalThis' } },
  },
  // Kapsam/durum testleri kiosk tarafındaki ORTAK test verisini okur
  server: { fs: { allow: ['..'] } },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
