/**
 * AYARLAR ve KAPSAM ÇÖZÜMLEMESİ (tarayıcı) — Qt `ayarlar.py` ile aynı kurallar.
 *
 * Ayarlar iki dosyadan gelir (ikisi de cihazın yerel sunucusundan okunur):
 *   · `ayarlar.json`         → genel varsayılanlar (panel tarafından yazılır)
 *   · `kapsam-ayarlari.json` → ilçe / bölge / cihaz bazında geçersiz kılmalar
 *
 * Çözümleme sırası (en özel kazanır): varsayilan → ilce → bolge → cihaz.
 * Yalnızca `KAPSAM_GRUPLARI` içindeki gruplar dikkate alınır; bilinmeyen gruplar
 * ve anahtarlar sessizce yok sayılır (Qt ile aynı davranış).
 */
export type GrupBelgesi = Record<string, Record<string, unknown>>

export interface AyarBelgesi {
  varsayilan?: GrupBelgesi
  ilceler?: Record<string, GrupBelgesi>
  bolgeler?: Record<string, GrupBelgesi>
  cihazlar?: Record<string, GrupBelgesi>
  [k: string]: unknown
}

export interface CihazSecimi {
  ilceId?: string
  bolgeId?: string
  clientId?: string
}

/** Kapsamla yönetilebilen gruplar (Qt: `ayarlar.KAPSAM_GRUPLARI`). */
export const KAPSAM_GRUPLARI = ['ozellikler', 'kusak', 'gorunum', 'gelismis', 'onbellek'] as const

export interface CozumSonucu {
  degerler: GrupBelgesi
  /** hangi katmanlar uygulandı (günlük/gösterim için) */
  uygulanan: string[]
}

/** Kapsam belgesini çözer: en özel katman en son uygulanır. */
export function kapsamCoz(belge: AyarBelgesi | null | undefined, secim: CihazSecimi = {}): CozumSonucu {
  const sonuc: GrupBelgesi = {}
  const uygulanan: string[] = []
  if (!belge || typeof belge !== 'object') return { degerler: sonuc, uygulanan }

  const katmanlar: Array<[string, GrupBelgesi | undefined]> = [['varsayilan', belge.varsayilan]]
  const ilceId = String(secim.ilceId ?? '')
  const bolgeId = String(secim.bolgeId ?? '')
  const clientId = String(secim.clientId ?? '')
  if (ilceId) katmanlar.push([`ilce:${ilceId}`, belge.ilceler?.[ilceId]])
  if (bolgeId) katmanlar.push([`bolge:${bolgeId}`, belge.bolgeler?.[bolgeId]])
  if (clientId) katmanlar.push([`cihaz:${clientId}`, belge.cihazlar?.[clientId]])

  for (const [etiket, katman] of katmanlar) {
    if (!katman || typeof katman !== 'object') continue
    let dokundu = false
    for (const grup of KAPSAM_GRUPLARI) {
      const grupDegerleri = katman[grup]
      if (!grupDegerleri || typeof grupDegerleri !== 'object') continue
      sonuc[grup] = { ...(sonuc[grup] ?? {}), ...grupDegerleri }
      dokundu = true
    }
    if (dokundu) uygulanan.push(etiket)
  }
  return { degerler: sonuc, uygulanan }
}

/**
 * Etkin ayarlar: dosya değerleri varsayılanların ÜZERİNE yazılır.
 *
 * DİKKAT — iki dosyanın yapısı FARKLIDIR (Qt `ayarlar.py` ile aynı):
 *   · `ayarlar.json`         → **düz grup haritası**: `{ "ozellikler": {...}, "calistirma": {...} }`
 *   · `kapsam-ayarlari.json` → **iç içe**: `{ varsayilan, ilceler, bolgeler, cihazlar }`
 *
 * @param varsayilanlar  `yerlesim.json` içindeki üretilmiş varsayılanlar (config.py)
 * @param belge          `ayarlar.json` içeriği (düz grup haritası)
 * @param kapsam         `kapsam-ayarlari.json` içeriği (iç içe)
 */
export class Ayarlar {
  private readonly degerler: GrupBelgesi

  constructor(
    varsayilanlar: GrupBelgesi = {},
    belge: AyarBelgesi | null = null,
    kapsam: AyarBelgesi | null = null,
    secim: CihazSecimi = {},
  ) {
    const dosyaKatmani = (belge ?? {}) as GrupBelgesi  // düz grup haritası
    const kapsamKatmani = kapsamCoz(kapsam, secim).degerler
    const birlesik: GrupBelgesi = {}
    for (const grup of Object.keys({ ...varsayilanlar, ...dosyaKatmani, ...kapsamKatmani })) {
      birlesik[grup] = {
        ...(varsayilanlar[grup] ?? {}),
        ...(dosyaKatmani[grup] ?? {}),
        ...(kapsamKatmani[grup] ?? {}),
      }
    }
    this.degerler = birlesik
  }

  /** Bir anahtarın ham değeri (yoksa `yedek`). */
  deger(grup: string, anahtar: string, yedek?: unknown): unknown {
    const deger = this.degerler[grup]?.[anahtar]
    return deger === undefined ? yedek : deger
  }

  /** Özellik bayrağı (Qt: `ayarlar.ozellik("yayinlar")`). */
  ozellik(ad: string, yedek = true): boolean {
    const deger = this.deger('ozellikler', ad, yedek)
    return deger === true || deger === 'true' || deger === 1 || deger === '1'
  }

  sayi(grup: string, anahtar: string, yedek: number): number {
    const deger = Number(this.deger(grup, anahtar, yedek))
    return Number.isFinite(deger) ? deger : yedek
  }

  metin(grup: string, anahtar: string, yedek: string): string {
    const deger = this.deger(grup, anahtar, yedek)
    return deger === undefined || deger === null ? yedek : String(deger)
  }

  /** Tüm etkin değerler (teşhis/günlük). */
  tumu(): GrupBelgesi {
    return this.degerler
  }
}
