/**
 * KAYAN YAZI KUŞAĞI (tarayıcı) — Qt `core/ticker.py` + `pharmacy_app.py` ile aynı kurallar.
 *
 * Metin: her kayıt için `"{ECZANE} - {telefon|bölge}"`; `KUSAK_TEKLI` açıkken kayıtlar
 * TEK TEK ortaya girip bekleyip sola çıkar (giriş/durma/çıkış), kapalıyken tüm liste
 * tek metin olarak sağdan sola sürekli akar.
 *
 * Konum formülü (Qt ile birebir):
 *     x = round(şerit_genişlik − oran × (şerit_genişlik + yazı_genişlik))
 *     oran 0.0 → tamamen sağda (görünmez) · 0.5 → şeridin ORTASI · 1.0 → tamamen solda
 */

/** Qt `utils.format_phone`: rakam dışını at, 10 hane ise başına 0 ekle, 11 haneyi grupla. */
export function formatTelefon(tel: unknown): string {
  const ham = typeof tel === 'string' ? tel : tel === null || tel === undefined ? '' : String(tel)
  const rakamlar = ham.replace(/\D/g, '')
  if (!rakamlar) return ham.trim() || '-'
  let hane = rakamlar
  if (hane.length === 10 && !hane.startsWith('0')) hane = `0${hane}`
  if (hane.length === 11) {
    return `${hane.slice(0, 4)} ${hane.slice(4, 7)} ${hane.slice(7, 9)} ${hane.slice(9, 11)}`
  }
  return ham.trim() || '-'
}

export interface KusakSecenekleri {
  /** telefon yoksa bölge adı yazılsın mı (Qt: EKSIK_TELEFON_YERINE_BOLGE) */
  eksikTelefonYerineBolge?: boolean
}

/** Kaydın ikincil metni (telefon; yoksa bölge adı; o da yoksa "-"). */
export function ikincilMetin(kayit: Record<string, unknown> | null | undefined, secenek: KusakSecenekleri = {}): string {
  const eksikYerineBolge = secenek.eksikTelefonYerineBolge ?? true
  const telefon = formatTelefon(kayit?.tel)
  if (telefon && telefon !== '-') return telefon
  if (eksikYerineBolge) {
    const bolge = String(kayit?.bolge ?? '').trim()
    if (bolge) return bolge
  }
  return '-'
}

/** Kuşak öğeleri: `["ECZANE - TELEFON", ...]` (kayıt yoksa `["-"]`). */
export function kusakOgeleri(
  kayitlar: Array<Record<string, unknown>>,
  secenek: KusakSecenekleri = {},
): string[] {
  const ogeler = kayitlar.map((kayit) => `${String(kayit.eczane ?? '').toUpperCase()} - ${ikincilMetin(kayit, secenek)}`)
  return ogeler.length ? ogeler : ['-']
}

/** Tek metin modunda birleştirme (Qt: 8 boşluk + ayırıcı + 8 boşluk). */
export function kusakMetni(ogeler: string[], tekli: boolean, ayirici: string): string {
  if (tekli) return ogeler[0] ?? '-'
  return `        ${ogeler.join(ayirici)}        `
}

/** Qt `in_out_cubic` ile aynı easing. */
export function inOutCubic(t: number): number {
  const x = Math.min(1, Math.max(0, t))
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2
}

/** Kuşak konumu (px): `x = şerit − oran×(şerit + yazı)`. */
export function kusakX(seritGenislik: number, yaziGenislik: number, oran: number): number {
  return Math.round(seritGenislik - oran * (seritGenislik + yaziGenislik))
}

/**
 * Tekli modun faz makinesi — Qt `KusakAnimasyonu` ile aynı adım aritmetiği.
 *
 * 30 ms'lik tik ile sürülür; her tikte `adim()` çağrılır, `oran()` konumu verir,
 * `donguTamamlandi` true olduğunda çağıran bir sonraki kayda geçer.
 */
export class KusakAnimasyonu {
  private adimSayaci = 0
  private tamamlandi = false
  private readonly girisAdim: number
  private readonly durmaAdim: number
  private readonly cikisAdim: number

  constructor(
    private readonly girisMs = 1200,
    private readonly durmaMs = 3000,
    private readonly cikisMs = 1200,
    adimMs = 30,
  ) {
    const adim = Math.max(1, adimMs)
    this.girisAdim = Math.max(1, Math.round(this.girisMs / adim))
    this.durmaAdim = Math.max(0, Math.round(this.durmaMs / adim))
    this.cikisAdim = Math.max(1, Math.round(this.cikisMs / adim))
  }

  get toplamAdim(): number {
    return this.girisAdim + this.durmaAdim + this.cikisAdim
  }

  /** Bir tik ilerletir; döngü tamamlandıysa true döner (Qt: `dongu_tamamlandi`). */
  adim(): boolean {
    this.adimSayaci = (this.adimSayaci + 1) % this.toplamAdim
    this.tamamlandi = this.adimSayaci === 0
    return this.tamamlandi
  }

  /** Şu anki oran (0 = sağda, 0.5 = ortada, 1 = solda). */
  oran(): number {
    const i = this.adimSayaci
    if (i < this.girisAdim) {
      // giriş: 0 → 0.5
      return inOutCubic(i / this.girisAdim) * 0.5
    }
    if (i < this.girisAdim + this.durmaAdim) {
      return 0.5 // ortada bekle
    }
    const j = i - this.girisAdim - this.durmaAdim
    // çıkış: 0.5 → 1.0
    return 0.5 + inOutCubic(j / this.cikisAdim) * 0.5
  }

  get donguTamamlandi(): boolean {
    return this.tamamlandi
  }

  sifirla(): void {
    this.adimSayaci = 0
    this.tamamlandi = false
  }
}
