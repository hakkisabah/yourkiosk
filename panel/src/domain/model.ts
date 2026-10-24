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
