/**
 * Hangi kiosk dosyaları S3'ten OKUNACAK — saf yardımcı (test edilebilir).
 *
 * Neden: `hepsiniYukle` her açılışta 7 ayrı GET atıyordu. Yeni kurulumda kova boş olduğu için
 * 7 × 404 üretiyor ve tarayıcı konsolunu dolduruyordu. Önce TEK liste isteği (ListObjectsV2)
 * yapılır; bu yardımcı, listede olmayan dosyalar için okuma denemesi yapılmamasını söyler.
 */
import { DOSYALAR, s3Anahtar } from '@/aws/config'

export interface OkumaKalemi {
  /** kiosk dosya adı (ör. `ayarlar.json`) */
  ad: string
  /** kovada var mı (liste alınamadıysa bilinmiyor → `true` kabul edilir) */
  varMi: boolean
}

/**
 * @param mevcutAnahtarlar ListObjectsV2 sonucu tam anahtarlar; `null` = liste alınamadı
 * @param onEk             kova ön eki (ör. `kiosk/`)
 */
export function okumaPlani(mevcutAnahtarlar: Iterable<string> | null, onEk: string): OkumaKalemi[] {
  const kume = mevcutAnahtarlar === null ? null : new Set(mevcutAnahtarlar)
  return Object.values(DOSYALAR).map((ad) => ({
    ad,
    varMi: kume === null ? true : kume.has(s3Anahtar(ad, onEk)),
  }))
}
