/**
 * VERİ KAYNAĞI (tarayıcı) — Qt `core/veri_kaynagi.py` ile aynı dosyalar ve aynı kurallar.
 *
 * · `veri=yerel`  → dosyalar cihazdaki yerel sunucudan (aynı kaynak; `lastSystemData.json` …)
 * · `veri=https`  → veri VE ayarlar `taban` adresinden (ör. https://sunucu/veri); çevrimdışıysa önbellek/yerel
 *
 * Ayarlar (`ayarlar.json`, `kapsam-ayarlari.json`) HER ZAMAN yerel kaynaktan okunur —
 * Qt sürümünde de bu dosyalar cihazın kendi diskinden okunur.
 *
 * Maliyet: `lastupdate.json` (küçük damga dosyası) her turda okunur; damga değişmediyse
 * büyük dosyalar **ağdan çekilmez**, önbellekten gelir (bkz. `onbellek.ts`).
 */
import { Onbellek } from './onbellek'
import type { SistemVerisi } from './nobet'
import { sabit } from '@/stiller/olcu'

export type VeriModu = 'yerel' | 'https'

/** Ayarların son iyi kopyası (bellek + localStorage). Çevrimdışı açılışta kullanılır. */
const AYAR_BELLEK = new Map<string, string>()

/** Testler/diagnostik için: ayar önbelleğini boşalt. */
export function ayarOnbellegiTemizle(): void {
  AYAR_BELLEK.clear()
}

/** Panelin yazdığı tetikleyici (nöbet değişikliği bildirimi). */
export interface TetikBilgisi {
  /** ISO zaman damgası — aynı tetikleyicinin tekrar uygulanmaması için karşılaştırılır. */
  zaman: string
  /** Boş/"*" → tüm cihazlar; dolu ise yalnız o ilçe/bölge cihazları yenilenir. */
  ilceId: string
  bolgeId: string
  aciklama: string
}

/** `/degisiklik` (uzun yoklama) yanıtı. */
export interface DegisiklikBildirimi {
  degisti: boolean
  imza: string
  damga: string
  tetik: TetikBilgisi | null
}

export interface BaslatmaSecenekleri {
  clientID: string
  veri: VeriModu
  /** https modunda veri kök adresi (launcher `DOSYA_ADRESI`'ni buraya yazar) */
  taban: string
  /** yalnızca test/teşhis: ölçek zorlaması (ör. 0.5) */
  yerlesim?: number
}

export const VERI_DOSYALARI = ['lastupdate.json', 'lastSystemData.json', 'match.json', 'sablon.json'] as const
export const AYAR_DOSYALARI = ['ayarlar.json', 'kapsam-ayarlari.json'] as const

/** URL sorgu parametrelerini okur (`?clientID=...&veri=...&taban=...`). */
export function parametreleriOku(arama: string, varsayilanTaban = ''): BaslatmaSecenekleri {
  const parametreler = new URLSearchParams(arama.startsWith('?') ? arama.slice(1) : arama)
  const veri = String(parametreler.get('veri') ?? 'yerel').toLowerCase() === 'https' ? 'https' : 'yerel'
  const yerlesim = parametreler.get('yerlesim')
  const olcek = yerlesim === null ? undefined : Number(yerlesim)
  return {
    clientID: String(parametreler.get('clientID') ?? parametreler.get('clientId') ?? '').trim(),
    veri,
    taban: String(parametreler.get('taban') ?? varsayilanTaban).trim(),
    yerlesim: Number.isFinite(olcek) ? (olcek as number) : undefined,
  }
}

export interface VeriKaynagiSecenekleri {
  secenekler: BaslatmaSecenekleri
  onbellek?: Onbellek
  /** test için: fetch yerine geçen işlev */
  getir?: typeof fetch
  /** yerel kök (varsayılan: sayfanın bulunduğu yer) */
  yerelTaban?: string
}

export class VeriKaynagi {
  private readonly getir: typeof fetch
  private readonly onbellek: Onbellek
  private readonly yerel: string

  constructor(private readonly ayar: VeriKaynagiSecenekleri) {
    this.getir = ayar.getir ?? ((...arg: Parameters<typeof fetch>) => fetch(...arg))
    this.onbellek = ayar.onbellek ?? new Onbellek()
    this.yerel = ayar.yerelTaban ?? ''
  }

  get secenekler(): BaslatmaSecenekleri {
    return this.ayar.secenekler
  }

  /** Büyük veri dosyalarının kökü (yerel modda aynı kaynak). */
  veriTaban(): string {
    if (this.ayar.secenekler.veri !== 'https') return this.yerel
    return this.ayar.secenekler.taban || this.yerel
  }

  private async _metin(adres: string): Promise<ArrayBuffer | null> {
    try {
      const yanit = await this.getir(adres, { cache: 'no-store' })
      if (!yanit.ok) return null
      return await yanit.arrayBuffer()
    } catch {
      return null
    }
  }

  private async _json<T>(adres: string): Promise<T | null> {
    const govde = await this._metin(adres)
    if (!govde) return null
    try {
      return JSON.parse(new TextDecoder().decode(govde)) as T
    } catch {
      return null
    }
  }

    /** Damga dosyası (her turda ağdan; hata olursa önbellekteki son damga). */
  async lastupdate(): Promise<string> {
    const govde = await this._metin(`${this.veriTaban()}/lastupdate.json`)
    if (govde) {
      try {
        const veri = JSON.parse(new TextDecoder().decode(govde)) as Record<string, unknown>
        const damga = String(veri.lastupdate ?? veri.lastUpdate ?? veri.tarih ?? '').trim()
        if (damga) {
          // damgayı sakla: bir sonraki turda ağ erişilemezse bu değer kullanılır
          await this.onbellek.damgaYaz(damga)
          return damga
        }
      } catch {
        /* bozuk damga: önbellekteki değere düşülür */
      }
    }
    return this.onbellek.damga()
  }

  /**
   * Nöbet/yayın verisi — damga aynıysa önbellekten (ağa çıkılmaz).
   *
   * `zorla = true` → **damga aynı olsa da** önbellek atlanır ve taze indirilir. Bu yol,
   * "veri yerelde değişti ama `lastupdate` damgası değişmedi" durumları için şarttır
   * (panel/araç kaynaklı değişiklikler, tetikleyici bildirimi):
   * aksi hâlde arayüz eskİ gövdeyi önbellekten servis etmeye devam eder.
   */
  async sistemVerisi(damga?: string, zorla = false): Promise<SistemVerisi | null> {
    const guncel = damga ?? (await this.lastupdate())
    const ad = 'lastSystemData.json'
    if (zorla) await this.onbellek.veriSil(ad)
    const onbellekten = await this.onbellek.veriOku(ad, guncel)
    if (onbellekten) {
      try {
        return JSON.parse(new TextDecoder().decode(onbellekten)) as SistemVerisi
      } catch {
        /* bozuk kayıt: ağdan yeniden alınır */
      }
    }
    const govde = await this._metin(`${this.veriTaban()}/${ad}`)
    if (!govde) return null
    await this.onbellek.veriYaz(ad, govde, guncel)
    try {
      return JSON.parse(new TextDecoder().decode(govde)) as SistemVerisi
    } catch {
      return null
    }
  }

  /** match.json (cihaz → ilçe/bölge eşlemesi). */
  async match(): Promise<Record<string, unknown> | null> {
    const ad = 'match.json'
    const govde = await this._metin(`${this.veriTaban()}/${ad}`)
    if (!govde) return null
    try {
      return JSON.parse(new TextDecoder().decode(govde)) as Record<string, unknown>
    } catch {
      return null
    }
  }

  /**
   * Ayar belgesi.
   *
   * `veri=https` → **yayınlanmış** ayarlar (`DOSYA_ADRESI`) okunur; panelden yapılan değişiklikler
   * cihaza ulaşır. Uzak okunamazsa (çevrimdışı / 403 / bozuk JSON) sırayla:
   * `localStorage` kopyası → yerel dosya → varsayılan. Böylece cihaz çevrimdışıyken ayarsız kalmaz.
   */
  async ayarBelgesi(ad: string): Promise<Record<string, unknown> | null> {
    if (!(AYAR_DOSYALARI as readonly string[]).includes(ad)) return null
    if (this.ayar.secenekler.veri === 'https') {
      const uzak = await this._json<Record<string, unknown>>(`${this.veriTaban()}/${ad}`)
      if (uzak) {
        this.ayarOnbellekYaz(ad, uzak)
        return uzak
      }
      const yerelKopya = this.ayarOnbellekOku(ad)
      if (yerelKopya) return yerelKopya
    }
    return this._json<Record<string, unknown>>(`${this.yerel}/${ad}`)
  }

  private ayarOnbellekAnahtari(ad: string): string {
    return `yourkiosk:ayar:${ad}`
  }

  private ayarOnbellekYaz(ad: string, belge: Record<string, unknown>): void {
    const metin = JSON.stringify(belge)
    AYAR_BELLEK.set(ad, metin)
    try {
      localStorage.setItem(this.ayarOnbellekAnahtari(ad), metin)
    } catch {
      /* depolama kapalı/dolu: bellek kopyası yine de var */
    }
  }

  private ayarOnbellekOku(ad: string): Record<string, unknown> | null {
    let ham: string | null = AYAR_BELLEK.get(ad) ?? null
    if (!ham) {
      try {
        ham = localStorage.getItem(this.ayarOnbellekAnahtari(ad))
      } catch {
        ham = null
      }
    }
    if (!ham) return null
    try {
      const belge = JSON.parse(ham) as unknown
      return belge && typeof belge === 'object' ? (belge as Record<string, unknown>) : null
    } catch {
      return null
    }
  }

  /**
   * TETİKLEYİCİ (panel → cihaz): nöbet değişikliği yapıldığında panel `tetikle.json` yazar;
   * cihaz bunu görünce **beklemeden** yenilenir. Yalnızca yerel sunucudan okunur (cihaz dosyası).
   */
  async tetikleyici(): Promise<TetikBilgisi | null> {
    const ad = String(sabit('TETIK_DOSYASI', 'tetikle.json')) || 'tetikle.json'
    const belge = await this._json<Record<string, unknown>>(`${this.yerel}/${ad}`)
    if (!belge) return null
    const zaman = String(belge.zaman ?? '').trim()
    if (!zaman) return null
    return {
      zaman,
      ilceId: String(belge.ilceId ?? '').trim(),
      bolgeId: String(belge.bolgeId ?? '').trim(),
      aciklama: String(belge.aciklama ?? '').trim(),
    }
  }

  /**
   * ANLIK DEĞİŞİKLİK BİLDİRİMİ (uzun yoklama): yerel sunucu `lastupdate.json`/`tetikle.json`
   * değişene kadar isteği açık tutar (nabız: `nobetBeklemeS`). Böylece nöbet değişikliği
   * 20 sn'lik yoklamayı beklemeden (tipik <1 sn) ekrana yansır.
   *
   * Uç yoksa (statik sunum) `null` döner → arayüz yalnız damga yoklamasıyla çalışır.
   */
  async degisiklikBekle(
    imza: string,
    sureS: number,
  ): Promise<DegisiklikBildirimi | null> {
    const adres = `${this.yerel}/degisiklik?imza=${encodeURIComponent(imza)}&sure=${encodeURIComponent(String(sureS))}`
    const belge = await this._json<Record<string, unknown>>(adres)
    if (!belge || typeof belge.degisisti !== 'boolean') return null
    const tetik = belge.tetik as Record<string, unknown> | null | undefined
    return {
      degisti: belge.degisisti,
      imza: String(belge.imza ?? ''),
      damga: String(belge.damga ?? ''),
      tetik: tetik && String(tetik.zaman ?? '').trim()
        ? {
            zaman: String(tetik.zaman),
            ilceId: String(tetik.ilceId ?? '').trim(),
            bolgeId: String(tetik.bolgeId ?? '').trim(),
            aciklama: String(tetik.aciklama ?? '').trim(),
          }
        : null,
    }
  }

  /**
   * Yayın görselini alır.
   *
   * ÖNCELİK: **yerel sunucu köprüsü** `/gorsel?u=<url>` — tarayıcı farklı alan adındaki
   * görseli `fetch` ile alamaz (CORS); sunucu indirir, doğrular (izin listesi, bayt/piksel
   * bütçesi, biçim beyaz listesi) ve **cihaz önbelleğine** yazar (Qt ile aynı `onbellek/`).
   * Köprü yoksa/başarısızsa tarayıcı önbelleği → doğrudan indirme sırasına düşülür.
   */
  async gorsel(url: string, damga = ''): Promise<ArrayBuffer | null> {
    if (!url) return null
    const kopru = await this._metin(`${this.yerel}/gorsel?u=${encodeURIComponent(url)}`)
    if (kopru) return kopru
    const onbellekten = await this.onbellek.gorselOku(url)
    if (onbellekten) return onbellekten
    const govde = await this._metin(url)
    if (!govde) return null
    await this.onbellek.gorselYaz(url, govde, '', damga)
    return govde
  }
}
