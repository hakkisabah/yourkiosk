/**
 * Ayar şeması — kiosk ile TEK KAYNAK.
 *
 * `sema.generated.json` dosyası `kiosk/tools/sema_disa_aktar.py` tarafından
 * `kiosk/ayarlar.py` (KURALLAR/ACIKLAMALAR + config varsayılanları) üzerinden
 * üretilir. Elle düzenlemeyin; şema değiştiğinde:
 *     cd kiosk && python3 tools/sema_disa_aktar.py
 * (kiosk tarafındaki test, dosya güncel değilse kırılır ve bunu hatırlatır.)
 */
import ham from './sema.generated.json'

export type AyarTipi = 'bool' | 'int' | 'float' | 'str' | 'secim' | 'liste' | 'sayi_listesi'

export interface AyarTanimi {
  ad: string
  tam: string
  tip: AyarTipi
  etiket: string
  aciklama: string
  birim: string
  alt: number | null
  ust: number | null
  izinli: string[] | null
  varsayilan: unknown
  gelismis: boolean
}

export interface AyarGrubu {
  ad: string
  baslik: string
  kapsam: boolean
  anahtarlar: AyarTanimi[]
}

export interface Sema {
  _aciklama: string
  surum: number
  kapsam_gruplari: string[]
  gruplar: AyarGrubu[]
}

export const sema = ham as unknown as Sema
export const gruplar: AyarGrubu[] = sema.gruplar
export const kapsamGruplari: string[] = sema.kapsam_gruplari
export const tumAnahtarlar: AyarTanimi[] = gruplar.flatMap((g) => g.anahtarlar)

const _indeks = new Map<string, AyarTanimi>(tumAnahtarlar.map((a) => [a.tam, a]))

/** Kapsam (ilçe/bölge/cihaz) bazında geçersiz kılınabilen gruplar. */
export const kapsamGrubuMu = (grup: string): boolean => kapsamGruplari.includes(grup)

export const tanim = (tam: string): AyarTanimi | undefined => _indeks.get(tam)

export interface Dogrulama {
  gecerli: boolean
  /** Doğrulanmış (dönüştürülmüş) değer — yalnızca `gecerli` ise güvenilir. */
  deger?: unknown
  hata?: string
}

/**
 * Tek bir değeri doğrular — `kiosk/ayarlar.py::_deger_dogrula` ile aynı kurallar.
 * Geçersiz değer asla sessizce kabul edilmez; panelde kırmızı gösterilir.
 */
export function dogrula(tam: string, deger: unknown): Dogrulama {
  const t = tanim(tam)
  if (!t) return { gecerli: false, hata: `bilinmeyen anahtar: ${tam}` }

  switch (t.tip) {
    case 'bool':
      return typeof deger === 'boolean'
        ? { gecerli: true, deger }
        : { gecerli: false, hata: `${tam}: mantıksal değer (true/false) bekleniyordu` }

    case 'int':
    case 'float': {
      if (typeof deger === 'boolean' || (typeof deger !== 'number' && typeof deger !== 'string')) {
        return { gecerli: false, hata: `${tam}: sayı bekleniyordu` }
      }
      const sayi = typeof deger === 'number' ? deger : Number(String(deger).trim().replace(',', '.'))
      if (!Number.isFinite(sayi)) return { gecerli: false, hata: `${tam}: sayıya çevrilemedi` }
      const tamSayi = t.tip === 'int' ? Math.trunc(sayi) : sayi
      if (t.alt !== null && tamSayi < t.alt)
        return { gecerli: false, hata: `${tam}: ${tamSayi} alt sınırın altında (en az ${t.alt})` }
      if (t.ust !== null && tamSayi > t.ust)
        return { gecerli: false, hata: `${tam}: ${tamSayi} üst sınırın üstünde (en çok ${t.ust})` }
      return { gecerli: true, deger: tamSayi }
    }

    case 'str': {
      if (typeof deger !== 'string') return { gecerli: false, hata: `${tam}: metin bekleniyordu` }
      if (t.alt !== null && deger.length < t.alt)
        return { gecerli: false, hata: `${tam}: çok kısa (en az ${t.alt} karakter)` }
      if (t.ust !== null && deger.length > t.ust)
        return { gecerli: false, hata: `${tam}: çok uzun (en çok ${t.ust} karakter)` }
      return { gecerli: true, deger }
    }

    case 'secim': {
      const izinli = t.izinli ?? []
      if (typeof deger !== 'string' || !izinli.includes(deger))
        return { gecerli: false, hata: `${tam}: şunlardan biri olmalı: ${izinli.join(', ')}` }
      return { gecerli: true, deger }
    }

    case 'liste': {
      if (!Array.isArray(deger)) return { gecerli: false, hata: `${tam}: liste bekleniyordu` }
      const temiz = deger.filter((x): x is string => typeof x === 'string' && x.trim() !== '')
      if (temiz.length !== deger.length)
        return { gecerli: false, hata: `${tam}: listede boş olmayan metinler olmalı` }
      return { gecerli: true, deger: temiz.map((x) => x.trim()) }
    }

    case 'sayi_listesi': {
      if (!Array.isArray(deger)) return { gecerli: false, hata: `${tam}: sayı listesi bekleniyordu` }
      const sayilar: number[] = []
      for (const x of deger) {
        const n = typeof x === 'number' ? x : Number(x)
        if (!Number.isFinite(n)) return { gecerli: false, hata: `${tam}: listede sayı olmayan değer` }
        if (t.alt !== null && n < t.alt) return { gecerli: false, hata: `${tam}: ${n} alt sınırın altında` }
        if (t.ust !== null && n > t.ust) return { gecerli: false, hata: `${tam}: ${n} üst sınırın üstünde` }
        sayilar.push(Math.trunc(n))
      }
      return { gecerli: true, deger: sayilar }
    }

    default:
      return { gecerli: false, hata: `${tam}: desteklenmeyen tip (${t.tip})` }
  }
}

/** config.py varsayılanlarından tam ayar belgesi (kiosk'taki yapı ile aynı). */
export function varsayilanBelge(): Record<string, Record<string, unknown>> {
  const belge: Record<string, Record<string, unknown>> = {}
  for (const g of gruplar) {
    belge[g.ad] = {}
    for (const a of g.anahtarlar) belge[g.ad][a.ad] = a.varsayilan
  }
  return belge
}

/** Yalnızca kapsam gruplarını içeren boş belge iskeleti. */
export function bosKapsamBelgesi(): Record<string, Record<string, unknown>> {
  const belge: Record<string, Record<string, unknown>> = {}
  for (const g of gruplar.filter((x) => x.kapsam)) belge[g.ad] = {}
  return belge
}

/** Panelde yalnızca bu anahtarlar kapsam bazında geçersiz kılınabilir. */
export const kapsamAnahtarlari: AyarTanimi[] = tumAnahtarlar.filter((a) => kapsamGrubuMu(a.tam.split('.')[0]))
