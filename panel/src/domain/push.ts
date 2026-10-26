/**
 * Panel → cihaz ANLIK tetikleme (MQTT).
 *
 * NEDEN: 600 cihazda cihaz başına yoklama maliyeti doğrusal büyür (3 sn ≈ 518 M istek/ay).
 * MQTT'de cihaz başına tek kalıcı bağlantı vardır; yayın başına tek mesaj gider (~100 ms).
 *
 * Yapılandırma (panel/.env.local — YALNIZ sır OLMAYAN alanlar):
 *   VITE_MQTT_URL=wss://broker.example:8084/mqtt
 *   VITE_MQTT_KONU=yourkiosk/yayin
 *   VITE_MQTT_KULLANICI=panel
 *
 * GÜVENLİK (i5 bulgusu — ölçüldü: yayın parolası derleme anında JS paketine gömülüyordu):
 * panel paketi CloudFront'tan kimlik doğrulaması OLMADAN indirilebiliyor ve `VITE_*` değerleri
 * derleme anında pakete LİTERAL yazılır (`curl .../assets/index-*.js` ile okunur). Bu yüzden
 * yayın parolası artık bir derleme değişkeni DEĞİL: operatör oturumda bir kez girer, yalnız
 * `sessionStorage`'da tutulur (sekme kapanınca silinir, diske/pakete yazılmaz). Kayıt, sekmenin
 * bu SAYFA YÜKLEMESİNE etiketlenir: sayfa yenilenince etiket değişir ve parola yeniden sorulur
 * (sessionStorage yenilemede yaşadığı için etiket olmadan eski sır sessizce kullanılırdı).
 * Sır yoksa yayın yapılmaz ve operatöre ne yapacağını söyleyen hata döner.
 *
 * Ayarlanmamışsa (URL yok) sessizce atlanır (cihazlar yoklama emniyet ağıyla çalışır).
 * `mqtt` paketi **dinamik** yüklenir: yapılandırma yoksa ana pakete girmez.
 */

const URL_ = import.meta.env.VITE_MQTT_URL as string | undefined

/** Oturum parolasının sessionStorage anahtarı (SIR — localStorage'a asla yazılmaz). */
export const YAYIN_PAROLA_ANAHTARI = 'yourkiosk.yayin-parola'

/** Bu sayfa yüklemesinin etiketi: yenilemede değişir → eski sır yeniden kullanılmaz. */
const SAYFA_ETIKETI = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`

/** Yayın hesabının kullanıcı adı (sır değil). */
export const VARSAYILAN_YAYIN_KULLANICI = 'panel'

/** Parola yokken operatöre gösterilecek açıklama: neden çalışmıyor + ne yapmalı. */
export const PAROLA_YOK_MESAJI =
  'Yayın parolası bu oturumda girilmedi. Yöneticinizden aldığınız parolayı yayın istemine yazın ' +
  '(parola pakete gömülmez, yalnız oturumda tutulur; sayfa yenilenirse yeniden sorulur).'

export function mqttYapilandirildi(): boolean {
  return Boolean(URL_)
}

export interface MqttSonuc {
  gonderildi: boolean
  hata?: string
}

/** Oturumdaki yayın parolasını okur; yoksa/başka sayfa yüklemesindense boş dize. */
export function yayinParolasi(depo: Storage | undefined = oturumDeposu()): string {
  if (!depo) return ''
  try {
    const ham = depo.getItem(YAYIN_PAROLA_ANAHTARI)
    if (!ham) return ''
    const belge = JSON.parse(ham) as { p?: unknown; s?: unknown }
    if (belge.s !== SAYFA_ETIKETI) return ''
    return String(belge.p ?? '')
  } catch {
    return ''
  }
}

/** Parolayı OTURUMA yazar (yalnız sessionStorage, bu sayfa yüklemesi için — kalıcı değil). */
export function yayinParolasiYaz(parola: string, depo: Storage | undefined = oturumDeposu()): void {
  if (!depo || !parola) return
  try {
    depo.setItem(YAYIN_PAROLA_ANAHTARI, JSON.stringify({ p: parola, s: SAYFA_ETIKETI }))
  } catch {
    /* gizli modda yazma engellenebilir: parola yalnız bu çağrı için kullanılır */
  }
}

export function yayinParolasiSil(depo: Storage | undefined = oturumDeposu()): void {
  try {
    depo?.removeItem(YAYIN_PAROLA_ANAHTARI)
  } catch {
    /* yoksay */
  }
}

/** Oturumda parola var mı? (yayın düğmesinin hazır olup olmadığını göstermek için) */
export function yayinParolasiVarMi(depo: Storage | undefined = oturumDeposu()): boolean {
  return yayinParolasi(depo) !== ''
}

/** Operatöre parolayı BİR KEZ sorar ve oturuma yazar; boş/iptal → ''. */
export function yayinParolasiSor(mevcut: string = ''): string {
  if (mevcut) return mevcut
  if (typeof window === 'undefined' || typeof window.prompt !== 'function') return ''
  const cevap = window.prompt(
    'MQTT yayın parolası (panel hesabı). Yalnız bu oturum için saklanır; ' +
      'sayfa yenilenirse yeniden sorulur. Parolayı yöneticinizden alın.',
    '',
  )
  const parola = String(cevap ?? '')
  if (parola) yayinParolasiYaz(parola)
  return parola
}

/** Yayın bildirimini MQTT konusuna gönderir (QoS 1, sonra bağlantı kapatılır). */
export async function mqttBildir(
  ad: string,
  zaman: string = new Date().toISOString(),
  secenekler: { parola?: string; depo?: Storage } = {},
): Promise<MqttSonuc> {
  if (!URL_) return { gonderildi: false, hata: 'VITE_MQTT_URL tanımlı değil' }
  const depo = secenekler.depo ?? oturumDeposu()
  const parola = secenekler.parola || yayinParolasi(depo) || yayinParolasiSor()
  // FAIL-CLOSED: sır yoksa yayın denenmez (kimliksiz/parolasız bağlantı denemesi de yok).
  if (!parola) return { gonderildi: false, hata: PAROLA_YOK_MESAJI }
  try {
    const { connect } = await import('mqtt')
    const istemci = connect(URL_, {
      clientId: `panel-${Math.random().toString(16).slice(2, 10)}`,
      username:
        (import.meta.env.VITE_MQTT_KULLANICI as string | undefined) || VARSAYILAN_YAYIN_KULLANICI,
      password: parola,
      connectTimeout: 5000,
      reconnectPeriod: 0,
      clean: true,
    })

    await new Promise<void>((coz, red) => {
      const zamanAsimi = setTimeout(() => red(new Error('MQTT bağlantı zaman aşımı')), 5000)
      istemci.once('connect', () => {
        clearTimeout(zamanAsimi)
        coz()
      })
      istemci.once('error', (hata: Error) => {
        clearTimeout(zamanAsimi)
        red(hata)
      })
    })

    const konu = (import.meta.env.VITE_MQTT_KONU as string | undefined) || 'yourkiosk/yayin'
    await new Promise<void>((coz) => {
      istemci.publish(konu, JSON.stringify({ zaman, kaynak: ad }), { qos: 1 }, () => coz())
    })
    istemci.end(true)
    return { gonderildi: true }
  } catch (hata) {
    return { gonderildi: false, hata: (hata as Error).message }
  }
}

function oturumDeposu(): Storage | undefined {
  try {
    return typeof sessionStorage === 'undefined' ? undefined : sessionStorage
  } catch {
    // gizli modda erişim engellenebilir
    return undefined
  }
}
