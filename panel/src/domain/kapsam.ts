/**
 * KAPSAM ÇÖZÜMLEMESİ (ilçe / bölge / cihaz bazlı özellik yönetimi).
 *
 * Kiosk tarafındaki `kiosk/ayarlar.py::kapsam_belgesi` ile BİREBİR aynı kurallar:
 *   varsayilan → ilceler[ilceId] → bolgeler[bolgeId] → cihazlar[clientID]
 * En özel kapsam kazanır; yalnızca verilen anahtar geçersiz kılınır.
 * Ortak test verisi: kiosk/tests/veri/kapsam_ornek.json (iki tarafta da doğrulanır).
 */
import { kopya } from '@/domain/kopya'
import { dogrula, kapsamGruplari, tanim } from './sema'

export interface KapsamSecimi {
  ilceId?: string
  bolgeId?: string
  clientId?: string
}

export type GrupBelgesi = Record<string, Record<string, unknown>>

export interface KapsamBelgesi {
  _aciklama?: unknown
  varsayilan?: GrupBelgesi
  ilceler?: Record<string, GrupBelgesi>
  bolgeler?: Record<string, GrupBelgesi>
  cihazlar?: Record<string, GrupBelgesi>
}

export type KapsamTuru = 'varsayilan' | 'ilceler' | 'bolgeler' | 'cihazlar'

export const KAPSAM_ETIKETLERI: Record<KapsamTuru, string> = {
  varsayilan: 'Varsayılan (tüm cihazlar)',
  ilceler: 'İlçe',
  bolgeler: 'Bölge',
  cihazlar: 'Cihaz',
}

/** Kapsam türü → seçim anahtarı ('' = varsayılan). */
export function secimAnahtari(tur: KapsamTuru, id: string): KapsamSecimi {
  switch (tur) {
    case 'ilceler':
      return { ilceId: id }
    case 'bolgeler':
      return { bolgeId: id }
    case 'cihazlar':
      return { clientId: id }
    default:
      return {}
  }
}

interface CozumSonucu {
  belge: GrupBelgesi
  /** "ozellikler.kayan_yazi" → "ilce:1001" | "varsayilan" (yalnızca verilen anahtarlar) */
  kaynak: Record<string, string>
}

/** Kapsam dosyasını okur ve cihaz için birleştirilmiş ayar belgesini döner. */
export function kapsamCoz(ham: KapsamBelgesi | null | undefined, secim: KapsamSecimi = {}): CozumSonucu {
  const belge: GrupBelgesi = {}
  const kaynak: Record<string, string> = {}
  if (!ham) return { belge, kaynak }

  const birlestir = (veri: unknown, etiket: string): void => {
    if (!veri || typeof veri !== 'object') return
    for (const [grup, icerik] of Object.entries(veri as Record<string, unknown>)) {
      if (!kapsamGruplari.includes(grup) || !icerik || typeof icerik !== 'object') continue
      for (const [anahtar, deger] of Object.entries(icerik as Record<string, unknown>)) {
        if (anahtar.startsWith('_')) continue
        belge[grup] = belge[grup] ?? {}
        belge[grup][anahtar] = deger
        kaynak[`${grup}.${anahtar}`] = etiket
      }
    }
  }

  birlestir(ham.varsayilan, 'varsayilan')
  if (secim.ilceId) birlestir(ham.ilceler?.[secim.ilceId], `ilce:${secim.ilceId}`)
  if (secim.bolgeId) birlestir(ham.bolgeler?.[secim.bolgeId], `bolge:${secim.bolgeId}`)
  if (secim.clientId) birlestir(ham.cihazlar?.[secim.clientId], `cihaz:${secim.clientId}`)
  return { belge, kaynak }
}

export interface KapsamSatiri {
  tam: string
  etiket: string
  grup: string
  etkin: unknown
  kaynak: string
  varsayilan: unknown
  /** Kapsam dosyasında geçersiz bir değer var mı (kiosk yok sayar, panel uyarır) */
  gecersizMi: boolean
  hata?: string
}

/**
 * Panel/teşhis görünümü: her anahtarın ETKİN değeri ve hangi kapsamdan geldiği.
 * Geçersiz değerler gizlenmez — kullanıcı hangi kaydı düzeltmesi gerektiğini görür.
 */
export function kapsamSatirlari(ham: KapsamBelgesi | null | undefined, secim: KapsamSecimi = {}): KapsamSatiri[] {
  const { belge, kaynak } = kapsamCoz(ham, secim)
  const satirlar: KapsamSatiri[] = []
  for (const grup of kapsamGruplari) {
    for (const [anahtar, hamDeger] of Object.entries(belge[grup] ?? {})) {
      const tam = `${grup}.${anahtar}`
      const t = tanim(tam)
      if (!t) continue // bilinmeyen anahtar (kiosk da yok sayar)
      const sonuc = dogrula(tam, hamDeger)
      satirlar.push({
        tam,
        etiket: t.etiket,
        grup,
        etkin: sonuc.gecerli ? sonuc.deger : t.varsayilan,
        kaynak: kaynak[tam] ?? 'varsayilan',
        varsayilan: t.varsayilan,
        gecersizMi: !sonuc.gecerli,
        hata: sonuc.hata,
      })
    }
  }
  return satirlar.sort((a, b) => a.grup.localeCompare(b.grup, 'tr') || a.tam.localeCompare(b.tam, 'tr'))
}

/** Kapsam belgesinde bir kapsamın ayarlarını (tam anahtar → değer) döner. */
export function kapsamAyarlari(
  ham: KapsamBelgesi | null | undefined,
  tur: KapsamTuru,
  id = '',
): Record<string, unknown> {
  if (!ham) return {}
  const grup = tur === 'varsayilan' ? ham.varsayilan : (ham[tur]?.[id] as GrupBelgesi | undefined)
  const sonuc: Record<string, unknown> = {}
  for (const kapsamGrubu of kapsamGruplari) {
    for (const [anahtar, deger] of Object.entries(grup?.[kapsamGrubu] ?? {})) {
      sonuc[`${kapsamGrubu}.${anahtar}`] = deger
    }
  }
  return sonuc
}

/** Kapsam belgesine değer yazar (değiştirilemez / immutable). */
export function kapsamYaz(
  ham: KapsamBelgesi | null | undefined,
  tur: KapsamTuru,
  id: string,
  degisiklikler: Record<string, unknown>,
): KapsamBelgesi {
  const yeni: KapsamBelgesi = kopya(ham ?? {})
  const hedef: GrupBelgesi = _kapsam_grubu(yeni, tur, id, true)!
  for (const [tam, deger] of Object.entries(degisiklikler)) {
    const [grup, anahtar] = tam.split('.')
    if (!kapsamGruplari.includes(grup) || !anahtar) continue
    hedef[grup] = hedef[grup] ?? {}
    hedef[grup][anahtar] = deger
  }
  return _bosluklari_temizle(yeni)
}

/** Bir kapsamdan anahtarı kaldırır (üst kapsama geri döner). */
export function kapsamSil(
  ham: KapsamBelgesi | null | undefined,
  tur: KapsamTuru,
  id: string,
  anahtarlar: string[],
): KapsamBelgesi {
  const yeni: KapsamBelgesi = kopya(ham ?? {})
  const grup = _kapsam_grubu(yeni, tur, id, false)
  for (const tam of anahtarlar) {
    const [g, a] = tam.split('.')
    if (grup?.[g]) delete grup[g][a]
  }
  return _bosluklari_temizle(yeni)
}

/** Seçilen kapsamın grup belgesini getirir (oluştur=true ise yoksa oluşturur). */
function _kapsam_grubu(
  belge: KapsamBelgesi,
  tur: KapsamTuru,
  id: string,
  olustur: boolean,
): GrupBelgesi | undefined {
  if (tur === 'varsayilan') {
    if (!belge.varsayilan && olustur) belge.varsayilan = {}
    return belge.varsayilan
  }
  if (!belge[tur] && olustur) belge[tur] = {}
  const liste = belge[tur]
  if (!liste) return undefined
  if (!liste[id] && olustur) liste[id] = {}
  return liste[id]
}

/** Boş kapsam/grup kayıtlarını atar (dosya okunabilir kalsın). */
function _bosluklari_temizle(belge: KapsamBelgesi): KapsamBelgesi {
  const temizle = (grup?: GrupBelgesi): GrupBelgesi | undefined => {
    if (!grup) return undefined
    const yeni: GrupBelgesi = {}
    for (const [ad, icerik] of Object.entries(grup)) {
      if (icerik && Object.keys(icerik).length) yeni[ad] = icerik
    }
    return Object.keys(yeni).length ? yeni : undefined
  }
  const sonuc: KapsamBelgesi = { ...(belge._aciklama ? { _aciklama: belge._aciklama } : {}) }
  const v = temizle(belge.varsayilan)
  if (v) sonuc.varsayilan = v
  for (const tur of ['ilceler', 'bolgeler', 'cihazlar'] as const) {
    const liste = belge[tur]
    if (!liste) continue
    const yeni: Record<string, GrupBelgesi> = {}
    for (const [id, grup] of Object.entries(liste)) {
      const t = temizle(grup)
      if (t) yeni[id] = t
    }
    if (Object.keys(yeni).length) sonuc[tur] = yeni
  }
  return sonuc
}

/** Kapsam belgesindeki tüm kapsam kimlikleri (panelde ağaç/liste için). */
export function kapsamKimlikleri(ham: KapsamBelgesi | null | undefined): Record<KapsamTuru, string[]> {
  return {
    varsayilan: [''],
    ilceler: Object.keys(ham?.ilceler ?? {}).sort(),
    bolgeler: Object.keys(ham?.bolgeler ?? {}).sort(),
    cihazlar: Object.keys(ham?.cihazlar ?? {}).sort(),
  }
}
