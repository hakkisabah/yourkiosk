/**
 * Panel → cihaz ANLIK tetikleme (MQTT).
 *
 * NEDEN: 600 cihazda cihaz başına yoklama maliyeti doğrusal büyür (3 sn ≈ 518 M istek/ay).
 * MQTT'de cihaz başına tek kalıcı bağlantı vardır; yayın başına tek mesaj gider (~100 ms).
 *
 * Yapılandırma (panel/.env.local — SIR DEĞİL, yalnız adres/konu):
 *   VITE_MQTT_URL=wss://broker.example:8084/mqtt
 *   VITE_MQTT_KONU=yourkiosk/yayin
 *
 * YAYIN PAROLASI PAKETE GİRMEZ (27 Ekim i5 bulgusu, yüksek): panel paketi CloudFront'tan kimlik
 * doğrulamasız indirilebildiği için derleme zamanı parola = herkese açık parola. Parola çalışma
 * anında `domain/yayinKimligi` üzerinden oturumdan (sessionStorage) okunur; yoksa yayın
 * FAIL-CLOSED: broker'a hiç bağlanılmaz, sonuç `gonderildi:false` + gerekçe döner.
 *
 * Ayarlanmamışsa sessizce atlanır (cihazlar yoklama emniyet ağıyla çalışmaya devam eder).
 * `mqtt` paketi **dinamik** yüklenir: yapılandırma yoksa ana pakete girmez.
 */

import { yayinKimligiOku, type YayinKimligi } from './yayinKimligi'

const URL_ = import.meta.env.VITE_MQTT_URL as string | undefined

export function mqttYapilandirildi(): boolean {
  return Boolean(URL_)
}

export interface MqttSonuc {
  gonderildi: boolean
  hata?: string
}

/**
 * Yayın bildirimini MQTT konusuna gönderir (QoS 1, sonra bağlantı kapatılır).
 *
 * `kimlik` verilmezse oturumdaki yayın kimliği kullanılır. Kimlik yoksa **hiç bağlanılmaz**:
 * parolasız bağlanma denemesi broker tarafından reddedilir ve hata kullanıcıya anlamsız gelir.
 */
export async function mqttBildir(ad: string, zaman: string = new Date().toISOString(),
  kimlik?: YayinKimligi | null): Promise<MqttSonuc> {
  if (!URL_) return { gonderildi: false, hata: 'VITE_MQTT_URL tanımlı değil' }
  const oturumKimligi = kimlik === undefined ? yayinKimligiOku() : kimlik
  if (!oturumKimligi) {
    return { gonderildi: false, hata: 'yayın kimliği yok — yayın parolası bu oturumda girilmedi' }
  }
  try {
    const { connect } = await import('mqtt')
    const istemci = connect(URL_, {
      clientId: `panel-${Math.random().toString(16).slice(2, 10)}`,
      username: oturumKimligi.kullanici,
      password: oturumKimligi.parola,
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
