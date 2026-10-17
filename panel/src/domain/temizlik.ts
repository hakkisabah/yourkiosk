/**
 * SÜRESİ GEÇEN YAYINLARIN TEMİZLİĞİ (iki taraf: S3 + cihaz).
 *
 * Yayın kaydı `Yayinlar.<id>` altında `start` / `end` / `contentUrl` / `duration` taşır.
 * `end` alanı yayının **son gösterim tarihidir**: o an geçtikten sonra yayın ne kioskta
 * ne panelde anlamlıdır. Bu modül:
 *
 *   1. süresi geçen kayıtları veri dosyasından ayıklar (S3'teki `lastSystemData.json`),
 *   2. adresi KENDİ kovamızdaysa ilgili görsel nesnesinin anahtarını üretir (S3'ten silinir),
 *      dış kaynak adresleri (ör. başka bir site) için `anahtar: null` döner — nesne bizim değil,
 *   3. cihaz tarafı önbelleği kiosk yönetir (`kiosk/core/onbellek.py`: son gösterim +
 *      `ONBELLEK_GORSEL_SAKLAMA_GUN` gün sonra görseli cihazdan siler).
 *
 * Kural (güvenli taraf): `end` alanı okunamayan/eksik kayda DOKUNULMAZ — yanlışlıkla
 * canlı bir yayını silmektense öksüz kayıt kalsın (panel bunları "atlanan" olarak bildirir).
 */
import { tarihCoz, type SistemVerisi } from './veri'

/** Yayının son gösterim tarihini taşıyabilecek alan adları (veri sağlayıcı farkları). */
export const BITIS_ALANLARI = ['end', 'bitis', 'gosterimBitis', 'sonGosterim', 'son_gosterim'] as const

/** Yayın görselinin adresini taşıyabilecek alan adları. */
export const ADRES_ALANLARI = ['contentUrl', 'contentURL', 'url', 'gorsel'] as const

/** Varsayılan güvenlik payı (saat): `end` geçtikten sonra bu kadar süre beklenir. */
export const VARSAYILAN_EK_SAAT = 2

export interface SilinecekYayin {
  /** `Yayinlar` altındaki anahtar (ör. "3") */
  id: string
  /** Yayın görselinin adresi ("" olabilir) */
  url: string
  /** Son gösterim tarihi */
  bitis: Date
  /** Kendi kovamızdaki nesne anahtarı; dış adreslerde null */
  anahtar: string | null
  /** Özgün kayıt (günlük/önizleme için) */
  kayit: unknown
}

export interface TemizlikSonucu {
  silinenler: SilinecekYayin[]
  /** `end` okunamadığı için korunan kayıt sayısı */
  atlananlar: number
  /** Temizlik sonrası veri (kaydetmeye hazır) */
  kalanlar: SistemVerisi
  /** Toplam yayın sayısı (öncesi) */
  toplam: number
}

/** Kayıttan son gösterim tarihini okur (yoksa null). */
export function yayinBitisTarihi(yayin: unknown): Date | null {
  if (!yayin || typeof yayin !== 'object' || Array.isArray(yayin)) return null
  const kayit = yayin as Record<string, unknown>
  for (const alan of BITIS_ALANLARI) {
    const tarih = tarihCoz(kayit[alan])
    if (tarih) return tarih
  }
  return null
}

/** Kayıttan görsel adresini okur (yoksa ""). */
export function yayinAdresi(yayin: unknown): string {
  if (!yayin || typeof yayin !== 'object' || Array.isArray(yayin)) return ''
  const kayit = yayin as Record<string, unknown>
  for (const alan of ADRES_ALANLARI) {
    const deger = kayit[alan]
    if (typeof deger === 'string' && deger.trim()) return deger.trim()
  }
  return ''
}

/**
 * Adres KENDİ S3 kovamıza mı ait? Öyleyse nesne anahtarını (ön ek dahil) döner.
 *
 * Desteklenen biçimler:
 *   https://<kova>.s3.<bölge>.amazonaws.com/<anahtar>
 *   https://s3.<bölge>.amazonaws.com/<kova>/<anahtar>
 *   https://<kova>.s3.amazonaws.com/<anahtar>
 * Dış adreslerde null (o nesne bizim değil; silme denenmez).
 */
export function s3NesneAnahtari(url: string, kova: string, onEk = ''): string | null {
  if (!url || !kova) return null
  let parcali: URL
  try {
    parcali = new URL(url)
  } catch {
    return null
  }
  if (parcali.protocol !== 'https:') return null
  const ana = parcali.hostname.toLowerCase()
  const kovaKucuk = kova.toLowerCase()
  let anahtar = decodeURIComponent(parcali.pathname.replace(/^\/+/, ''))

  const sanalHost = ana === `${kovaKucuk}.s3.amazonaws.com` || ana.startsWith(`${kovaKucuk}.s3.`)
  if (sanalHost) {
    // <kova>.s3... → anahtar doğrudan yolda
  } else if (ana === 's3.amazonaws.com' || /^s3[.-][a-z0-9-]+\.amazonaws\.com$/.test(ana)) {
    // yol biçimi: ilk parça kova adı olmalı
    const [ilk, ...kalan] = anahtar.split('/')
    if (ilk.toLowerCase() !== kovaKucuk) return null
    anahtar = kalan.join('/')
  } else {
    return null
  }
  if (!anahtar) return null
  if (onEk && !anahtar.startsWith(onEk)) return null // kovada ama bizim ön eğimizin dışında
  return anahtar
}

/**
 * Süresi geçen yayınları ayıklar (veriyi DEĞİŞTİRMEZ, yeni bir kopya döner).
 *
 * @param veri      `lastSystemData.json` içeriği
 * @param an        "şimdi" (test edilebilirlik için dışarıdan verilir)
 * @param ekSaat    son gösterimden sonra beklenecek güvenlik payı (saat)
 * @param kova      kendi S3 kovamız (nesne anahtarı üretmek için; boşsa hiç üretilmez)
 * @param onEk      kovanın ön eki (ör. "kiosk/")
 */
export function silinecekYayinlar(
  veri: SistemVerisi | null | undefined,
  an: Date = new Date(),
  ekSaat: number = VARSAYILAN_EK_SAAT,
  kova = '',
  onEk = '',
): TemizlikSonucu {
  const bosSonuc = (): TemizlikSonucu => ({ silinenler: [], atlananlar: 0, kalanlar: veri ?? {}, toplam: 0 })
  if (!veri || typeof veri !== 'object') return bosSonuc()
  const yayinlar = veri.Yayinlar
  if (!yayinlar || typeof yayinlar !== 'object' || Array.isArray(yayinlar)) return bosSonuc()

  const kayitlar = yayinlar as Record<string, unknown>
  const esik = an.getTime() - Math.max(0, ekSaat) * 3600 * 1000
  const silinenler: SilinecekYayin[] = []
  const kalan: Record<string, unknown> = {}
  let atlananlar = 0

  for (const [id, kayit] of Object.entries(kayitlar)) {
    const bitis = yayinBitisTarihi(kayit)
    if (!bitis) {
      // Son gösterim tarihi okunamadı → güvenli taraf: DOKUNMA
      if (kayit && typeof kayit === 'object') atlananlar += 1
      kalan[id] = kayit
      continue
    }
    if (bitis.getTime() <= esik) {
      const url = yayinAdresi(kayit)
      silinenler.push({ id, url, bitis, anahtar: s3NesneAnahtari(url, kova, onEk), kayit })
    } else {
      kalan[id] = kayit
    }
  }

  return {
    silinenler,
    atlananlar,
    kalanlar: { ...veri, Yayinlar: kalan },
    toplam: Object.keys(kayitlar).length,
  }
}

/** Yerel saat damgası: `2026-10-15 02:45:40` (kiosk `lastupdate.json` ile aynı biçim). */
export function zamanDamgasi(an: Date = new Date()): string {
  const iki = (n: number): string => String(n).padStart(2, '0')
  return (
    `${an.getFullYear()}-${iki(an.getMonth() + 1)}-${iki(an.getDate())} ` +
    `${iki(an.getHours())}:${iki(an.getMinutes())}:${iki(an.getSeconds())}`
  )
}
