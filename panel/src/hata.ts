/**
 * Uygulama geneli hata görünürlüğü.
 *
 * Neden: bir hata oluştuğunda Vue ekranı boş bırakabiliyor (beyaz ekran) ve kullanıcı
 * ne olduğunu göremiyor. Burada toplanan hatalar `App.vue` içinde okunur bir kart
 * olarak gösterilir; kullanıcı mesajı kopyalayıp paylaşabilir.
 */
import { ref, type App } from 'vue'

export interface UygulamaHatasi {
  mesaj: string
  ayrinti?: string
  zaman: string
}

export const uygulamaHatasi = ref<UygulamaHatasi | null>(null)

function _metne(deger: unknown): string {
  if (deger instanceof Error) return deger.message || deger.name
  if (typeof deger === 'string') return deger
  try {
    return JSON.stringify(deger)
  } catch {
    return String(deger)
  }
}

/** Hatayı görünür hâle getirir (aynı hata tekrar tekrar eklenmez). */
export function hataBildir(hata: unknown, ayrinti?: unknown): void {
  const mesaj = _metne(hata)
  if (uygulamaHatasi.value?.mesaj === mesaj) return
  uygulamaHatasi.value = {
    mesaj,
    ayrinti: ayrinti === undefined ? undefined : _metne(ayrinti),
    zaman: new Date().toISOString(),
  }
  // Geliştirici için konsolda da kalsın
  console.error('[yourkiosk panel]', hata, ayrinti ?? '')
}

export function hatayiTemizle(): void {
  uygulamaHatasi.value = null
}

/** Vue ve tarayıcı düzeyindeki yakalanmamış hataları bağlar (main.ts çağırır). */
export function hataYakalayicilariKur(uygulama: App): void {
  uygulama.config.errorHandler = (hata, _ornek, bilgi) => hataBildir(hata, bilgi)
  if (typeof window !== 'undefined') {
    window.addEventListener('unhandledrejection', (olay) => hataBildir(olay.reason, 'işlenmeyen söz (promise)'))
    window.addEventListener('error', (olay) => hataBildir(olay.message, olay.filename))
  }
}
