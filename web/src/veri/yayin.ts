/**
 * YAYINLAR (tarayıcı) — Qt `core/broadcast_manager.py` + `data_handler.py` ile aynı kurallar.
 *
 * Veri: `lastSystemData.json` → `Yayinlar` = { "<sayısalAnahtar>": { start, end, contentUrl, duration } }
 *
 * · Görünürlük yayının KENDİ penceresine göre:  start ≤ şimdi < end
 * · Anahtarlar sayısal sırayla gezilir (1, 2, 10 …)
 * · `duration` saniyedir; `YAYIN_SURE_EN_AZ_S` … `YAYIN_SURE_EN_COK_S` aralığına kıstırılır,
 *   okunamıyorsa `YAYIN_SURE_VARSAYILAN_S` kullanılır
 */
import { tarihCoz, type SistemVerisi } from './nobet'
import type { Ayarlar } from './ayarlar'

export interface YayinKaydi {
  start?: string
  end?: string
  contentUrl?: string
  contentURL?: string
  url?: string
  duration?: string | number
  [k: string]: unknown
}

const ADRES_ALANLARI = ['contentUrl', 'contentURL', 'url'] as const

/**
 * HEDEFLEME (kapsam) — Qt `core/yayin_kapsam.py` ile BİREBİR aynı kurallar.
 *
 * Alanlar isteğe bağlıdır; boş/yok = kısıt yok (mevcut veri böyle çalışır).
 * Hepsi doluysa üçü de eşleşmeli. Eşleşmeyen cihaz yayını hiç görmez/indirmez.
 */
export interface YayinKapsami {
  ilceId?: string
  bolgeId?: string
  cihazId?: string
}

const KAPSAM_ALANLARI = {
  ilceId: ['ilceId', 'ilce_id', 'ilce'],
  bolgeId: ['bolgeId', 'bolge_id', 'bolge'],
  cihazId: ['cihazId', 'cihaz_id', 'clientID', 'clientId'],
} as const

/** Yayın kaydındaki kapsam alanlarını normalize eder (boş = kısıt yok). */
export function yayinKapsami(yayin: YayinKaydi | null | undefined): Required<YayinKapsami> {
  const sonuc = { ilceId: '', bolgeId: '', cihazId: '' }
  if (!yayin || typeof yayin !== 'object') return sonuc
  for (const [anahtar, adlar] of Object.entries(KAPSAM_ALANLARI)) {
    for (const ad of adlar) {
      const deger = String((yayin as Record<string, unknown>)[ad] ?? '').trim()
      if (deger) {
        sonuc[anahtar as keyof YayinKapsami] = deger
        break
      }
    }
  }
  return sonuc
}

/** Yayın bu cihaz için geçerli mi? (boş kapsam = tüm cihazlar) */
export function kapsamUygun(
  yayin: YayinKaydi | null | undefined,
  cihaz: YayinKapsami = {},
): boolean {
  const kapsam = yayinKapsami(yayin)
  const ilce = String(cihaz.ilceId ?? '').trim()
  const bolge = String(cihaz.bolgeId ?? '').trim()
  const kimlik = String(cihaz.cihazId ?? '').trim()
  if (kapsam.ilceId && kapsam.ilceId !== ilce) return false
  if (kapsam.bolgeId && kapsam.bolgeId !== bolge) return false
  if (kapsam.cihazId && kapsam.cihazId !== kimlik) return false
  return true
}

/** Yayının pencere sınırları (okunamayan alan için null). */
export function yayinPenceresi(yayin: YayinKaydi | null | undefined): { bas: Date | null; bit: Date | null } {
  if (!yayin || typeof yayin !== 'object') return { bas: null, bit: null }
  return { bas: tarihCoz(yayin.start), bit: tarihCoz(yayin.end) }
}

/** Görsel adresi (yoksa ""). */
export function yayinAdresi(yayin: YayinKaydi | null | undefined): string {
  if (!yayin || typeof yayin !== 'object') return ''
  for (const alan of ADRES_ALANLARI) {
    const deger = yayin[alan]
    if (typeof deger === 'string' && deger.trim()) return deger.trim()
  }
  return ''
}

/**
 * Yayın şu an gösterilmeli mi?
 *
 * Penceresi okunamayan yayın **gösterilmez** (yayın görseli için yanlış içerik riski
 * almaktansa atlanır; nöbet kaydındaki "penceresi yoksa göster" kuralından farklıdır).
 */
export function yayinAktifMi(yayin: YayinKaydi, an: Date): boolean {
  const { bas, bit } = yayinPenceresi(yayin)
  if (!bas || !bit) return false
  return bas.getTime() <= an.getTime() && an.getTime() < bit.getTime()
}

/** `Yayinlar` sözlüğünü **Qt ile aynı** sıraya dizer.
 *
 * Qt: `sorted(keys, key=lambda x: int(x) if x.isdigit() else -1)` — sayısal olmayan
 * anahtarlar -1 alır, yani **başa** gelir; sayısal anahtarlar artan sırada.
 */
export function yayinSirasi(veri: SistemVerisi | null | undefined): YayinKaydi[] {
  const yayinlar = veri?.Yayinlar
  if (!yayinlar || typeof yayinlar !== 'object' || Array.isArray(yayinlar)) return []
  const kayitlar = yayinlar as Record<string, YayinKaydi>
  const anahtarlar = Object.keys(kayitlar).sort((a, b) => {
    const sa = /^\d+$/.test(a) ? Number(a) : -1
    const sb = /^\d+$/.test(b) ? Number(b) : -1
    return sa === sb ? a.localeCompare(b, 'tr') : sa - sb
  })
  return anahtarlar
    .map((anahtar) => kayitlar[anahtar])
    .filter((kayit): kayit is YayinKaydi => Boolean(kayit) && typeof kayit === 'object')
}

/** Şu an gösterilecek yayınlar (sıralı, en fazla `enBuyuk` adet). */
export function aktifYayinlar(
  veri: SistemVerisi | null | undefined,
  an: Date = new Date(),
  enBuyuk = 20,
  cihaz: YayinKapsami = {},
): YayinKaydi[] {
  return yayinSirasi(veri)
    .filter((yayin) => kapsamUygun(yayin, cihaz))
    .filter((yayin) => yayinAktifMi(yayin, an))
    .slice(0, Math.max(0, enBuyuk))
}

/** Yayın süresi (ms) — ayarlardaki sınırlara kıstırılır. */
export function yayinSuresiMs(yayin: YayinKaydi | null | undefined, ayarlar?: Ayarlar): number {
  const enAz = ayarlar?.sayi('veri', 'yayin_sure_en_az_s', 1) ?? 1
  const enCok = ayarlar?.sayi('veri', 'yayin_sure_en_cok_s', 60) ?? 60
  const varsayilan = ayarlar?.sayi('veri', 'yayin_sure_varsayilan_s', 10) ?? 10
  const ham = Number(yayin?.duration)
  const saniye = Number.isFinite(ham) && ham > 0 ? Math.min(Math.max(ham, enAz), enCok) : varsayilan
  return Math.round(saniye * 1000)
}
