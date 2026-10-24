/**
 * GÖRSEL YÜKLEME HATTI (saf fonksiyonlar) — panelden yükleme eklenince kullanılacak.
 *
 * Amaç: cihazların indirdiği dosyayı **küçültmek** (bant + RAM) ve **içerik adlı** saklamak.
 * Ölçüm (gerçek yayın görseli): 2473 KB PNG → 211 KB WebP q82 (tam) · 130 KB (1280 px).
 *
 * Tasarım kararları:
 *  • Biçim **WebP** (Qt `IZINLI_BICIMLER` içinde; AVIF bu Qt derlemesinde yok).
 *  • Saydamlık (alpha) varsa WebP korur — JPEG'e çevrilmez (arka plan siyah olurdu).
 *  • En uzun kenar ≤ 1920 px: kiosk tam ekran; daha büyüğü yalnız RAM israfı.
 *  • Anahtar = sha256(gövde)[:16] → aynı görsel iki kez yüklenirse TEK nesne;
 *    adres içerik değişince değişir → `Cache-Control: immutable` güvenli.
 *  • Metadata (EXIF/GPS) canvas çıktısında düşer.
 */

/** Yükleme politikası (tek yerde; panel/CLI aynı değerleri kullanır). */
export const GORSEL_POLITIKA = {
  /** en uzun kenar (px) */
  maxKenar: 1920,
  /** WebP kalitesi — fotoğraf için 82; düz afiş/logo için 88–92 önerilir */
  kalite: 82,
  /** kabul edilen giriş boyutu (bayt) */
  maxGirisBayt: 12 * 1024 * 1024,
  /** kabul edilen giriş türleri */
  girisTurleri: ['image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/bmp'] as readonly string[],
  /** S3 öneki */
  onek: 'kiosk/yayin-gorselleri/',
  /** çıktı uzantısı */
  uzanti: '.webp',
} as const

export interface Boyut {
  genislik: number
  yukseklik: number
}

/** Küçültme sonrası boyut (oran korunur, büyütme YAPILMAZ). */
export function hedefBoyut(giris: Boyut, maxKenar = GORSEL_POLITIKA.maxKenar): Boyut {
  const enBuyuk = Math.max(giris.genislik, giris.yukseklik)
  if (!enBuyuk || enBuyuk <= maxKenar) {
    return { genislik: Math.round(giris.genislik), yukseklik: Math.round(giris.yukseklik) }
  }
  const oran = maxKenar / enBuyuk
  return {
    genislik: Math.max(1, Math.round(giris.genislik * oran)),
    yukseklik: Math.max(1, Math.round(giris.yukseklik * oran)),
  }
}

/** Giriş kabul edilebilir mi? (tür + boyut) — hata metni döner, sorun yoksa null. */
export function girisDogrula(tur: string, bayt: number): string | null {
  if (!GORSEL_POLITIKA.girisTurleri.includes(String(tur).toLowerCase())) {
    return `desteklenmeyen tür: ${tur || '(yok)'} (kabul: ${GORSEL_POLITIKA.girisTurleri.join(', ')})`
  }
  if (bayt > GORSEL_POLITIKA.maxGirisBayt) {
    return `dosya çok büyük: ${(bayt / 1048576).toFixed(1)} MB (üst sınır ${GORSEL_POLITIKA.maxGirisBayt / 1048576} MB)`
  }
  if (bayt <= 0) return 'boş dosya'
  return null
}

/** sha256(gövde) → 16 karakterlik anahtar (adres: onek + anahtar + .webp). */
export async function gorselAnahtari(govde: ArrayBuffer): Promise<string> {
  const ozet = await crypto.subtle.digest('SHA-256', govde)
  return [...new Uint8Array(ozet)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16)
}

/** İçerik adlı S3 anahtarı: `kiosk/yayin-gorselleri/9f2c1ab34de5f607.webp` */
export function gorselAnahtariYolu(anahtar: string, onek: string = GORSEL_POLITIKA.onek): string {
  const temiz = String(onek || '').replace(/^\/+/, '')
  const onekli = temiz && !temiz.endsWith('/') ? `${temiz}/` : temiz
  return `${onekli}${anahtar}${GORSEL_POLITIKA.uzanti}`
}

/** Küçültme özeti (arayüzde "2,4 MB → 211 KB (%91 küçüldü)" göstermek için). */
export function kazancOzeti(girisBayt: number, cikisBayt: number): string {
  const oran = girisBayt > 0 ? Math.max(0, 100 - (cikisBayt / girisBayt) * 100) : 0
  const mb = (b: number) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`)
  return `${mb(girisBayt)} → ${mb(cikisBayt)} (%${Math.round(oran)} küçüldü)`
}

/** Tarayıcı tarafı dönüştürücü (test edilebilirlik için enjekte edilebilir). */
export interface GorselDonusturucu {
  decode(govde: Blob): Promise<{ genislik: number; yukseklik: number }>
  encode(
    govde: Blob,
    hedef: Boyut,
    kalite: number,
  ): Promise<ArrayBuffer>
}

/** Tam hat: doğrula → küçült → WebP → sha256 → S3 anahtarı. */
export async function gorselHazirla(
  dosya: { tur: string; govde: ArrayBuffer },
  donusturucu: GorselDonusturucu,
): Promise<{ anahtar: string; yol: string; govde: ArrayBuffer; boyut: Boyut; ozet: string }> {
  const hata = girisDogrula(dosya.tur, dosya.govde.byteLength)
  if (hata) throw new Error(hata)
  const blob = new Blob([dosya.govde], { type: dosya.tur })
  const giris = await donusturucu.decode(blob)
  const hedef = hedefBoyut(giris)
  const cikti = await donusturucu.encode(blob, hedef, GORSEL_POLITIKA.kalite)
  const anahtar = await gorselAnahtari(cikti)
  return {
    anahtar,
    yol: gorselAnahtariYolu(anahtar),
    govde: cikti,
    boyut: hedef,
    ozet: kazancOzeti(dosya.govde.byteLength, cikti.byteLength),
  }
}
