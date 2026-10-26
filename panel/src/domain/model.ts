/**
 * VERİ MODELİ — tipler + doğrulama (tek kaynak: `kiosk/core/model.py`).
 *
 * `model.generated.json` üretilmiştir; elle düzenlenmez:
 *     cd kiosk && python3 tools/model_disa_aktar.py
 * (kiosk testi dosya güncel değilse kırılır → üç taraf ayrışamaz.)
 *
 * NEDEN: yayın hedefleme alanları (ilceId/bolgeId/cihazId) Qt, panel ve tarayıcıda AYNI ad/tip/
 * kurallarla kullanılmalı. Daha önce bu birlik yoktu ve `durum.json` gibi alanlar sessizce ayrıştı
 * ("Cannot set properties of undefined").
 */
import ham from './model.generated.json'

export type AlanTipi = 'tarih' | 'https_adres' | 'saniye' | 'metin' | 'nesne'

export interface AlanTanimi {
  ad: string
  tip: AlanTipi
  zorunlu: boolean
  etiket: string
  aciklama: string
  alias?: string[]
}

export interface VeriModeli {
  _aciklama: string
  surum: number
  yayin_alanlari: AlanTanimi[]
  durum_alanlari: AlanTanimi[]
  kapsam_kurallari: {
    bos_kisit_yok: boolean
    coklu_alan: string
    en_dar: string[]
    bilinmeyen_cihaz: string
  }
}

export const model = ham as unknown as VeriModeli
export const yayinAlanlari: AlanTanimi[] = model.yayin_alanlari

/** İnsan okur hedef açıklaması (panel arayüzünde gösterilir). */
export const KAPSAM_ACIKLAMASI =
  'Hedef boş bırakılırsa yayın TÜM cihazlarda gösterilir. İlçe/bölge/cihaz birlikte seçilirse ' +
  'hepsi eşleşmeli (VE). Cihaz kendi konumunu bilmiyorsa hedefli yayın gösterilmez.'

/** Yayın kaydının kapsam alanları — boş string = kısıt yok. */
export interface YayinKapsamiDto {
  ilceId?: string
  bolgeId?: string
  cihazId?: string
}

/** Panelde kaydetmeden önce doğrulanan yayın kaydı (DTO). */
export interface YayinDto {
  start?: string
  end?: string
  contentUrl?: string
  duration?: string | number
  ilceId?: string
  bolgeId?: string
  cihazId?: string
  [k: string]: unknown
}

const TARIH = /^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?)?/
const HTTPS = /^https:\/\/[^\s]+$/i

/** Alanın alias'ları dahil ilk dolu değerini döner. */
export function alanDegeri(kayit: Record<string, unknown>, alan: AlanTanimi): unknown {
  const adlar = [alan.ad, ...(alan.alias ?? [])]
  for (const ad of adlar) {
    const deger = kayit[ad]
    if (deger !== undefined && deger !== null && String(deger).trim() !== '') return deger
  }
  return undefined
}

/**
 * Tek yayın kaydını doğrular. Dönen liste boşsa kayıt geçerli.
 * Kurallar model.generated.json'dan gelir (zorunlu alanlar + tip biçimleri).
 */
export function yayinDogrula(kayit: YayinDto): string[] {
  const hatalar: string[] = []
  const ham = kayit as unknown as Record<string, unknown>
  for (const alan of yayinAlanlari) {
    const deger = alanDegeri(ham, alan)
    if (deger === undefined) {
      if (alan.zorunlu) hatalar.push(`${alan.etiket}: zorunlu alan boş`)
      continue
    }
    const metin = String(deger).trim()
    if (alan.tip === 'tarih' && !TARIH.test(metin)) {
      hatalar.push(`${alan.etiket}: tarih biçimi geçersiz (${metin}) — ör. 2026-10-24T08:30:00`)
    }
    if (alan.tip === 'https_adres' && !HTTPS.test(metin)) {
      hatalar.push(`${alan.etiket}: https adresi olmalı (${metin})`)
    }
    if (alan.tip === 'saniye') {
      const sayi = Number(metin)
      if (!Number.isFinite(sayi) || sayi <= 0) hatalar.push(`${alan.etiket}: pozitif saniye olmalı (${metin})`)
    }
    if (alan.tip === 'metin' && metin.length > 64) {
      hatalar.push(`${alan.etiket}: çok uzun (${metin.length} > 64)`)
    }
  }
  const bitis = alanDegeri(ham, yayinAlanlari.find((a) => a.ad === 'end')!)
  const bas = alanDegeri(ham, yayinAlanlari.find((a) => a.ad === 'start')!)
  if (bas && bitis) {
    const b = Date.parse(String(bas))
    const s = Date.parse(String(bitis))
    if (Number.isFinite(b) && Number.isFinite(s) && s <= b) {
      hatalar.push('Bitiş, başlangıçtan sonra olmalı')
    }
  }
  return hatalar
}

/** Kapsamı kayda yazar; boş alanları SİLER (veri dosyası temiz kalsın). */
export function kapsamiYaz(kayit: YayinDto, kapsam: YayinKapsamiDto): YayinDto {
  const kopya: YayinDto = { ...kayit }
  for (const alan of ['cihazId', 'bolgeId', 'ilceId'] as const) {
    const deger = String(kapsam[alan] ?? '').trim()
    if (deger) kopya[alan] = deger
    else delete kopya[alan]
  }
  return kopya
}

// ---------------------------------------------------------------- yayın görseli (contentUrl)
/**
 * CİHAZIN GÖRSEL KURALLARI (tek kaynak: `kiosk/security/network.py` + `kiosk/security/image_policy.py`).
 *
 * Cihaz adresi indirirken şunları dayatır: https, kullanıcı bilgisi yok, port 443, herkese açık host,
 * içerik türü `image/png|jpeg|webp`. UZANTIYA BAKMAZ — uzantısız bir adres (ör. /api/gorsel?id=3)
 * içerik türü doğruysa gösterilir. Panel bu yüzden:
 *   · kimlik bilgisi, 443 dışı port ve **özel/loopback/link-local host**u REDDEDER
 *     (cihaz da reddeder → "kaydettim ama çıkmıyor"; 26 Ekim i5 bulgusu: host denetimi eksikti),
 *   · uzantısız adresi KABUL eder (cihaz kabul ediyor; panel reddederse doğru adres engellenir),
 *   · bilinen yanlış biçimleri (.svg/.gif/.pdf/.html) erkenden REDDEDER (cihaz içerik türünden reddeder).
 *
 * Hata metinleri adresi GERİ BASTIRMAZ: operatör adrese kimlik bilgisi gömmüşse
 * (…://kullanici:parola@…) mesaj ekranda/ekran görüntüsünde o parolayı yayınlamamalı.
 *
 * Alan sırası (cihaz tüketicileri): Qt `contentUrl → contentURL`; tarayıcı modu
 * `contentUrl → contentURL → url` (`web/src/veri/yayin.ts` ADRES_ALANLARI). `gorsel` HİÇ okunmaz.
 */
/**
 * Özel/loopback/link-local host denetimi (26 Ekim i5 bulgusu: panelde geçen adres cihazda
 * sessizce reddediliyordu). Panel DNS ÇÖZEMEZ (tarayıcı), bu yüzden yalnız **literal** adresler ve
 * açıkça yerel adlar reddedilir: localhost, *.local, *.internal, nokta içermeyen ad, 127/8, 10/8,
 * 172.16/12, 192.168/16, 169.254/16, 0/8, 224/4 ve IPv6 ::1 / fc00::/7 / fe80::/10.
 */
const YEREL_AD = /^(localhost|\.local|.*\.local|.*\.internal|.*\.localhost)$/i

function ozelHostMu(host: string): boolean {
  // Cihaz tarafı `hostname.rstrip('.').lower()` uygular (`kiosk/security/network.py`); panel
  // aynı normalleştirmeyi yapmazsa `https://localhost./a.png` panelde GEÇER, cihazda REDDEDİLİR
  // (26 Ekim i3 bulgusu: sondaki noktada host paritesi açıktı).
  const h = host.trim().toLowerCase().replace(/^\[|\]$/g, '').replace(/\.+$/, '')
  if (!h) return true
  // IPv6 literal ÖNCE: "2a00:1450::1" nokta içermez; nokta kuralı onu yanlışlıkla yerel sayardı.
  if (h.includes(':')) {
    if (h === '::1' || h === '::' || /^f[cd]/.test(h) || /^fe[89ab]/.test(h)) return true
    // IPv4-mapped IPv6 (::ffff:127.0.0.1): gömülü IPv4 aynı kurallardan geçmeli, yoksa panel
    // loopback'i geçirir (26 Ekim i5 bilgi bulgusu). WHATWG URL host'u hex biçime çevirebilir
    // (::ffff:127.0.0.1 → ::ffff:7f00:1), bu yüzden iki biçim de çözülür.
    const eslenik = /^::ffff:(.+)$/.exec(h)
    if (eslenik) {
      const kalan = eslenik[1]
      if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(kalan)) return ozelIpv4Mu(kalan)
      const hex = /^([0-9a-f]{1,4}):([0-9a-f]{1,4})$/.exec(kalan)
      if (hex) {
        const ust = parseInt(hex[1], 16)
        const alt = parseInt(hex[2], 16)
        return ozelIpv4Mu(`${ust >> 8}.${ust & 255}.${alt >> 8}.${alt & 255}`)
      }
      return true // tanınmayan eşlenik biçim → güvenli taraf
    }
    return false
  }
  if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(h)) return ozelIpv4Mu(h)
  return !h.includes('.') || YEREL_AD.test(h)
}

/**
 * IPv4 ayrılmış/özel aralık denetimi — Python `ipaddress.is_global` ile aynı sonucu verir
 * (cihaz `_host_herkese_acik` bunu kullanır). Ayrılmış aralıklar (192.0.0/24, 198.18/15,
 * 198.51.100/24, 203.0.113/24, 100.64/10) da yerel sayılır: panel geçirirse cihaz reddeder.
 */
function ozelIpv4Mu(adres: string): boolean {
  const p = adres.split('.').map(Number)
  if (p.length !== 4 || p.some((x) => !Number.isInteger(x) || x < 0 || x > 255)) return true
  const [a, b, c] = p
  if (a === 0 || a === 10 || a === 127 || a >= 224) return true
  if (a === 100 && b >= 64 && b <= 127) return true
  if (a === 169 && b === 254) return true
  if (a === 172 && b >= 16 && b <= 31) return true
  if (a === 192 && b === 168) return true
  if (a === 192 && b === 0 && (c === 0 || c === 2)) return true
  if (a === 198 && (b === 18 || b === 19)) return true
  if (a === 198 && b === 51 && c === 100) return true
  if (a === 203 && b === 0 && c === 113) return true
  return false
}

/** Görsel adresi üst sınırı (kiosk tarafındaki ağ sınırlarıyla uyumlu, bol pay bırakır). */
export const GORSEL_URL_AZAMI = 512

/** Görsel adresini doğrular. Boş liste = geçerli. */
export function gorselUrlHatalari(url: string, izinliPortlar: readonly number[] = [443]): string[] {
  const metin = String(url ?? '').trim()
  if (!metin) return ['Görsel adresi: boş olamaz']
  if (metin.length > GORSEL_URL_AZAMI) {
    return [`Görsel adresi: çok uzun (${metin.length} > ${GORSEL_URL_AZAMI})`]
  }
  // Yalnız https: kiosk indirmeleri https ile yapılır; javascript:/data:/file: sessizce ölür.
  if (!HTTPS.test(metin)) return ['Görsel adresi: https ile başlamalı']
  let ayrisan: URL
  try {
    ayrisan = new URL(metin)
  } catch {
    return ['Görsel adresi: geçersiz adres']
  }
  if (ayrisan.username || ayrisan.password) {
    return ['Görsel adresi: kullanıcı adı/parola içeremez (cihaz bu adresi reddeder)']
  }
  if (ozelHostMu(ayrisan.hostname)) {
    return ['Görsel adresi: herkese açık bir adres olmalı (yerel/özel ağ adreslerini cihaz reddeder)']
  }
  const port = ayrisan.port ? Number(ayrisan.port) : 443
  if (!izinliPortlar.includes(port)) {
    return [`Görsel adresi: izin verilmeyen port (${port}) — yalnız ${izinliPortlar.join(', ')}`]
  }
  const uzanti = /\.([a-z0-9]{1,5})$/i.exec(ayrisan.pathname)
  if (uzanti && !['png', 'jpg', 'jpeg', 'webp'].includes(uzanti[1].toLowerCase())) {
    // Uzantı VARSA desteklenen listeden olmalı (.svg/.gif/.pdf/.exe… erkenden reddedilir).
    // Uzantı YOKSA kural yok: cihaz `image/png|jpeg|webp` içerik türüne bakar.
    return ['Görsel adresi: .svg/.gif/.pdf gibi biçimleri cihaz göstermez (png/jpeg/webp)']
  }
  return []
}

/**
 * Görsel adresini kayda yazar ve eski ALIAS'ları temizler.
 *
 * NEDEN TEMİZLEME: cihazın Qt gösterim yolu `contentUrl ?? contentURL` okur (data_handler.py:80,
 * tarayici.py:705, pharmacy_app.py:819 — üçü de aynı sıra); `gorsel` alanını cihaz HİÇ okumaz
 * (model.py:46'daki alias listesi yalnız eski kayıtları normalleştirmek içindir). Tarayıcı modu
 * ise `contentUrl → contentURL → url` sırasını izler (`web/src/veri/yayin.ts` ADRES_ALANLARI),
 * yani `url` ÜÇÜNCÜ yedek olarak okunur — "cihaz url alanını hiç okumaz" YANLIŞTIR (26 Ekim i3
 * bulgusu; `model.gorsel.test.ts` bu iddiayı tüketici listesine karşı kilitler).
 * Alias silinmezse eski adres veride kalır ve iki alan çeliştiğinde hangisinin kazandığı anlaşılmaz.
 */
export function gorselUrlYaz(kayit: YayinDto, url: string): YayinDto {
  const kopya: YayinDto = { ...kayit }
  kopya.contentUrl = String(url ?? '').trim()
  delete kopya.contentURL
  delete kopya.url
  delete (kopya as Record<string, unknown>)['gorsel']
  return kopya
}
