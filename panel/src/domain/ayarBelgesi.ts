/**
 * `ayarlar.json` — TAM BELGE kuralı (kullanıcı kararı, 25 Ekim).
 *
 * NEDEN: dosya bugüne kadar yalnız DEĞİŞTİRİLEN anahtarları taşıyordu (sparse). Cihaz eksik
 * anahtarları `kiosk/config.py` varsayılanlarıyla tamamlıyordu. Sonuç: yayınlanan belge tek
 * başına okunabilir değildi ("bu cihazda X kaç?" sorusu için cihazın sürümünü bilmek gerekiyordu)
 * ve panelin gösterdiği "etkin değer" ile S3'teki dosya farklı şeyler söyleyebiliyordu.
 *
 * YENİ KURAL: panel kaydettiğinde şemadaki **her** anahtar yazılır; değer, o anahtar için
 * girilmiş bir değer yoksa şemanın (kiosk `config.py`) varsayılanıdır — `CIHAZA_OZGU` hariç.
 *
 * CIHAZA ÖZGÜ ANAHTARLAR (`CIHAZA_OZGU`) yayına HİÇ yazılmaz: MQTT broker kimliği/parolası/
 * X.509 yolu ve uzaktan komutların `systemctl` dizeleri cihaz başına değişir. Bunlar yayına
 * yazılırsa panel varsayılanı (`push_parola: ""`) cihazın YEREL parolasını ezer — yani "tam
 * belge" kuralı sessizce MQTT'yi ve imza zorunluluğunu kapatırdı (i5 bulgusu, ölçüldü).
 * Kiosk tarafı da aynı anahtarları `ayarlar.YEREL_ONCELIKLI` ile korur (iki katman).
 *
 * BEDELİ (bilinçli): dosya varsayılanları da "sabitler"; kiosk sürümünde bir varsayılan değişirse
 * eski yayın o cihazları etkilemez. Yeni bir kiosk sürümüne geçerken panelde belge
 * `varsayilanBelge()` ile yeniden üretilmelidir.
 */
import { gruplar } from './sema'

export type AyarBelgesi = Record<string, Record<string, unknown>>

/**
 * Yayına YAZILMAYAN, cihaza özgü anahtarlar (tam ad).
 *
 * Kiosk tarafındaki `ayarlar.py::YEREL_ONCELIKLI` ile AYNI kümeyi hedefler; oradaki test
 * (`test_ayarlar_uzak.py`) bu listeyle eşleşmeyi doğrular. Yeni bir sır/komut anahtarı
 * eklendiğinde ÜÇ yeri güncelleyin: burada, kiosk `YEREL_ONCELIKLI`, ve `sema.test.ts`.
 */
export const CIHAZA_OZGU: ReadonlySet<string> = new Set([
  // MQTT broker kimliği — cihaz başına (parola/anahtar dosya yolu)
  'tetik.push_aktif',
  'tetik.push_broker',
  'tetik.push_port',
  'tetik.push_konu',
  'tetik.push_kullanici',
  'tetik.push_parola',
  'tetik.push_ca',
  'tetik.push_sertifika',
  'tetik.push_anahtar',
  // Uzaktan komutlar: systemctl dizeleri ve güvenlik anahtarı cihazda kalır
  'calistirma.komut_imza_zorunlu',
  'calistirma.komut_kuru_calistirma',
  'calistirma.komut_zaman_asimi_s',
  'calistirma.komut_yeniden_baslat',
  'calistirma.komut_uygulama_yeniden_baslat',
  'calistirma.komut_ekrani_yenile',
])

/** Anahtar yayına yazılır mı? (cihaza özgü olanlar yazılmaz) */
export function yayinaGirer(tam: string): boolean {
  return !CIHAZA_OZGU.has(tam)
}

/**
 * Taslaktan TAM ayar belgesi üretir.
 *
 * • Şemadaki her grup/anahtar bulunur (eksik olan varsayılanıyla yazılır) — `CIHAZA_OZGU` hariç.
 * • Taslakta şemada olmayan anahtarlar YAZILMAZ: kiosk bunları "bilinmeyen anahtar" diye
 *   günlüğe yazıp yok sayar; yayına taşımak gürültüden başka işe yaramaz.
 * • `_aciklama` gibi yardımcı alanlar da yazılmaz (kiosk `_` ile başlayanları atlar).
 */
export function tamBelge(taslak: AyarBelgesi | null | undefined): AyarBelgesi {
  const belge: AyarBelgesi = {}
  for (const g of gruplar) {
    const grup: Record<string, unknown> = {}
    for (const a of g.anahtarlar) {
      if (!yayinaGirer(a.tam)) continue
      const deger = taslak?.[g.ad]?.[a.ad]
      grup[a.ad] = deger === undefined ? a.varsayilan : deger
    }
    belge[g.ad] = grup
  }
  return belge
}

/** Tam belgede eksik kalan anahtarlar (kuralın denetimi/teşhis; cihaza özgüler sayılmaz). */
export function eksikAnahtarlar(belge: AyarBelgesi | null | undefined): string[] {
  const eksik: string[] = []
  for (const g of gruplar) {
    for (const a of g.anahtarlar) {
      if (!yayinaGirer(a.tam)) continue
      if (belge?.[g.ad]?.[a.ad] === undefined) eksik.push(a.tam)
    }
  }
  return eksik
}

/** Belgedeki anahtar sayısı (teşhis göstergesi; cihaza özgü anahtarlar sayılmaz). */
export function anahtarSayisi(belge: AyarBelgesi): number {
  return Object.values(belge).reduce((n, grup) => n + Object.keys(grup).length, 0)
}
