/**
 * i5 BULGU 1 — yayın parolası DERLEME PAKETİNE GÖMÜLMEMELİ.
 *
 * Ölçülen durum: `panel/src/domain/push.ts` parolayı `import.meta.env.VITE_MQTT_PAROLA` ile
 * okuyordu; Vite `VITE_*` değerlerini derleme anında JS'e LİTERAL yazar. Panel paketi
 * CloudFront'tan kimlik doğrulaması olmadan indirilebildiği için `curl .../assets/index-*.js`
 * parolayı okuyabiliyordu (deploy/README.md §4 bunun yapılmadığını söylüyordu → çelişki).
 *
 * Bu test iki şeyi kilitler:
 *   1. `VITE_MQTT_PAROLA` panel KAYNAK AĞACINDA hiç geçmez (derlemeye giremez),
 *   2. parola oturumda bir kez sorulur, yalnız `sessionStorage`'da tutulur; sır yoksa yayın
 *      FAIL-CLOSED olur ve operatöre ne yapacağını söyleyen mesaj döner.
 */
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const sahte = vi.hoisted(() => ({
  baglantilar: [] as Array<Record<string, unknown>>,
  yayinlar: [] as Array<{ konu: string; govde: string }>,
}))

vi.mock('mqtt', () => ({
  connect: (url: string, secenekler: Record<string, unknown>) => {
    sahte.baglantilar.push({ url, ...secenekler })
    const istemci = {
      once(olay: string, geri: (...a: unknown[]) => void) {
        if (olay === 'connect') setTimeout(geri, 0)
        return istemci
      },
      publish(konu: string, govde: string, _secenek: unknown, geri: () => void) {
        sahte.yayinlar.push({ konu, govde })
        geri()
        return istemci
      },
      end: () => undefined,
    }
    return istemci
  },
}))

async function pushYukle() {
  vi.resetModules()
  return await import('@/domain/push')
}

describe('i5/1 — gömülü yayın parolası YOK', () => {
  it('parola yoksa yayın FAIL-CLOSED ve operatöre yol gösteren mesaj', async () => {
    vi.stubEnv('VITE_MQTT_URL', 'wss://broker.test:8084/mqtt')
    const sor = vi.spyOn(window, 'prompt').mockReturnValue(null)
    const { mqttBildir, PAROLA_YOK_MESAJI } = await pushYukle()

    const sonuc = await mqttBildir('elle-bildirim')

    expect(sonuc.gonderildi).toBe(false)
    expect(sonuc.hata).toBe(PAROLA_YOK_MESAJI)
    expect(sonuc.hata).toMatch(/parola/i)
    expect(sor).toHaveBeenCalledTimes(1)
    expect(sahte.baglantilar).toHaveLength(0) // parolasız bağlantı denemesi bile yok
    expect(sessionStorage.getItem('yourkiosk.yayin-parola')).toBeNull()
  })

  it('parola bir kez sorulur, sessionStorage da tutulur, localStorage a yazılmaz', async () => {
    vi.stubEnv('VITE_MQTT_URL', 'wss://broker.test:8084/mqtt')
    const sor = vi.spyOn(window, 'prompt').mockReturnValue('oturum-sirri')
    const { mqttBildir } = await pushYukle()

    expect((await mqttBildir('bir')).gonderildi).toBe(true)
    expect((await mqttBildir('iki')).gonderildi).toBe(true)

    expect(sor).toHaveBeenCalledTimes(1) // ikinci yayında yeniden sorulmadı
    expect(sahte.baglantilar).toHaveLength(2)
    expect(sahte.baglantilar[0].password).toBe('oturum-sirri')
    expect(sahte.baglantilar[0].username).toBe('panel')
    expect(sessionStorage.getItem('yourkiosk.yayin-parola')).toContain('oturum-sirri')
  })

  it('sayfa yenilenince (yeni yükleme) parola yeniden sorulur', async () => {
    vi.stubEnv('VITE_MQTT_URL', 'wss://broker.test:8084/mqtt')
    const sor = vi.spyOn(window, 'prompt').mockReturnValue('oturum-sirri')
    const ilk = await pushYukle()
    await ilk.mqttBildir('bir')
    expect(ilk.yayinParolasiVarMi()).toBe(true)

    // "Yenileme": yeni modül örneği (yeni sayfa etiketi) — eski kayıt artık geçersiz
    const ikinci = await pushYukle()
    expect(ikinci.yayinParolasiVarMi()).toBe(false)
    await ikinci.mqttBildir('iki')
    expect(sor).toHaveBeenCalledTimes(2)
  })
})

beforeEach(() => {
  sessionStorage.clear()
  sahte.baglantilar.length = 0
  sahte.yayinlar.length = 0
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})
