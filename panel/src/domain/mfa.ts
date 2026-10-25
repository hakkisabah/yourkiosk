/**
 * MFA (TOTP, RFC 6238) — HAZIR ama VARSAYILAN OLARAK KAPALI.
 *
 * NEDEN ŞİMDİ: panel tek yönetici hesabıyla çalışıyor ve o hesap tüm yayın verisini
 * değiştirebiliyor. İki adımlı doğrulama sonradan eklenirse oturum/kayıt akışının yeniden
 * yazılması gerekir; bu yüzden algoritma, tohum üretimi ve doğrulama şimdiden yazıldı ve
 * testlerle kilitlendi. AÇMAK İÇİN tek satır: `.env` → `VITE_MFA_AKTIF=1` (bkz. panel/README).
 *
 * GÜVENLİK NOTLARI
 *  • Tohum (secret) ASLA depoya/pakete yazılmaz: kullanıcı kurulum sırasında üretir,Authenticator
 *    uygulamasına okutur; panelde yalnız **sessionStorage**'da tutulur (izleme kimliğiyle aynı
 *    kural — paket CloudFront'tan kimlik doğrulamasız indirilebiliyor).
 *  • Doğrulama `fail-closed`: hata/bozuk girdi → `false` (asla `true`'ya düşmez).
 *  • Saat kaymasına tolerans ±1 pencere (30 sn) — cihaz saati kaymış olsa da kilitlenmez.
 *  • Karşılaştırma SABİT ZAMANLI (zamanlama sızıntısı yok).
 */

/** Varsayılan: KAPALI. Sistem tam çalışır hâle gelince `.env`te `VITE_MFA_AKTIF=1` ile açılır. */
export const VARSAYILAN_MFA_AKTIF = false

export interface MfaAyarlari {
  /** Pencere süresi (sn) — RFC 6238 varsayılanı 30. */
  periyot?: number
  /** Kod hane sayısı — 6 (Authenticator varsayılanı). */
  hane?: number
  /** İleri/geri kabul edilen pencere sayısı (saat kayması toleransı). */
  tolerans?: number
}

const VARSAYILAN: Required<MfaAyarlari> = { periyot: 30, hane: 6, tolerans: 1 }

/** `.env` bayrağı: `VITE_MFA_AKTIF=1` → açık. Başka her değer KAPALI sayılır (fail-closed). */
export function mfaAktifMi(env: Record<string, string | undefined>): boolean {
  const ham = String(env.VITE_MFA_AKTIF ?? '').trim().toLowerCase()
  return ham === '1' || ham === 'true' || ham === 'evet'
}

// ------------------------------------------------------------------ base32
const ALFABE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'

/** 20 baytlık rastgele tohum → base32 (Authenticator uygulamalarının beklediği biçim). */
export function tohumUret(bayt = 20): string {
  const dizi = new Uint8Array(bayt)
  // WebCrypto ve Node'un `crypto` nesnesi aynı arayüzü verir; ikisi de yoksa hata (sessiz zayıf tohum YOK).
  const kripto = (globalThis as { crypto?: { getRandomValues?: (a: Uint8Array) => Uint8Array } }).crypto
  if (!kripto?.getRandomValues) throw new Error('güvenli rastgelelik yok (crypto.getRandomValues)')
  kripto.getRandomValues(dizi)
  return base32Kodla(dizi)
}

export function base32Kodla(veri: Uint8Array): string {
  let bitler = 0
  let deger = 0
  let cikti = ''
  for (const bayt of veri) {
    deger = (deger << 8) | bayt
    bitler += 8
    while (bitler >= 5) {
      cikti += ALFABE[(deger >>> (bitler - 5)) & 31]
      bitler -= 5
    }
  }
  if (bitler > 0) cikti += ALFABE[(deger << (5 - bitler)) & 31]
  return cikti
}

export function base32Coz(metin: string): Uint8Array {
  const temiz = String(metin ?? '').toUpperCase().replace(/[\s=-]/g, '')
  const baytlar: number[] = []
  let bitler = 0
  let deger = 0
  for (const karakter of temiz) {
    const indeks = ALFABE.indexOf(karakter)
    if (indeks < 0) throw new Error(`geçersiz base32 karakteri: ${karakter}`)
    deger = (deger << 5) | indeks
    bitler += 5
    if (bitler >= 8) {
      baytlar.push((deger >>> (bitler - 8)) & 255)
      bitler -= 8
    }
  }
  return new Uint8Array(baytlar)
}

// ------------------------------------------------------------------ TOTP
function sayacBaytlari(sayac: number): Uint8Array {
  const tampon = new Uint8Array(8)
  let kalan = Math.floor(sayac)
  for (let i = 7; i >= 0; i -= 1) {
    tampon[i] = kalan & 255
    kalan = Math.floor(kalan / 256)
  }
  return tampon
}

function hmacAnahtari(tohum: Uint8Array): Promise<CryptoKey> {
  const kripto = (globalThis as { crypto?: Crypto }).crypto
  if (!kripto?.subtle) throw new Error('WebCrypto yok (HMAC hesaplanamaz)')
  // `subtle.importKey` base32 çözülmüş ham baytları ister.
  return kripto.subtle.importKey('raw', tohum as unknown as ArrayBuffer, { name: 'HMAC', hash: 'SHA-1' }, false, ['sign'])
}

/** Belirli bir zaman dilimi için TOTP kodu (RFC 6238, HMAC-SHA1). */
export async function totpUret(
  tohum: string,
  zaman: number = Date.now(),
  ayarlar: MfaAyarlari = {},
): Promise<string> {
  const { periyot, hane } = { ...VARSAYILAN, ...ayarlar }
  const kripto = (globalThis as { crypto?: Crypto }).crypto
  if (!kripto?.subtle) throw new Error('WebCrypto yok (HMAC hesaplanamaz)')
  const anahtar = await hmacAnahtari(base32Coz(tohum))
  const sayac = Math.floor(zaman / 1000 / periyot)
  const imza = new Uint8Array(
    await kripto.subtle.sign('HMAC', anahtar, sayacBaytlari(sayac) as unknown as ArrayBuffer),
  )
  const konum = imza[imza.length - 1] & 0x0f
  const ikili =
    ((imza[konum] & 0x7f) << 24) | (imza[konum + 1] << 16) | (imza[konum + 2] << 8) | imza[konum + 3]
  const tam = ikili % 10 ** hane
  return String(tam).padStart(hane, '0')
}

/** Sabit zamanlı karşılaştırma (uzunluk farkı da sızdırmaz). */
export function sabitZamanliEsit(a: string, b: string): boolean {
  const x = String(a ?? '')
  const y = String(b ?? '')
  let fark = x.length ^ y.length
  const uzunluk = Math.max(x.length, y.length)
  for (let i = 0; i < uzunluk; i += 1) {
    fark |= (x.charCodeAt(i) || 0) ^ (y.charCodeAt(i) || 0)
  }
  return fark === 0
}

/**
 * Kodu doğrular. `fail-closed`: boş/bozuk girdi, WebCrypto yokluğu, hata → `false`.
 * `tolerans` kadar eski/yeni pencere de kabul edilir (saat kayması).
 */
export async function totpDogrula(
  tohum: string,
  kod: string,
  zaman: number = Date.now(),
  ayarlar: MfaAyarlari = {},
): Promise<boolean> {
  const { periyot, hane, tolerans } = { ...VARSAYILAN, ...ayarlar }
  const girilen = String(kod ?? '').replace(/\s/g, '')
  if (!/^\d+$/.test(girilen) || girilen.length !== hane) return false
  if (!String(tohum ?? '').trim()) return false
  try {
    for (let k = -tolerans; k <= tolerans; k += 1) {
      const beklenen = await totpUret(tohum, zaman + k * periyot * 1000, { periyot, hane })
      if (sabitZamanliEsit(beklenen, girilen)) return true
    }
    return false
  } catch {
    return false
  }
}

/** Authenticator uygulamasına okutulacak `otpauth://` adresi (QR kaynağı). */
export function otpauthAdresi(tohum: string, kullanici: string, kurum = 'yourkiosk', ayarlar: MfaAyarlari = {}): string {
  const { periyot, hane } = { ...VARSAYILAN, ...ayarlar }
  const etiket = encodeURIComponent(`${kurum}:${String(kullanici ?? '').trim()}`)
  const parametreler = new URLSearchParams({
    secret: String(tohum ?? '').trim(),
    issuer: kurum,
    algorithm: 'SHA1',
    digits: String(hane),
    period: String(periyot),
  })
  return `otpauth://totp/${etiket}?${parametreler.toString()}`
}
