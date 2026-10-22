/**
 * Panel → cihaz ANLIK tetikleme (MQTT).
 *
 * NEDEN: 600 cihazda cihaz başına yoklama maliyeti doğrusal büyür (3 sn ≈ 518 M istek/ay).
 * MQTT'de cihaz başına tek kalıcı bağlantı vardır; yayın başına tek mesaj gider (~100 ms).
 *
 * Yapılandırma (panel/.env.local):
 *   VITE_MQTT_URL=wss://broker.example:8084/mqtt
 *   VITE_MQTT_KONU=yourkiosk/yayin
 *   VITE_MQTT_KULLANICI=panel
 *   VITE_MQTT_PAROLA=…
 *
 * Ayarlanmamışsa sessizce atlanır (cihazlar yoklama emniyet ağıyla çalışmaya devam eder).
 * `mqtt` paketi **dinamik** yüklenir: yapılandırma yoksa ana pakete girmez.
 */

const URL_ = import.meta.env.VITE_MQTT_URL as string | undefined

export function mqttYapilandirildi(): boolean {
  return Boolean(URL_)
}

export interface MqttSonuc {
  gonderildi: boolean
  hata?: string
}

/** Yayın bildirimini MQTT konusuna gönderir (QoS 1, sonra bağlantı kapatılır). */
export async function mqttBildir(ad: string, zaman: string = new Date().toISOString()): Promise<MqttSonuc> {
  if (!URL_) return { gonderildi: false, hata: 'VITE_MQTT_URL tanımlı değil' }
  try {
    const { connect } = await import('mqtt')
    const istemci = connect(URL_, {
      clientId: `panel-${Math.random().toString(16).slice(2, 10)}`,
      username: (import.meta.env.VITE_MQTT_KULLANICI as string | undefined) || undefined,
      password: (import.meta.env.VITE_MQTT_PAROLA as string | undefined) || undefined,
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
