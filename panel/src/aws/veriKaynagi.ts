/**
 * Kimlik/veri erişim modu — panel iki modu destekler (bkz. MAALIYET.md):
 *
 *   cognito (varsayılan) : Cognito User Pool + Identity Pool → GEÇİCİ AWS anahtarı → S3 doğrudan
 *   lambda               : Cognito YOK → Lambda + HttpOnly cookie → PRESIGNED S3 URL'leri
 *
 * Her iki modda da panel ekranları ve doğrulamalar aynıdır; yalnızca veri erişimi değişir.
 */

import type { AuthModu } from './config'

/** Kimlik modu tipi (bkz. config.ts / MAALIYET.md). */
export type { AuthModu }

export interface LambdaIstek {
  dosya: string
  islem: 'oku' | 'yaz'
  etag?: string
  boyut?: number
}

export interface LambdaYanit<T> {
  veri: T
  etag?: string
  boyut?: number
  sonDegisiklik?: string
  anahtar: string
}

/** Nesne bu arada değiştiyse fırlatılır (koşullu okuma 412 döndü). */
export class EtagUyusmazligi extends Error {
  constructor(dosya: string) {
    super(
      `${dosya} siz düzenlerken değişmiş (başka bir panel/otomasyon yazmış olabilir). ` +
        'Kaydetmek için sayfayı yenileyip değişiklikleri yeniden uygulayın.',
    )
    this.name = 'EtagUyusmazligi'
  }
}

export interface DosyaBilgisi {
  ad: string
  anahtar: string
  varMi: boolean
  boyut?: number
  sonDegisiklik?: string
  etag?: string
}

export interface VeriKaynagi {
  readonly mod: AuthModu
  /** Silme yalnızca Cognito modunda desteklenir (Lambda modunda kaldırılmıştır). */
  readonly silDesteklenir: boolean
  oku<T>(ad: string, etag?: string): Promise<LambdaYanit<T> | null>
  yaz(ad: string, veri: unknown, etag?: string): Promise<{ etag?: string; anahtar: string; uyari?: string }>
  bilgi(ad: string): Promise<DosyaBilgisi>
  tumBilgiler(): Promise<DosyaBilgisi[]>
  liste(): Promise<Array<{ anahtar: string; boyut?: number; sonDegisiklik?: string }>>
  sil(ad: string): Promise<void>
  /**
   * Ön ek altındaki bir EKİ (ör. yayın görseli) tam anahtarıyla siler.
   * Mod desteklemiyorsa (Lambda) hata fırlatır — `silDesteklenir` ile aynı kural.
   */
  nesneSil(anahtar: string): Promise<void>
}
