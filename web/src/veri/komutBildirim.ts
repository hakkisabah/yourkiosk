/**
 * `/komut-bildirim` istemcisi — tarayıcı kioskunda uzaktan komut bildirimi.
 *
 * NEDEN AYRI MODÜL: yoklama mantığı `App.vue` içinde gömülüyken test edilemiyordu (i5 bulgusu).
 * Sunucu metni SABİT sözlükten üretir; burada yalnız `aktif` bayrağına bakılır ve metin
 * `textContent`/`{{ }}` ile basılır — HTML olarak yorumlanmaz.
 */

export interface KomutBildirimYaniti {
  aktif?: boolean
  metin?: string
  komut?: string
}

export const VARSAYILAN_BILDIRIM = 'Komut uygulanıyor…'

/** Sunucu yanıtından gösterilecek metni üretir (bildirim yoksa boş dize). */
export function bildirimMetni(veri: KomutBildirimYaniti | null | undefined): string {
  if (!veri?.aktif) return ''
  const metin = typeof veri.metin === 'string' ? veri.metin.trim() : ''
  return metin || VARSAYILAN_BILDIRIM
}

/**
 * Yerel süpervizörden bildirimi okur.
 *
 * Hata yolları SESSİZDİR (boş dize): https veri modunda yerel uç yoktur, ağ hatası ekranı
 * bozmamalı. `getir` enjekte edilebilir (test).
 */
export async function komutBildiriminiOku(
  getir: typeof fetch = fetch,
): Promise<string> {
  try {
    const yanit = await getir('/komut-bildirim', { cache: 'no-store' })
    if (!yanit.ok) return ''
    return bildirimMetni((await yanit.json()) as KomutBildirimYaniti)
  } catch {
    return ''
  }
}
