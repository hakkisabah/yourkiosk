/**
 * HEDEF SEÇİMİ yardımcıları (saf) — panel arayüzü için ilçe/bölge/cihaz listeleri ve etiketler.
 *
 * Kaynaklar:
 *  • `match.json` → hangi ilçe/bölgede hangi cihazlar var (kimlikler)
 *  • `lastSystemData.json` nöbet kayıtları → ilçe/bölge ADLARI (kimliğin yanında gösterilir)
 *
 * Arayüz bu dosyayı kullanır; böylece hedef listesi tek yerden gelir (test edilebilir).
 */
import { tumKayitlar, type SistemVerisi } from './veri'

export interface Secenek {
  deger: string
  baslik: string
  /** arama için ek metin (kimlik) */
  altBaslik?: string
}

/** match.json → { ilceId: [{ bolgeId: [cihazId…] }] } */
export type MatchBelgesi = Record<string, unknown>

function metin(deger: unknown): string {
  return String(deger ?? '').trim()
}

/** Nöbet kayıtlarından ilçe/bölge adı indeksleri. */
export function adIndeksi(veri: SistemVerisi | null | undefined): {
  ilce: Map<string, string>
  bolge: Map<string, string>
} {
  const ilce = new Map<string, string>()
  const bolge = new Map<string, string>()
  for (const kayit of tumKayitlar(veri)) {
    const ilceId = metin(kayit.ilceId)
    const bolgeId = metin(kayit.bolgeId)
    const ilceAd = metin(kayit.ilce)
    const bolgeAd = metin(kayit.bolge)
    if (ilceId && ilceAd && !ilce.has(ilceId)) ilce.set(ilceId, ilceAd)
    if (bolgeId && bolgeAd && !bolge.has(bolgeId)) bolge.set(bolgeId, bolgeAd)
  }
  return { ilce, bolge }
}

/** match.json içinden ilçe → bölge → cihazlar ağacını DÜZ listelere çevirir. */
export function matchAgaci(match: MatchBelgesi | null | undefined): {
  ilceler: string[]
  bolgeler: Map<string, string[]>
  cihazlar: Map<string, string[]>
} {
  const ilceler: string[] = []
  const bolgeler = new Map<string, string[]>()
  const cihazlar = new Map<string, string[]>()
  if (!match || typeof match !== 'object') return { ilceler, bolgeler, cihazlar }

  for (const [ilceId, ilceListesi] of Object.entries(match)) {
    if (ilceId.toLowerCase() === 'lastupdate' || !Array.isArray(ilceListesi)) continue
    ilceler.push(ilceId)
    const ilceBolgeler: string[] = []
    for (const kutu of ilceListesi) {
      if (!kutu || typeof kutu !== 'object') continue
      for (const [bolgeId, makineler] of Object.entries(kutu as Record<string, unknown>)) {
        ilceBolgeler.push(bolgeId)
        const anahtar = `${ilceId}/${bolgeId}`
        const liste = Array.isArray(makineler) ? makineler.map(metin).filter(Boolean) : []
        cihazlar.set(anahtar, [...(cihazlar.get(anahtar) ?? []), ...liste])
      }
    }
    bolgeler.set(ilceId, [...new Set(ilceBolgeler)])
  }
  return { ilceler: [...new Set(ilceler)].sort(), bolgeler, cihazlar }
}

/** İlçe seçenekleri ("ad (kimlik)" biçiminde, ad yoksa yalnız kimlik). */
export function ilceSecenekleri(match: MatchBelgesi | null | undefined, veri: SistemVerisi | null | undefined): Secenek[] {
  const { ilceler } = matchAgaci(match)
  const { ilce } = adIndeksi(veri)
  return ilceler.map((id) => {
    const ad = ilce.get(id)
    return { deger: id, baslik: ad ? `${ad} (${id})` : id, altBaslik: id }
  })
}

/** Seçili ilçenin bölgeleri. */
export function bolgeSecenekleri(
  match: MatchBelgesi | null | undefined,
  veri: SistemVerisi | null | undefined,
  ilceId: string,
): Secenek[] {
  const { bolgeler } = matchAgaci(match)
  const { bolge } = adIndeksi(veri)
  const liste = bolgeler.get(metin(ilceId)) ?? []
  return liste.map((id) => {
    const ad = bolge.get(id)
    return { deger: id, baslik: ad ? `${ad} (${id})` : id, altBaslik: id }
  })
}

/** Seçili ilçe+bölgenin cihazları. */
export function cihazSecenekleri(
  match: MatchBelgesi | null | undefined,
  ilceId: string,
  bolgeId: string,
): Secenek[] {
  const { cihazlar } = matchAgaci(match)
  const liste = cihazlar.get(`${metin(ilceId)}/${metin(bolgeId)}`) ?? []
  return [...new Set(liste)].sort().map((id) => ({ deger: id, baslik: id, altBaslik: id }))
}

/** Tek satırda hedef özeti (tabloda gösterilir). */
export function hedefEtiketi(
  kapsam: { ilceId?: string; bolgeId?: string; cihazId?: string },
  veri: SistemVerisi | null | undefined,
  match?: MatchBelgesi | null,
): string {
  const { ilce, bolge } = adIndeksi(veri)
  const cihazId = metin(kapsam.cihazId)
  const bolgeId = metin(kapsam.bolgeId)
  const ilceId = metin(kapsam.ilceId)
  if (!ilceId && !bolgeId && !cihazId) return 'Tüm cihazlar'

  const parcalar: string[] = []
  if (ilceId) parcalar.push(ilce.get(ilceId) ?? ilceId)
  if (bolgeId) parcalar.push(bolge.get(bolgeId) ?? bolgeId)
  if (cihazId) parcalar.push(`cihaz ${cihazId}`)
  else if ((ilceId || bolgeId) && match) {
    const secili = bolgeId
      ? cihazSecenekleri(match, ilceId, bolgeId).length
      : ilceSecenekleri(match, veri).find((s) => s.deger === ilceId)
        ? bolgeSecenekleri(match, veri, ilceId).reduce(
            (toplam, b) => toplam + cihazSecenekleri(match, ilceId, b.deger).length, 0)
        : 0
    if (secili) parcalar.push(`${secili} cihaz`)
  }
  return parcalar.join(' · ')
}
