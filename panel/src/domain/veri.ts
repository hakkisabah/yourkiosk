/**
 * NÖBET VERİSİ — kiosk ile aynı kurallar (`kiosk/core/sync.py`).
 *
 * Kural (sabit saat YOK): kayıt **kendi** penceresine göre gösterilir
 *   start ≤ şimdi < end   (yarı açık aralık → kayıt kendi bitiş anında devreder)
 * Blok seçimi: birleşim penceresi (en erken başlangıç → en geç bitiş) şu anı kapsayan gün;
 * yoksa en son biten gün (yanlış güne atlanmaz). Panel bu kuralları "Durum"
 * ekranında gösterir; cihazın ekranda ne tuttuğu ile birebir aynı olur.
 */

export interface NobetKaydi {
  eczane?: string
  tel?: string
  adres?: string
  adres_tarifi?: string
  bolge?: string
  ilce?: string
  bolgeId?: string
  ilceId?: string
  start?: string
  end?: string
  [k: string]: unknown
}

export interface YayinKaydi {
  [k: string]: unknown
}

export interface SistemVerisi {
  Nobetler?: Record<string, unknown>
  Yayinlar?: Record<string, unknown>
  BolgeIdleri?: unknown
  Cihazlar?: unknown
  lastupdate?: unknown
  _gecici_test?: boolean
  [k: string]: unknown
}

/** "14/10/2026 08:30" veya "2026-10-14T08:30:00" → Date (yerel saat; Python ile aynı). */
export function tarihCoz(deger: unknown): Date | null {
  if (deger instanceof Date) return Number.isNaN(deger.getTime()) ? null : deger
  if (typeof deger !== 'string' || !deger.trim()) return null
  const metin = deger.trim()
  const noktali = metin.match(/^(\d{1,2})[/.](\d{1,2})[/.](\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$/)
  if (noktali) {
    const [, g, a, y, sa = '0', dk = '0', sn = '0'] = noktali
    return new Date(Number(y), Number(a) - 1, Number(g), Number(sa), Number(dk), Number(sn))
  }
  const iso = metin.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/)
  if (iso) {
    const [, y, a, g, sa = '0', dk = '0', sn = '0'] = iso
    return new Date(Number(y), Number(a) - 1, Number(g), Number(sa), Number(dk), Number(sn))
  }
  const genel = new Date(metin)
  return Number.isNaN(genel.getTime()) ? null : genel
}

const _kayit_mi = (d: unknown): d is NobetKaydi => !!d && typeof d === 'object' && !Array.isArray(d)

/** Ağaçtaki tüm nöbet kayıtlarını dolaşır: Nobetler → gün → ilceId → [ {bolgeId:[kayıt]} ] */
export function tumKayitlar(veri: SistemVerisi | null | undefined): NobetKaydi[] {
  const kayitlar: NobetKaydi[] = []
  const nobetler = veri?.Nobetler
  if (!nobetler || typeof nobetler !== 'object') return kayitlar
  for (const blok of Object.values(nobetler as Record<string, unknown>)) {
    if (!blok || typeof blok !== 'object') continue
    for (const [ilceId, ilceListesi] of Object.entries(blok as Record<string, unknown>)) {
      if (!Array.isArray(ilceListesi)) continue
      for (const kutu of ilceListesi) {
        if (!kutu || typeof kutu !== 'object') continue
        for (const [bolgeId, liste] of Object.entries(kutu as Record<string, unknown>)) {
          if (!Array.isArray(liste)) continue
          for (const kayit of liste) {
            if (!_kayit_mi(kayit)) continue
            // Ağaç anahtarları kaydın İÇİNDE yoksa ekle: hedefleme (ilçe/bölge) ve ad indeksi
            // bu alanlara dayanır. Kayıt kendi kimliğini taşıyorsa DOKUNMA.
            if (!kayit.ilceId) kayit.ilceId = ilceId
            if (!kayit.bolgeId) kayit.bolgeId = bolgeId
            kayitlar.push(kayit)
          }
        }
      }
    }
  }
  return kayitlar
}

export const gunBloklari = (veri: SistemVerisi | null | undefined): Record<string, unknown> => {
  const nobetler = veri?.Nobetler
  return nobetler && typeof nobetler === 'object' ? (nobetler as Record<string, unknown>) : {}
}

export interface GunPenceresi {
  anahtar: string
  bas: Date | null
  bit: Date | null
}

/** Her gün bloğunun BİRLEŞİM penceresi (kısa nöbet bloğu temsil etmez). */
export function gunPencereleri(veri: SistemVerisi | null | undefined): GunPenceresi[] {
  const bloklar = gunBloklari(veri)
  return Object.keys(bloklar)
    .sort()
    .map((anahtar) => {
      const kayitlar = _blok_kayitlari(bloklar[anahtar])
      const baslar = kayitlar.map((k) => tarihCoz(k.start)).filter((d): d is Date => !!d)
      const bitler = kayitlar.map((k) => tarihCoz(k.end)).filter((d): d is Date => !!d)
      return {
        anahtar,
        bas: baslar.length ? new Date(Math.min(...baslar.map((d) => d.getTime()))) : null,
        bit: bitler.length ? new Date(Math.max(...bitler.map((d) => d.getTime()))) : null,
      }
    })
}

/** Bir gün bloğundaki tüm kayıtlar (ilçe/bölge ayrımı yapmadan). */
function _blok_kayitlari(blok: unknown): NobetKaydi[] {
  const kayitlar: NobetKaydi[] = []
  if (!blok || typeof blok !== 'object') return kayitlar
  for (const ilceListesi of Object.values(blok as Record<string, unknown>)) {
    if (!Array.isArray(ilceListesi)) continue
    for (const kutu of ilceListesi) {
      if (!kutu || typeof kutu !== 'object') continue
      for (const liste of Object.values(kutu as Record<string, unknown>)) {
        if (!Array.isArray(liste)) continue
        for (const kayit of liste) if (_kayit_mi(kayit)) kayitlar.push(kayit)
      }
    }
  }
  return kayitlar
}

/** Gösterilecek gün bloğunu seçer — `sync.gun_sec` ile aynı kurallar. */
export function gunSec(veri: SistemVerisi | null | undefined, an: Date = new Date()): { anahtar: string; blok: unknown; kaynak: string } {
  const bloklar = gunBloklari(veri)
  const pencereler = gunPencereleri(veri)
  if (!pencereler.length) return { anahtar: '', blok: undefined, kaynak: 'veri yok' }

  for (const p of pencereler) {
    if (p.bas && p.bit && p.bas <= an && an < p.bit) return { anahtar: p.anahtar, blok: bloklar[p.anahtar], kaynak: 'aktif pencere' }
  }
  const gecmis = pencereler.filter((p) => p.bit && p.bit <= an)
  if (gecmis.length) {
    const secili = gecmis.reduce((a, b) => (a.bit! > b.bit! ? a : b))
    return { anahtar: secili.anahtar, blok: bloklar[secili.anahtar], kaynak: 'en son biten (veri tazelenmeli)' }
  }
  const gelecek = pencereler.filter((p) => p.bas && p.bas > an)
  const secili = gelecek.length ? gelecek.reduce((a, b) => (a.bas! < b.bas! ? a : b)) : pencereler[pencereler.length - 1]
  return { anahtar: secili.anahtar, blok: bloklar[secili.anahtar], kaynak: 'henüz başlamamış' }
}

/** Kaydın KENDİ penceresi şu anı kapsıyor mu? (penceresi okunamayan kayıt gösterilir) */
export function kayitAktifMi(kayit: NobetKaydi, an: Date): boolean {
  const bas = tarihCoz(kayit.start)
  const bit = tarihCoz(kayit.end)
  if (!bas || !bit) return true
  return bas <= an && an < bit
}

/** Bitmiş/başlamamış kayıtları düşer; hiç kalmazsa tümünü döner (ekran boş kalmasın). */
export function aktifKayitlar(kayitlar: NobetKaydi[], an: Date): NobetKaydi[] {
  const aktif = kayitlar.filter((k) => kayitAktifMi(k, an))
  return aktif.length ? aktif : kayitlar
}

export interface CihazKonumu {
  ilceId?: string
  bolgeId?: string
  ilce?: string
  bolge?: string
  bulundu?: boolean
  [k: string]: unknown
}

/** Cihazın ilçe/bölgesine göre kayıtları süzer (`sync.ilce_bolge_filtrele` ile aynı). */
export function ilceBolgeFiltrele(blok: unknown, konum: CihazKonumu, kapsam = 'ilce'): NobetKaydi[] {
  const kayitlar = _blok_kayitlari(blok)
  if (!konum || (!konum.ilceId && !konum.bolgeId)) return kayitlar
  if (kapsam === 'bolge' && konum.bolgeId) {
    return kayitlar.filter((k) => String(k.bolgeId ?? '') === String(konum.bolgeId))
  }
  if (konum.ilceId) {
    const ilce = kayitlar.filter((k) => String(k.ilceId ?? '') === String(konum.ilceId))
    if (ilce.length) return ilce
  }
  return kayitlar.filter((k) => String(k.bolgeId ?? '') === String(konum.bolgeId))
}

/** Cihazın göstereceği kayıtlar + gün (panelde "cihaz neyi gösteriyor" için). */
export function gosterilecekKayitlar(
  veri: SistemVerisi | null | undefined,
  konum: CihazKonumu,
  an: Date = new Date(),
  kapsam = 'ilce',
): { anahtar: string; kayitlar: NobetKaydi[]; kaynak: string } {
  const { anahtar, blok, kaynak } = gunSec(veri, an)
  if (!anahtar) return { anahtar, kayitlar: [], kaynak }
  const suzulmus = ilceBolgeFiltrele(blok, konum, kapsam)
  return { anahtar, kayitlar: aktifKayitlar(suzulmus, an), kaynak }
}

/** Cihazın ilçe/bölge adlarını match.json + veriden bulur (`sync.konum_adlarini_bul`). */
export function konumAdlariniBul(veri: SistemVerisi | null | undefined, konum: CihazKonumu): CihazKonumu {
  const kayitlar = tumKayitlar(veri)
  const ilceId = String(konum.ilceId ?? '')
  const bolgeId = String(konum.bolgeId ?? '')
  const ilceKaydi = kayitlar.find((k) => String(k.ilceId ?? '') === ilceId)
  const bolgeKaydi = kayitlar.find((k) => String(k.bolgeId ?? '') === bolgeId)
  return {
    ...konum,
    ilce: ilceKaydi?.ilce ?? konum.ilce ?? '',
    bolge: bolgeKaydi?.bolge ?? konum.bolge ?? '',
    bulundu: Boolean(ilceKaydi || bolgeKaydi) || Boolean(konum.bulundu),
  }
}

export interface VeriOzeti {
  gunSayisi: number
  kayitSayisi: number
  ilceSayisi: number
  bolgeSayisi: number
  ilkGun: string
  sonGun: string
  yayinSayisi: number
  geciciMi: boolean
}

export function ozetle(veri: SistemVerisi | null | undefined): VeriOzeti {
  const gunler = Object.keys(gunBloklari(veri)).sort()
  const kayitlar = tumKayitlar(veri)
  const yayinlar = veri?.Yayinlar && typeof veri.Yayinlar === 'object' ? (veri.Yayinlar as Record<string, unknown>) : {}
  const ilceler = new Set<string>()
  const bolgeler = new Set<string>()
  for (const k of kayitlar) {
    if (k.ilceId) ilceler.add(String(k.ilceId))
    if (k.bolgeId) bolgeler.add(String(k.bolgeId))
  }
  const say = (x: unknown): number => (Array.isArray(x) ? x.length : 1)
  const yayinSayisi = Object.values(yayinlar).reduce((t: number, v) => t + say(v), 0)
  return {
    gunSayisi: gunler.length,
    kayitSayisi: kayitlar.length,
    ilceSayisi: ilceler.size,
    bolgeSayisi: bolgeler.size,
    ilkGun: gunler[0] ?? '',
    sonGun: gunler[gunler.length - 1] ?? '',
    yayinSayisi,
    geciciMi: Boolean(veri?._gecici_test),
  }
}

/** "T20261015" → "15.10.2026" (panelde okunur gün etiketi). */
export function gunEtiketi(anahtar: string): string {
  const m = anahtar.match(/^T(\d{4})(\d{2})(\d{2})$/)
  return m ? `${m[3]}.${m[2]}.${m[1]}` : anahtar
}

/** Tarihi kiosk ile aynı biçimde yazar: "15.10.26 08:30:00". */
export function tarihMetni(deger: unknown): string {
  const d = tarihCoz(deger)
  if (!d) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${String(d.getFullYear()).slice(2)} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
