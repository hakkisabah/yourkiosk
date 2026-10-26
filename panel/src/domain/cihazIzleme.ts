/**
 * CİHAZ İZLEME — 600 cihazın çevrimiçi/çevrimdışı durumu (MQTT kalp atışı).
 *
 * Cihaz (`kiosk/core/push.py`) MQTT'ye **retained** kalp atışı yayınlar:
 *   konu  : `<taban>/durum/<cihazId>`      (taban: `VITE_MQTT_KONU`nun son parçası atılmış hâli)
 *   gövde : `{"cevrimici":true,"zaman":"2026-10-25T10:00:00Z","mod":"qt","surum":""}`
 * Bağlantı koparsa broker LWT ile aynı konuya `cevrimici:false` yazar (retained).
 *
 * PANEL YALNIZ OKUR: cihazlara komut göndermez (o yol `kiosk/tools/komut_gonder.py`).
 * MQTT yapılandırılmamışsa izleme sessizce kapalıdır — panel çalışmaya devam eder.
 */

import { guvenliAdresMi } from './izlemeKimligi'

/** Bir cihazın "çevrimiçi" sayılması için son kalp atışının yaşı (dakika).
 *  Cihaz 5 dakikada bir yayınlar; 15 dk = 3 kaçırılmış atış (ağ dalgalanmasına tolerans). */
export const VARSAYILAN_ESIK_DK = 15

/**
 * GİRDİ SINIRLARI (i5 bulgusu) — `durum/+` konusuna yazabilen bir hesap (ya da ele geçirilmiş
 * bir cihaz) retained gövdeyi sınırsız büyütebilir. Sınırlar JSON.parse'tan ÖNCE uygulanır:
 * büyük gövde hiç ayrıştırılmaz, kimliği uzun/bozuk mesajlar hiç haritaya girmez, harita
 * 2000 kayıtta durur (en eski kayıt düşer). Aksi hâlde panel belleği ve arayüzü kilitlenir.
 */
export const AZAMI_GOVDE_BAYT = 512
export const AZAMI_KIMLIK_UZUNLUK = 64
export const AZAMI_CIHAZ = 2000
/** İzleme oturumunun ardışık yeniden bağlanma denemesi üst sınırı (sonsuz döngüyü keser). */
export const AZAMI_YENIDEN_BAGLANMA = 5
/** Cihaz kimliği deseni: konu güvenliği için harf/rakam/alt çizgi/tire. */
const KIMLIK_DESENI = /^[A-Za-z0-9_-]+$/

export interface CihazDurumu {
  cihazId: string
  cevrimici: boolean
  /** ISO damga (cihazın bildirdiği — yalnız BİLGİ; yaş hesabı `alindi` ile yapılır) */
  zaman: string
  mod: string
  /** Panelin mesajı ALDIĞI an (epoch ms). Saat kaymasına dayanıklı çevrimiçilik için. */
  alindi: number
}

/** Yayın konusundan cihaz durum konusu: `yourkiosk/yayin` → `yourkiosk/durum/+`. */
export function durumKonusu(yayinKonusu: string): string {
  const temiz = String(yayinKonusu ?? '').trim().replace(/\/+$/, '')
  const taban = temiz.includes('/') ? temiz.slice(0, temiz.lastIndexOf('/')) : temiz
  return `${taban || 'yourkiosk'}/durum/+`
}

/** Durum konusundan cihaz kimliğini çıkarır (`yourkiosk/durum/C1` → `C1`).
 *
 * GÜVENLİK: kimlik uzunluk ve karakter denetiminden geçer. Aksi hâlde 5000 karakterlik bir
 * kimlik haritaya girer ve arayüzü kilitler (i5 bulgusu, ölçüldü: kabul ediliyordu).
 * Geçersizse boş dize döner → mesaj tümüyle yok sayılır.
 */
export function konudanCihaz(konu: string): string {
  const parcalar = String(konu ?? '').split('/').filter(Boolean)
  const kimlik = parcalar.length ? parcalar[parcalar.length - 1] : ''
  if (!kimlik || kimlik.length > AZAMI_KIMLIK_UZUNLUK) return ''
  return KIMLIK_DESENI.test(kimlik) ? kimlik : ''
}

/** Kalp atışı gövdesini çözer; bozuk/eksik gövdede null.
 *
 * `alindi`: mesajın panele ulaştığı an (epoch ms). Çevrimiçilik bu damgaya göre hesaplanır:
 * RTC/NTP'si olmayan kiosk PC'lerinde cihaz saati saatlerce kayabilir; cihazın kendi `zaman`ı
 * esas alınırsa ayakta olan cihaz "çevrimdışı" görünür (i5 bulgusu).
 */
export function kalpAtisiCoz(
  konu: string,
  govde: string | Uint8Array,
  alindi: number = Date.now(),
): CihazDurumu | null {
  const cihazId = konudanCihaz(konu)
  if (!cihazId) return null
  // BOYUT SINIRI (i5 bulgusu): JSON.parse'tan ÖNCE. 1 MB'lık retained gövde ayrıştırılmaz.
  const bayt = typeof govde === 'string' ? new TextEncoder().encode(govde).length : govde.length
  if (!Number.isFinite(bayt) || bayt === 0 || bayt > AZAMI_GOVDE_BAYT) return null
  let belge: unknown
  try {
    const metin = typeof govde === 'string' ? govde : new TextDecoder().decode(govde)
    belge = JSON.parse(metin)
  } catch {
    return null
  }
  if (!belge || typeof belge !== 'object' || Array.isArray(belge)) return null
  const k = belge as Record<string, unknown>
  const zaman = typeof k.zaman === 'string' ? k.zaman : ''
  if (!zaman && k.cevrimici !== true) return null
  return {
    cihazId,
    cevrimici: k.cevrimici === true,
    zaman,
    mod: typeof k.mod === 'string' ? k.mod : '',
    alindi,
  }
}

/** Son kalp atışı eşikten yeni mi?
 *
 * `alindi` verilirse yaş, cihazın saatine DEĞİL mesajın geliş anına göre ölçülür (önerilen).
 * `zaman` yalnız `alindi` yoksa (eski kayıt/test) kullanılır.
 */
export function cevrimiciMi(
  zaman: string,
  simdi: Date = new Date(),
  esikDk = VARSAYILAN_ESIK_DK,
  alindi?: number,
): boolean {
  const t = typeof alindi === 'number' && Number.isFinite(alindi) ? alindi : Date.parse(zaman)
  if (!Number.isFinite(t)) return false
  const yasDk = (simdi.getTime() - t) / 60_000
  return yasDk <= esikDk
}

/** Kaydın tazeliği: `alindi` varsa ona, yoksa cihazın `zaman`ına göre. */
function tazeMi(durum: CihazDurumu, simdi: Date, esikDk: number): boolean {
  return cevrimiciMi(durum.zaman, simdi, esikDk, durum.alindi)
}

/** Bir cihazın gösterilecek durumu: `cevrimici` + bayat kalp atışı "çevrimdışı" sayılır. */
export function durumEtiketi(
  durum: CihazDurumu | undefined,
  simdi: Date = new Date(),
  esikDk = VARSAYILAN_ESIK_DK,
): { metin: string; renk: string } {
  if (!durum) return { metin: 'bilinmiyor', renk: 'grey' }
  if (durum.cevrimici && tazeMi(durum, simdi, esikDk)) return { metin: 'çevrimiçi', renk: 'success' }
  return { metin: 'çevrimdışı', renk: 'error' }
}

/** Özet: kaç cihaz çevrimiçi / çevrimdışı (panel başlığı için). */
export function izlemeOzeti(
  durumlar: Map<string, CihazDurumu>,
  cihazlar: string[],
  simdi: Date = new Date(),
  esikDk = VARSAYILAN_ESIK_DK,
): { cevrimici: number; cevrimdisi: number; bilinmiyor: number } {
  let cevrimici = 0
  let cevrimdisi = 0
  let bilinmiyor = 0
  for (const cihaz of cihazlar) {
    const d = durumlar.get(cihaz)
    if (!d) bilinmiyor += 1
    else if (d.cevrimici && tazeMi(d, simdi, esikDk)) cevrimici += 1
    else cevrimdisi += 1
  }
  return { cevrimici, cevrimdisi, bilinmiyor }
}

export interface IzlemeOturumu {
  durdur: () => void
}

/**
 * Haritaya cihaz durumu ekler — YENİ Map döndürür (Vue tepkiselliği için).
 *
 * GÜVENLİK (i5 bulgusu): harita sınırsız büyümemeli. `durum/+` konusuna yazan biri binlerce
 * farklı kimlik yayınlayıp paneli şişirebilir. `AZAMI_CIHAZ` aşılırsa EN ESKİ kayıt düşer
 * (yeni kimlik yine girer; böylece aktif cihazlar görünür kalır).
 */
export function durumEkle(
  harita: Map<string, CihazDurumu>,
  durum: CihazDurumu,
  azami: number = AZAMI_CIHAZ,
): Map<string, CihazDurumu> {
  const yeni = new Map(harita)
  yeni.delete(durum.cihazId)
  yeni.set(durum.cihazId, durum)
  while (yeni.size > Math.max(1, azami)) {
    const enEski = yeni.keys().next()
    if (enEski.done) break
    yeni.delete(enEski.value)
  }
  return yeni
}

export interface IzlemeAyarlari {
  /** Broker adresi (wss://host:8084/mqtt) — SIR DEĞİL, yayınlanabilir. */
  url: string
  /** Yayın konusu; durum konusu bundan türetilir. */
  konu?: string
  /** Okuma yetkili kullanıcı (`panel-izleme`) — çalışma anında girilir, pakete GÖMÜLMEZ. */
  kullanici: string
  /** Okuma parolası — yalnız bellekte/sessionStorage'da; derleme paketine yazılmaz. */
  parola: string
}

/** İzleme oturumunun bağlantı durumu. */
export type BaglantiDurumu = 'baglaniyor' | 'bagli' | 'koptu' | 'hata'

export interface IzlemeOlaylari {
  /** Bağlantı durumu değişti (abonelik reddi dahil). */
  durum?: (durum: BaglantiDurumu, ayrinti?: string) => void
  /** Test için: `mqtt.connect` yerine kullanılacak işlev. */
  baglan?: (url: string, secenekler: Record<string, unknown>) => MqttIstemci
}

/** Test edilebilirlik için en küçük istemci arayüzü (mqtt.js'in kullandığımız yüzeyi). */
export interface MqttIstemci {
  on: (olay: string, dinleyici: (...args: never[]) => void) => unknown
  subscribe: (
    konu: string,
    secenekler?: Record<string, unknown>,
    geriCagri?: (hata: Error | null, granted?: Array<{ topic: string; qos: number }>) => void,
  ) => unknown
  end: (zorla?: boolean) => unknown
}

/**
 * MQTT izlemesini başlatır; adres yoksa `null` (panel sessizce çalışır).
 *
 * GÜVENLİK (i5 bulgusu): parola `import.meta.env`ten OKUNMAZ. Panel paketi CloudFront'tan
 * kimlik doğrulaması olmadan indirilebildiği için `VITE_MQTT_PAROLA` derlemeye gömülürse sır
 * herkese açık olur. Bu yüzden kimlik çalışma anında verilir (bkz. `izlemeKimligi.ts`).
 * İzleme kullanıcısı broker ACL'inde YALNIZ `durum/+` okur; yayın yazamaz.
 *
 * `mqtt` paketi DİNAMİK yüklenir: izleme kapalıysa ana pakete girmez.
 */
export async function izlemeBaslat(
  geriCagri: (durum: CihazDurumu) => void,
  ayarlar: IzlemeAyarlari,
  olaylar: IzlemeOlaylari = {},
): Promise<IzlemeOturumu | null> {
  const url = String(ayarlar.url ?? '').trim()
  if (!url) return null
  // İKİNCİ KAPI (26 Ekim i5 bulgusu): adres çağırandan ne gelirse gelsin `connect`e verilmeden
  // önce şema denetlenir. `ws://`/`http://` ile parola düz metin gider; `http://` hiç bağlanmaz.
  if (!guvenliAdresMi(url)) {
    olaylar.durum?.('hata', `broker adresi güvenli değil (${url}) — wss://… bekleniyor`)
    return null
  }
  const { connect } = olaylar.baglan
    ? { connect: olaylar.baglan }
    : ((await import('mqtt')) as unknown as {
        connect: (url: string, secenekler: Record<string, unknown>) => MqttIstemci
      })
  const konu = durumKonusu(String(ayarlar.konu ?? 'yourkiosk/yayin'))
  olaylar.durum?.('baglaniyor')
  // SONSUZ YENİDEN BAĞLANMA YOK (i5 bulgusu): parola yanlışsa/ACL reddediyorsa mqtt.js
  // sonsuza kadar 5 sn'de bir dener — broker'da kimlik doğrulama trafiği, panelde sürekli
  // durum değişimi. Ardışık N başarısız denemeden sonra oturum kapatılır ve hata bildirilir.
  let deneme = 0
  const istemci = connect(url, {
    clientId: `panel-izleme-${Math.random().toString(16).slice(2, 10)}`,
    username: ayarlar.kullanici || undefined,
    password: ayarlar.parola || undefined,
    connectTimeout: 5000,
    reconnectPeriod: 5000,
    clean: true,
  })

  istemci.on('connect', () => {
    deneme = 0
    istemci.subscribe(konu, { qos: 1 }, (hata, granted) => {
      // mqtt.js abonelik reddini (ACL) HATA olarak değil, granted[qos]=128 ile bildirir.
      const red = (granted ?? []).some((g) => (g?.qos ?? 0) >= 128)
      if (hata || red) {
        olaylar.durum?.('hata', hata?.message ?? 'abonelik reddedildi (ACL)')
        return
      }
      olaylar.durum?.('bagli')
    })
  })
  istemci.on('reconnect', () => {
    deneme += 1
    if (deneme > AZAMI_YENIDEN_BAGLANMA) {
      olaylar.durum?.(
        'hata',
        `broker'a ${AZAMI_YENIDEN_BAGLANMA} kez yeniden bağlanılamadı (kimlik/ACL?) — izleme durduruldu`,
      )
      istemci.end(true)
    }
  })
  istemci.on('message', (gelenKonu: string, govde: Uint8Array) => {
    // GELİŞ ANI damgası: cihaz saati kaymış olsa da çevrimiçilik doğru hesaplanır.
    const durum = kalpAtisiCoz(gelenKonu, govde, Date.now())
    if (durum) geriCagri(durum)
  })
  istemci.on('offline', () => olaylar.durum?.('koptu', 'broker bağlantısı koptu'))
  istemci.on('close', () => olaylar.durum?.('koptu', 'bağlantı kapandı'))
  // Hata dinlenmezse mqtt.js "error" olayında süreç fırlatır; durumu raporla ama çökme.
  istemci.on('error', (hata: Error) => olaylar.durum?.('hata', hata?.message ?? 'MQTT hatası'))
  return { durdur: () => istemci.end(true) }
}
