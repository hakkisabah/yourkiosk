/**
 * NÖBET TASLAĞI — düzenleme/kaydetme mantığı (saf, test edilebilir).
 *
 * NEDEN AYRI MODÜL: Bu mantık sayfa içinde gömülüyken "kaydettim ama değişmedi" sınıfı hatalar
 * test edilemiyordu. Gerçek olay: `tumKayitlar` store verisini mutasyona uğratınca derin watcher
 * taslağı sıfırladı ve Kaydet ESKİ içeriği yazdı. Kurallar burada tek yerde ve testli.
 *
 * Sözleşme:
 *  • `kirliMi`  → taslak ile kaynak veri farklı mı (kaydedilecek bir şey var mı)
 *  • `kaydaHazirla` → { yazilsin, mesaj } — boş/bozuk durumda YAZMAZ
 */
import type { SistemVerisi } from './veri'

/** Boş/bozuk kayıt kontrolü: her kaydın start & end alanı dolu olmalı. */
export function bozukKayitVar(kayitlar: Array<Record<string, unknown>>): boolean {
  return kayitlar.some(
    (k) => !String(k.start ?? '').trim() || !String(k.end ?? '').trim(),
  )
}

/** Taslak, kaynak veriden farklı mı? (JSON karşılaştırması — belgeler JSON'dur) */
export function kirliMi(taslak: SistemVerisi | null | undefined, kaynak: SistemVerisi | null | undefined): boolean {
  return JSON.stringify(taslak ?? {}) !== JSON.stringify(kaynak ?? {})
}

export interface KaydetKarari {
  yazilsin: boolean
  mesaj: string
}

/**
 * Kaydetme kararı — arayüz yalnız bu karara uyar.
 *
 * @param kayitlar ekranda düzenlenen satırların kayıtları (start/end doğrulaması için)
 */
export function kaydaHazirla(
  taslak: SistemVerisi | null | undefined,
  kaynak: SistemVerisi | null | undefined,
  kayitlar: Array<Record<string, unknown>>,
): KaydetKarari {
  if (bozukKayitVar(kayitlar)) {
    return { yazilsin: false, mesaj: 'Her kaydın başlangıç ve bitiş zamanı olmalı (ör. 15/10/2026 08:30).' }
  }
  if (!kirliMi(taslak, kaynak)) {
    return {
      yazilsin: false,
      mesaj: 'Kaydedilecek değişiklik yok. (Bir alanı düzenleyip tekrar deneyin.)',
    }
  }
  return { yazilsin: true, mesaj: '' }
}

/** Kaydettikten sonra geri okunan içerik gönderilenle aynı mı? */
export function yazmaDogrulandiMi(gonderilen: unknown, geriOkunan: unknown): boolean {
  return JSON.stringify(gonderilen ?? {}) === JSON.stringify(geriOkunan ?? {})
}

/** Uyuşmazlıkta gösterilecek metin (kullanıcı ne yapacağını bilsin). */
export const YAZMA_UYUSMAZLIGI =
  "Kayıt S3'e yazıldı ancak geri okunan içerik farklı. Sayfayı yenileyip kontrol edin; " +
  'sorun sürerse bu mesajı bildirin.'
