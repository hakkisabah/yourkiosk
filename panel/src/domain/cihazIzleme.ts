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

/** Bir cihazın "çevrimiçi" sayılması için son kalp atışının yaşı (dakika).
 *  Cihaz 5 dakikada bir yayınlar; 15 dk = 3 kaçırılmış atış (ağ dalgalanmasına tolerans). */
export const VARSAYILAN_ESIK_DK = 15

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

/** Durum konusundan cihaz kimliğini çıkarır (`yourkiosk/durum/C1` → `C1`). */
export function konudanCihaz(konu: string): string {
  const parcalar = String(konu ?? '').split('/').filter(Boolean)
  return parcalar.length ? parcalar[parcalar.length - 1] : ''
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
  const { connect } = olaylar.baglan
    ? { connect: olaylar.baglan }
    : ((await import('mqtt')) as unknown as {
        connect: (url: string, secenekler: Record<string, unknown>) => MqttIstemci
      })
  const konu = durumKonusu(String(ayarlar.konu ?? 'yourkiosk/yayin'))
  olaylar.durum?.('baglaniyor')
  const istemci = connect(url, {
    clientId: `panel-izleme-${Math.random().toString(16).slice(2, 10)}`,
    username: ayarlar.kullanici || undefined,
    password: ayarlar.parola || undefined,
    connectTimeout: 5000,
    reconnectPeriod: 5000,
    clean: true,
  })

  istemci.on('connect', () => {
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
