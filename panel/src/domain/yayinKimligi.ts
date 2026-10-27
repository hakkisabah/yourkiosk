/**
 * Yayın kimliği — broker'a YAYIN yapan `panel` hesabının kullanıcı/parolası.
 *
 * GÜVENLİK (27 Ekim i5 bulgusu, YÜKSEK): panel paketi CloudFront'tan kimlik doğrulaması
 * OLMADAN indirilebiliyor. `VITE_MQTT_PAROLA` gibi derleme zamanı değişkenleri Vite tarafından
 * JS paketine LİTERAL olarak gömülür ve `curl .../assets/index-*.js` ile okunabilir → broker'ın
 * yayın hesabı herkese açık olurdu.
 *
 * Bu yüzden yayın parolası PAKETE YAZILMAZ: yönetici yayın sırasında girer, yalnız
 * **sessionStorage**'da tutulur (sekme kapanınca silinir, cihazda kalıcı değildir). Kimlik
 * yoksa yayın FAIL-CLOSED'dır: MQTT'ye hiç bağlanılmaz, cihazlar yoklama emniyet ağıyla
 * çalışmaya devam eder (bkz. `domain/push.ts`).
 *
 * Broker tarafında bu kullanıcı YALNIZ `yourkiosk/yayin` konusuna YAZAR; durum konularını
 * okuyamaz (bkz. `deploy/mosquitto/kur.sh` ACL'leri).
 */

export interface YayinKimligi {
  kullanici: string
  parola: string
}

export const VARSAYILAN_YAYIN_KULLANICI = 'panel'
const ANAHTAR = 'yourkiosk.yayin'

/** Oturumdaki yayın kimliğini okur; yoksa/bozuksa `null`. */
export function yayinKimligiOku(depo: Storage | undefined = oturumDeposu()): YayinKimligi | null {
  if (!depo) return null
  try {
    const ham = depo.getItem(ANAHTAR)
    if (!ham) return null
    const belge = JSON.parse(ham) as Partial<YayinKimligi>
    const kullanici = String(belge.kullanici ?? '').trim()
    const parola = String(belge.parola ?? '')
    if (!kullanici || !parola) return null
    return { kullanici, parola }
  } catch {
    return null
  }
}

/** Kimliği oturuma yazar (parola diske yazılmaz). */
export function yayinKimligiYaz(kimlik: YayinKimligi, depo: Storage | undefined = oturumDeposu()): void {
  if (!depo) return
  depo.setItem(ANAHTAR, JSON.stringify({ kullanici: kimlik.kullanici, parola: kimlik.parola }))
}

export function yayinKimligiSil(depo: Storage | undefined = oturumDeposu()): void {
  depo?.removeItem(ANAHTAR)
}

function oturumDeposu(): Storage | undefined {
  try {
    return typeof sessionStorage === 'undefined' ? undefined : sessionStorage
  } catch {
    // gizli modda erişim engellenebilir
    return undefined
  }
}
