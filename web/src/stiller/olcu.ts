/**
 * ÖLÇÜ KAYNAĞI — `yerlesim.json` (kiosk/tools/web_disa_aktar.py ÜRETİR).
 *
 * Tüm görsel değerler (ölçü, punto, renk) Qt kodundan üretilir; burada yalnızca tip
 * tanımı ve CSS değişkenlerine aktarım vardır. Elle yazılan ölçü YOKTUR; Qt tarafı
 * değişirse `yerlesim.json` yenilenir ve test bunu zorunlu kılar.
 */
import ham from '@/veri/yerlesim.json'

export interface Yerlesim {
  ekran: { genislik: number; yukseklik: number; scale_formulu: string }
  olculer: {
    satir_yuksekligi: number
    sol_panel_genislik: number
    sag_panel_genislik: number
    viewport_yukseklik: number
    sol_gorunur_yukseklik: number
    logo_genislik: number
    saat_kutusu_genislik: number
    kusak_y: number
  }
  elle: Record<string, number | string>
  renkler: Record<string, string>
}

export interface Sabitler {
  [ad: string]: string | number | boolean | null
}

export interface Varsayilanlar {
  [grup: string]: Record<string, unknown>
}

export const yerlesim = ham.yerlesim as unknown as Yerlesim
export const sabitler = ham.sabitler as unknown as Sabitler
export const varsayilanlar = ham.varsayilanlar as unknown as Varsayilanlar

/** Qt config sabiti (yoksa yedek). */
export function sabit<T extends string | number | boolean>(ad: string, yedek: T): T {
  const deger = sabitler[ad]
  return (deger === undefined || deger === null ? yedek : deger) as T
}

/** `elle` tablosundan değer (ör. "sol.punto_ad"). */
export function elle<T extends number | string>(ad: string, yedek: T): T {
  const deger = yerlesim.elle?.[ad]
  return (deger === undefined ? yedek : deger) as T
}

/** Ekran yüksekliğine göre ölçek (Qt: `scale = screen_h / 1080`). */
export function sahneOlcegi(yukseklik: number): number {
  return yukseklik / yerlesim.ekran.yukseklik
}

/**
 * CSS için ölçü değeri: birimsiz sayıya `px` ekler.
 *
 * NEDEN GEREKLİ: `yerlesim.json` değerleri Qt'den **sayı** olarak gelir (1080, 208, 3…).
 * `height: var(--ekran-y)` içine birimsiz `1080` yazılırsa CSS değeri **geçersiz** sayar
 * ("invalid at computed-value time") ve özellik ilk değerine düşer → `height: auto`.
 * Sahnenin çocukları `position: absolute` olduğu için yükseklik **0** olur ve arkadaki
 * siyah `body` görünür: konsolda hata YOK, ekran siyah. Metin de olabilir ('3'), bu yüzden
 * sayısal metin de px'e çevrilir.
 *
 * Eksik/yanlış anahtar (ör. `viewport_yuksekligi` ↔ `viewport_yukseklik`) sessizce siyah
 * ekrana dönüşmesin diye değer yoksa **görünür hata** verilir; güvenlik ağı bunu ekrana
 * kart olarak basar (sessiz boş ekrandan iyidir).
 */
function px(deger: number | string | undefined, anahtar = ''): string {
  if (deger === undefined || deger === null) {
    throw new Error(
      `yerlesim.json'da eksik ölçü: ${anahtar || '(bilinmeyen)'} — web_disa_aktar.py güncel mi?`,
    )
  }
  const metin = String(deger).trim()
  return /^-?\d+(\.\d+)?$/.test(metin) ? `${metin}px` : metin
}

/** Yerleşim + renkleri CSS değişkeni olarak `<html>`e yazar (tek kaynak: yerlesim.json). */
export function cssDegiskenleriniUygula(kok: HTMLElement = document.documentElement): Record<string, string> {
  const o = yerlesim.olculer
  const e = yerlesim.elle
  const r = yerlesim.renkler
  const degiskenler: Record<string, string> = {
    '--ekran-g': px(yerlesim.ekran.genislik, 'ekran.genislik'),
    '--ekran-y': px(yerlesim.ekran.yukseklik, 'ekran.yukseklik'),
    '--sol-genislik': px(o.sol_panel_genislik, 'olculer.sol_panel_genislik'),
    '--sag-genislik': px(o.sag_panel_genislik, 'olculer.sag_panel_genislik'),
    '--satir-yuksekligi': px(o.satir_yuksekligi, 'olculer.satir_yuksekligi'),
    '--viewport-yuksekligi': px(o.viewport_yukseklik, 'olculer.viewport_yukseklik'),
    '--logo-genislik': px(o.logo_genislik, 'olculer.logo_genislik'),
    '--saat-kutusu': px(o.saat_kutusu_genislik, 'olculer.saat_kutusu_genislik'),
    '--kusak-y': px(o.kusak_y, 'olculer.kusak_y'),
    '--dikey-cizgi': px(e['sol.dikey_cizgi'], 'elle.sol.dikey_cizgi'),
    '--satir-bosluk': px(e['sol.satir_bosluk'], 'elle.sol.satir_bosluk'),
    '--sol-ic-bosluk': px(e['sol.ic_bosluk'], 'elle.sol.ic_bosluk'),
    '--punto-sol-ad': px(e['sol.punto_ad'], 'elle.sol.punto_ad'),
    '--punto-sol-ikincil': px(e['sol.punto_ikincil'], 'elle.sol.punto_ikincil'),
    '--serit-yukseklik': px(e['orta.serit_yukseklik'], 'elle.orta.serit_yukseklik'),
    '--tarih-aralik-yuksekligi': px(e['orta.tarih_aralik_yukseklik'], 'elle.orta.tarih_aralik_yukseklik'),
    '--detay-yuksekligi': px(e['orta.detay_yukseklik'], 'elle.orta.detay_yukseklik'),
    '--yatay-cizgi': px(e['orta.yatay_cizgi'], 'elle.orta.yatay_cizgi'),
    '--alt-serit-yuksekligi': px(e['orta.alt_serit_yukseklik'], 'elle.orta.alt_serit_yukseklik'),
    '--punto-tarih-aralik': px(e['orta.punto_tarih_aralik'], 'elle.orta.punto_tarih_aralik'),
    '--punto-orta-ad': px(e['orta.punto_ad'], 'elle.orta.punto_ad'),
    '--punto-adres': px(e['orta.punto_adres'], 'elle.orta.punto_adres'),
    '--punto-telefon': px(e['orta.punto_telefon'], 'elle.orta.punto_telefon'),
    '--punto-saat': px(e['orta.punto_saat'], 'elle.orta.punto_saat'),
    '--kusak-yukseklik': px(sabit('KUSAK_YUKSEKLIK', 110), 'KUSAK_YUKSEKLIK'),
    '--kusak-punto': px(sabit('KUSAK_YAZI_PUNTO', 36), 'KUSAK_YAZI_PUNTO'),
    '--animasyon-ms': px(elle('animasyon.sure_ms', 1800), 'animasyon.sure_ms').replace(/px$/, 'ms'),
    '--kirmizi': String(r.kirmizi),
    '--krem': String(r.krem),
    '--kaydirma-genislik': px(sabit('SOL_PANEL_KAYDIRMA_CUBUGU_GENISLIK', 12), 'kaydirma genişliği'),
    '--kaydirma-ray': String(sabit('SOL_PANEL_KAYDIRMA_CUBUGU_RENK', '#d9dee5')),
    '--kaydirma-tutamak': String(sabit('SOL_PANEL_KAYDIRMA_TUTAMAK_RENK', '#6b7280')),
    '--kutu-normal': `url('/${elle('sol.kutu_normal', 'bg_layout/box.png')}')`,
    '--kutu-aktif': `url('/${elle('sol.kutu_aktif', 'bg_layout/activeBox.png')}')`,
    '--serit-gorseli': `url('/${elle('orta.serit_gorseli', 'bg_layout/kusak.png')}')`,
  }
  for (const [ad, deger] of Object.entries(degiskenler)) {
    kok.style.setProperty(ad, deger)
  }
  return degiskenler
}
