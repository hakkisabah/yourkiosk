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
  /** ISO damga (cihazın bildirdiği) */
  zaman: string
  mod: string
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

/** Kalp atışı gövdesini çözer; bozuk/eksik gövdede null. */
export function kalpAtisiCoz(konu: string, govde: string | Uint8Array): CihazDurumu | null {
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
  if (!zaman) return null
  return {
    cihazId,
    cevrimici: k.cevrimici === true,
    zaman,
    mod: typeof k.mod === 'string' ? k.mod : '',
  }
}

/** Son kalp atışı eşikten yeni mi? (zaman okunamazsa false) */
export function cevrimiciMi(zaman: string, simdi: Date = new Date(), esikDk = VARSAYILAN_ESIK_DK): boolean {
  const t = Date.parse(zaman)
  if (!Number.isFinite(t)) return false
  const yasDk = (simdi.getTime() - t) / 60_000
  return yasDk <= esikDk
}

/** Bir cihazın gösterilecek durumu: `cevrimici` + bayat kalp atışı "çevrimdışı" sayılır. */
export function durumEtiketi(
  durum: CihazDurumu | undefined,
  simdi: Date = new Date(),
  esikDk = VARSAYILAN_ESIK_DK,
): { metin: string; renk: string } {
  if (!durum) return { metin: 'bilinmiyor', renk: 'grey' }
  if (durum.cevrimici && cevrimiciMi(durum.zaman, simdi, esikDk)) return { metin: 'çevrimiçi', renk: 'success' }
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
    else if (d.cevrimici && cevrimiciMi(d.zaman, simdi, esikDk)) cevrimici += 1
    else cevrimdisi += 1
  }
  return { cevrimici, cevrimdisi, bilinmiyor }
}

export interface IzlemeOturumu {
  durdur: () => void
}

/**
 * MQTT izlemesini başlatır; yapılandırma yoksa `null` (panel sessizce çalışır).
 * `mqtt` paketi DİNAMİK yüklenir: yapılandırma yoksa ana pakete girmez.
 */
export async function izlemeBaslat(
  geriCagri: (durum: CihazDurumu) => void,
  env: Record<string, string | undefined> = import.meta.env as unknown as Record<string, string | undefined>,
): Promise<IzlemeOturumu | null> {
  const url = String(env.VITE_MQTT_URL ?? '').trim()
  if (!url) return null
  const { connect } = await import('mqtt')
  const konu = durumKonusu(String(env.VITE_MQTT_KONU ?? 'yourkiosk/yayin'))
  const istemci = connect(url, {
    clientId: `panel-izleme-${Math.random().toString(16).slice(2, 10)}`,
    username: env.VITE_MQTT_KULLANICI || undefined,
    password: env.VITE_MQTT_PAROLA || undefined,
    connectTimeout: 5000,
    reconnectPeriod: 5000,
    clean: true,
  })
  istemci.on('connect', () => istemci.subscribe(konu, { qos: 1 }))
  istemci.on('message', (gelenKonu: string, govde: Uint8Array) => {
    const durum = kalpAtisiCoz(gelenKonu, govde)
    if (durum) geriCagri(durum)
  })
  // Hata dinlenmezse mqtt.js "error" olayında süreç fırlatır; sessizce yut.
  istemci.on('error', () => undefined)
  return { durdur: () => istemci.end(true) }
}
