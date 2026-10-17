/**
 * CİHAZ ÖNBELLEĞİ (tarayıcı sürümü) — Qt tarafındaki `core/onbellek.py` ile aynı kurallar.
 *
 * Amaç: aynı içerik tekrar gösterilirken **ağa çıkılmaması** (maliyet + hız).
 * Tarayıcıda bunun karşılığı Cache Storage'dır (kalıcı profil klasöründe saklanır).
 *
 * Kurallar:
 *  • **Geçersizleşme:** veri önbelleği `lastupdate` damgasına bağlıdır; damga değiştiyse
 *    kayıt geçersiz sayılır ve içerik yeniden alınır.
 *  • **Süre sonu:** her görselin `son_gosterim` zamanı tutulur; `saklamaGun` gün boyunca
 *    gösterilmeyen görsel (ya da veride artık geçmeyen) silinir.
 *  • **Bütünlük:** kayıtlar sha256 ile saklanır ve okurken doğrulanır (bozuk kayıt atılır).
 *
 * ÖNEMLİ (tarayıcı kuralı): Cache Storage anahtarları **geçerli http(s) URL** olmalıdır.
 * `cache.put('meta:lastupdate', …)` → "Request scheme 'meta' is unsupported" hatası verir.
 * Bu yüzden anahtarlar sayfanın kaynağı üzerinden üretilir:
 * `http://127.0.0.1:8090/__onbellek/veri/lastSystemData.json` gibi.
 *
 * Ayrıca **her yazma hataya dayanıklıdır**: önbellek bozuksa/kapalıysa gösterim devam eder
 * (önbellek sessizce devre dışı bırakılır, ekran boş kalmaz).
 *
 * Test edilebilirlik: `Cache` benzeri bir nesne dışarıdan verilebilir; testlerdeki sahte
 * depo GERÇEK Cache Storage kurallarını uygular (http(s) dışı anahtarı reddeder).
 */

/** Tarayıcı `Cache` arayüzünün kullandığımız kadarı (test edilebilir).
 *
 * DİKKAT: gerçek `Cache.keys()` **Request nesneleri** döndürür (string değil).
 * `match`/`delete` ise anahtar olarak string (mutlak URL) ya da Request kabul eder.
 */
export interface OnbellekDeposu {
  match(sorgu: string): Promise<Yanit | undefined>
  put(sorgu: string, yanit: Yanit): Promise<void>
  delete(sorgu: string): Promise<boolean>
  keys(): Promise<readonly unknown[]>
}

/** `Response` benzeri en küçük arayüz. */
export interface Yanit {
  ok?: boolean
  status?: number
  headers: { get(ad: string): string | null }
  arrayBuffer(): Promise<ArrayBuffer>
  text(): Promise<string>
  blob?(): Promise<Blob>
}

export interface KayitBilgisi {
  url: string
  alindi: string
  sonGosterim: string
  gosterim: number
  bayt: number
  sha256: string
  damga: string
  icerikTuru: string
}

const ONEK = '__onbellek'
const VERI_YOLU = `${ONEK}/veri/`
const GORSEL_YOLU = `${ONEK}/gorsel/`
const META_YOLU = `${ONEK}/meta/lastupdate`
export const ONBELLEK_ADI = 'yourkiosk-onbellek'

/** Sayfa kaynağına göre GEÇERLİ (http/https) bir önbellek anahtarı üretir. */
function anahtar(yol: string): string {
  const kok = (globalThis as { location?: { origin?: string } }).location?.origin || 'http://127.0.0.1'
  try {
    return new URL(yol, `${kok}/`).toString()
  } catch {
    return `http://127.0.0.1/${yol}`
  }
}

/** Kısa, kararlı, eşzamanlı özet (uzun görsel adreslerini anahtara sığdırmak için). */
function ozet(metin: string): string {
  let h = 5381
  for (let i = 0; i < metin.length; i += 1) h = ((h << 5) + h + metin.charCodeAt(i)) >>> 0
  return h.toString(16).padStart(8, '0')
}

const gorselAnahtari = (url: string): string => anahtar(GORSEL_YOLU + ozet(url))

/**
 * `Cache.keys()` çıktısını karşılaştırılabilir bir metne çevirir.
 * Gerçek tarayıcı `Request` nesnesi döndürür; testler/sahte depolar string döndürür → ikisi de.
 */
export function anahtarMetni(k: unknown): string {
  if (typeof k === 'string') return k
  const url = (k as { url?: unknown } | null)?.url
  return typeof url === 'string' ? url : String(k)
}

/** sha256 (tarayıcıda crypto.subtle, testte Node'un webcrypto'su). */
export async function sha256(veri: ArrayBuffer): Promise<string> {
  const tuz = globalThis.crypto?.subtle
  if (!tuz) return ''
  const ozet_ = await tuz.digest('SHA-256', veri)
  return [...new Uint8Array(ozet_)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

export class Onbellek {
  private depo: OnbellekDeposu | null = null

  constructor(
    private readonly saklamaGun: number = 2,
    depo?: OnbellekDeposu | null,
  ) {
    this.depo = depo ?? null
  }

  /**
   * Tarayıcı deposunu bağlar ve **çalışıp çalışmadığını dener** (yaz-oku-sil).
   * Çalışmıyorsa önbellek devre dışı kalır; gösterim etkilenmez.
   */
  async bagla(ad: string = ONBELLEK_ADI): Promise<boolean> {
    const caches = (globalThis as unknown as { caches?: { open(ad: string): Promise<OnbellekDeposu> } }).caches
    if (!caches) return false
    try {
      this.depo = await caches.open(ad)
      // deneme: yazma/okuma/silme gerçekten çalışıyor mu?
      const deneme = anahtar(`${ONEK}/deneme`)
      await this.depo.put(
        deneme,
        new Response('ok', { headers: { 'Content-Type': 'text/plain' } }) as unknown as Yanit,
      )
      await this.depo.match(deneme)
      await this.depo.delete(deneme)
      return true
    } catch (hata) {
      this.depo = null
      console.warn('[yourkiosk] önbellek kullanılamıyor, devre dışı:', hata)
      return false
    }
  }

  get etkin(): boolean {
    return this.depo !== null
  }

  /** Yazma hatası: önbelleği kapat, gösterimi sürdür. */
  private _kapat(hata: unknown): void {
    this.depo = null
    console.warn('[yourkiosk] önbellek yazılamadı, devre dışı bırakıldı:', hata)
  }

  private async _meta(ad: string): Promise<Record<string, unknown>> {
    if (!this.depo) return {}
    try {
      const yanit = await this.depo.match(anahtar(ad))
      if (!yanit) return {}
      return JSON.parse(await yanit.text()) as Record<string, unknown>
    } catch {
      return {}
    }
  }

  private async _metaYaz(ad: string, veri: Record<string, unknown>): Promise<void> {
    if (!this.depo) return
    try {
      await this.depo.put(
        anahtar(ad),
        new Response(JSON.stringify(veri), { headers: { 'Content-Type': 'application/json' } }) as unknown as Yanit,
      )
    } catch (hata) {
      this._kapat(hata)
    }
  }

  // ---------------------------------------------------------------- veri damgası
  /** Saklanan `lastupdate` damgası (yoksa ""). */
  async damga(): Promise<string> {
    const meta = await this._meta(META_YOLU)
    return String(meta.damga ?? '')
  }

  /** Damgayı saklar; **değiştiyse** true döner (ilk kayıtta false). */
  async damgaYaz(damga: string): Promise<boolean> {
    const onceki = await this.damga()
    await this._metaYaz(META_YOLU, { damga })
    return Boolean(onceki) && onceki !== damga
  }

  // ---------------------------------------------------------------- veri (JSON)
  /** Damga eşleşiyorsa önbellekten döner; aksi hâlde null (çağıran ağdan alır). */
  async veriOku(ad: string, damga: string): Promise<ArrayBuffer | null> {
    if (!this.depo) return null
    const k = anahtar(VERI_YOLU + ad)
    const yanit = await this.depo.match(k)
    if (!yanit) return null
    const kayitli = yanit.headers.get('x-damga') ?? ''
    if (damga && kayitli !== damga) return null
    const govde = await yanit.arrayBuffer()
    const beklenen = yanit.headers.get('x-sha256') ?? ''
    if (beklenen && (await sha256(govde)) !== beklenen) {
      await this.depo.delete(k)
      return null
    }
    return govde
  }

  async veriYaz(ad: string, govde: ArrayBuffer, damga: string): Promise<void> {
    if (!this.depo) return
    try {
      await this.depo.put(
        anahtar(VERI_YOLU + ad),
        new Response(govde, {
          headers: { 'x-damga': damga, 'x-sha256': await sha256(govde), 'Content-Type': 'application/json' },
        }) as unknown as Yanit,
      )
    } catch (hata) {
      this._kapat(hata)
    }
  }

  // ---------------------------------------------------------------- görseller
  async gorselOku(url: string): Promise<ArrayBuffer | null> {
    if (!this.depo) return null
    const k = gorselAnahtari(url)
    const yanit = await this.depo.match(k)
    if (!yanit) return null
    const govde = await yanit.arrayBuffer()
    const beklenen = yanit.headers.get('x-sha256') ?? ''
    if (beklenen && (await sha256(govde)) !== beklenen) {
      await this.depo.delete(k)
      return null
    }
    return govde
  }

  async gorselYaz(url: string, govde: ArrayBuffer, icerikTuru = '', damga = ''): Promise<void> {
    if (!this.depo) return
    const simdi = new Date().toISOString()
    try {
      await this.depo.put(
        gorselAnahtari(url),
        new Response(govde, {
          headers: {
            'Content-Type': icerikTuru || 'application/octet-stream',
            'x-url': url,
            'x-alindi': simdi,
            'x-son-gosterim': simdi,
            'x-gosterim': '0',
            'x-damga': damga,
            'x-sha256': await sha256(govde),
          },
        }) as unknown as Yanit,
      )
    } catch (hata) {
      this._kapat(hata)
    }
  }

  /** Görsel gösterildi: son gösterim zamanı ve sayaç güncellenir (süre sonu için). */
  async gorselGosterildi(url: string): Promise<void> {
    if (!this.depo) return
    const k = gorselAnahtari(url)
    const yanit = await this.depo.match(k)
    if (!yanit) return
    const govde = await yanit.arrayBuffer()
    const basliklar = new Headers()
    for (const ad of ['Content-Type', 'x-url', 'x-alindi', 'x-damga', 'x-sha256']) {
      const deger = yanit.headers.get(ad)
      if (deger) basliklar.set(ad, deger)
    }
    basliklar.set('x-son-gosterim', new Date().toISOString())
    basliklar.set('x-gosterim', String(Number(yanit.headers.get('x-gosterim') ?? '0') + 1))
    try {
      await this.depo.put(k, new Response(govde, { headers: basliklar }) as unknown as Yanit)
    } catch (hata) {
      this._kapat(hata)
    }
  }

  async gorselSil(url: string): Promise<void> {
    if (!this.depo) return
    await this.depo.delete(gorselAnahtari(url))
  }

  /** Önbellekteki görsel kayıtlarının bilgileri (teşhis/test/bakım). */
  async gorselBilgileri(): Promise<KayitBilgisi[]> {
    if (!this.depo) return []
    const kayitlar: KayitBilgisi[] = []
    for (const ham of await this.depo.keys()) {
      // gerçek tarayıcı Request döndürür → metne çevir (string de olabilir)
      const k = anahtarMetni(ham)
      if (!k.includes(GORSEL_YOLU)) continue
      const yanit = await this.depo.match(k)
      if (!yanit) continue
      kayitlar.push({
        url: yanit.headers.get('x-url') ?? '',
        alindi: yanit.headers.get('x-alindi') ?? '',
        sonGosterim: yanit.headers.get('x-son-gosterim') ?? '',
        gosterim: Number(yanit.headers.get('x-gosterim') ?? '0'),
        bayt: Number(yanit.headers.get('Content-Length') ?? '0'),
        sha256: yanit.headers.get('x-sha256') ?? '',
        damga: yanit.headers.get('x-damga') ?? '',
        icerikTuru: yanit.headers.get('Content-Type') ?? '',
      })
    }
    return kayitlar.filter((k) => Boolean(k.url))
  }

  /**
   * Bakım (Qt `onbellek.bakim` ile aynı): süresi geçenleri ve veride artık geçmeyen
   * görselleri siler. `gecerliUrlKumesi` verilmezse artık-temizliği atlanır.
   */
  async bakim(an: Date = new Date(), gecerliUrlKumesi?: Set<string>): Promise<{ silinen: number }> {
    if (!this.depo) return { silinen: 0 }
    let silinen = 0
    const sinir = an.getTime() - Math.max(0, this.saklamaGun) * 86400000
    for (const kayit of await this.gorselBilgileri()) {
      const taze = Date.parse(kayit.sonGosterim || kayit.alindi || '')
      const artik = gecerliUrlKumesi !== undefined && !gecerliUrlKumesi.has(kayit.url)
      const eski = Number.isFinite(taze) && taze < sinir
      if (artik || eski) {
        await this.gorselSil(kayit.url)
        silinen += 1
      }
    }
    return { silinen }
  }

  /** Tüm önbelleği boşaltır (panelden/teşhisten). */
  async bosalt(): Promise<number> {
    if (!this.depo) return 0
    const anahtarlar = await this.depo.keys()
    let silinen = 0
    for (const ham of anahtarlar) {
      if (await this.depo.delete(anahtarMetni(ham))) silinen += 1
    }
    return silinen
  }
}
