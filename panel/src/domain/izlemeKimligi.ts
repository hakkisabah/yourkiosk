/**
 * İzleme kimliği — broker okuma kullanıcısı/parolası.
 *
 * GÜVENLİK (i5 bulgusu): panel paketi CloudFront'tan kimlik doğrulaması OLMADAN indirilebiliyor.
 * `VITE_MQTT_PAROLA` gibi derleme zamanı değişkenleri JS paketine literal olarak gömülür ve
 * `curl .../assets/index-*.js` ile okunabilir. Bu yüzden izleme parolası pakete YAZILMAZ:
 * yönetici bağlanırken girer, yalnız **sessionStorage**'da tutulur (sekme kapanınca silinir,
 * cihazda kalıcı değildir) ve sayfa yenilenince yeniden kullanılabilir.
 *
 * Broker tarafında bu kullanıcı YALNIZ `yourkiosk/durum/+` konusunu OKUR (bkz.
 * `deploy/mosquitto/kur.sh`); yayın yazamaz, başka konu göremez.
 */

export interface IzlemeKimligi {
  kullanici: string
  parola: string
}

export const VARSAYILAN_IZLEME_KULLANICI = 'panel-izleme'
const ANAHTAR = 'yourkiosk.izleme'
/** Yerel geliştirme (vite dev sunucusu) için TLS'siz WebSocket'e izin verilen adlar. */
const YEREL_ADLAR = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

/**
 * Broker adresi GÜVENLİ mi? (26 Ekim i5 bulgusu)
 *
 * `izlemeAdresi` eskiden `.env`teki `VITE_MQTT_URL`i yalnız `trim` ediyordu. `ws://`/`http://`
 * yazılırsa çalışma anında girilen izleme parolası DÜZ METİN gider (ve `http://` mqtt.js'te
 * hiç bağlanmaz → izleme sessizce ölür). Kural: yalnız `wss://`; `ws://` yalnız yerel adlarda.
 */
export function guvenliAdresMi(adres: string): boolean {
  let url: URL
  try {
    url = new URL(String(adres ?? '').trim())
  } catch {
    return false
  }
  if (url.protocol === 'wss:') return true
  return url.protocol === 'ws:' && YEREL_ADLAR.has(url.hostname)
}

/** Yayın konusundan izleme adresi (sır değil; `.env`ten gelebilir). Güvenli değilse `''`. */
export function izlemeAdresi(env: Record<string, string | undefined>): string {
  const ham = String(env.VITE_MQTT_URL ?? '').trim()
  return guvenliAdresMi(ham) ? ham : ''
}

/** `VITE_MQTT_URL` dolu ama güvenli değilse yöneticiye gösterilecek hata; sorun yoksa `''`. */
export function izlemeAdresiHatasi(env: Record<string, string | undefined>): string {
  const ham = String(env.VITE_MQTT_URL ?? '').trim()
  if (!ham || guvenliAdresMi(ham)) return ''
  return `VITE_MQTT_URL güvenli değil (${ham}) — wss://… bekleniyor; ws:// / http:// parolayı şifresiz gönderir`
}

/** `.env`teki yayın konusu (varsayılan `yourkiosk/yayin`). */
export function izlemeKonusu(env: Record<string, string | undefined>): string {
  return String(env.VITE_MQTT_KONU ?? 'yourkiosk/yayin').trim() || 'yourkiosk/yayin'
}

/** Oturumdaki kimliği okur; yoksa/bozuksa `null`. */
export function kimligiOku(depo: Storage | undefined = oturumDeposu()): IzlemeKimligi | null {
  if (!depo) return null
  try {
    const ham = depo.getItem(ANAHTAR)
    if (!ham) return null
    const belge = JSON.parse(ham) as Partial<IzlemeKimligi>
    const kullanici = String(belge.kullanici ?? '').trim()
    const parola = String(belge.parola ?? '')
    if (!kullanici || !parola) return null
    return { kullanici, parola }
  } catch {
    return null
  }
}

/** Kimliği oturuma yazar (parola diske yazılmaz). */
export function kimligiYaz(kimlik: IzlemeKimligi, depo: Storage | undefined = oturumDeposu()): void {
  if (!depo) return
  depo.setItem(ANAHTAR, JSON.stringify({ kullanici: kimlik.kullanici, parola: kimlik.parola }))
}

export function kimligiSil(depo: Storage | undefined = oturumDeposu()): void {
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
