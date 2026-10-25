/**
 * `ayarlar.json` — TAM BELGE kuralı (kullanıcı kararı, 25 Ekim).
 *
 * NEDEN: dosya bugüne kadar yalnız DEĞİŞTİRİLEN anahtarları taşıyordu (sparse). Cihaz eksik
 * anahtarları `kiosk/config.py` varsayılanlarıyla tamamlıyordu. Sonuç: yayınlanan belge tek
 * başına okunabilir değildi ("bu cihazda X kaç?" sorusu için cihazın sürümünü bilmek gerekiyordu)
 * ve panelin gösterdiği "etkin değer" ile S3'teki dosya farklı şeyler söyleyebiliyordu.
 *
 * YENİ KURAL: panel kaydettiğinde şemadaki **her** anahtar yazılır; değer, o anahtar için
 * girilmiş bir değer yoksa şemanın (kiosk `config.py`) varsayılanıdır.
 *
 * BEDELİ (bilinçli): dosya artık varsayılanları da "sabitlediği" için kiosk sürümünde bir
 * varsayılan değişirse eski yayın o cihazları etkilemez. Bu yüzden:
 *  • yeni bir kiosk sürümüne geçerken panelde "Varsayılanları şemadan yenile" ile belge
 *    yeniden üretilmelidir (`varsayilanBelge()`),
 *  • `veri.*`, `ag.*`, `calistirma.mod` gibi cihaza özgü anahtarlar kiosk tarafında
 *    `YEREL_ONCELIKLI` olduğu için yayın onları ezmez (davranış değişmedi).
 */
import { gruplar } from './sema'

export type AyarBelgesi = Record<string, Record<string, unknown>>

/**
 * Taslaktan TAM ayar belgesi üretir.
 *
 * • Şemadaki her grup/anahtar bulunur (eksik olan varsayılanıyla yazılır).
 * • Taslakta şemada olmayan anahtarlar YAZILMAZ: kiosk bunları "bilinmeyen anahtar" diye
 *   günlüğe yazıp yok sayar; yayına taşımak gürültüden başka işe yaramaz.
 * • `_aciklama` gibi yardımcı alanlar da yazılmaz (kiosk `_` ile başlayanları atlar).
 */
export function tamBelge(taslak: AyarBelgesi | null | undefined): AyarBelgesi {
  const belge: AyarBelgesi = {}
  for (const g of gruplar) {
    const grup: Record<string, unknown> = {}
    for (const a of g.anahtarlar) {
      const deger = taslak?.[g.ad]?.[a.ad]
      grup[a.ad] = deger === undefined ? a.varsayilan : deger
    }
    belge[g.ad] = grup
  }
  return belge
}

/** Tam belgede eksik kalan anahtarlar (kuralın denetimi/teşhis; boş liste = tam). */
export function eksikAnahtarlar(belge: AyarBelgesi | null | undefined): string[] {
  const eksik: string[] = []
  for (const g of gruplar) {
    for (const a of g.anahtarlar) {
      if (belge?.[g.ad]?.[a.ad] === undefined) eksik.push(a.tam)
    }
  }
  return eksik
}

/** Belgedeki anahtar sayısı (panelde "tam belge: 61 anahtar" göstergesi). */
export function anahtarSayisi(belge: AyarBelgesi): number {
  return Object.values(belge).reduce((n, grup) => n + Object.keys(grup).length, 0)
}
