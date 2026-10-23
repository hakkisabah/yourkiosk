/**
 * KIOSK DURUM MAKİNESİ (tarayıcı) — Qt `pharmacy_app.py` akışının birebir karşılığı.
 *
 * Kritik kurallar (Qt ile aynı; bkz. `kiosk/pharmacy_app.py`, `core/*`):
 *  · döngü: her turda bir sonraki nöbetçi; liste bitince aktif yayın varsa yayın modu,
 *    yoksa başa dön (yayına geçilmez),
 *  · nöbet adımı 10 sn, yayın adımı yayının `duration`'ı (1–60 sn),
 *  · orta panel geçişi: çıkan aşağı (0→+viewport), giren yukarıdan (−viewport→0), 1800 ms InOutCubic,
 *  · sol panel kaydırması orta geçişle AYNI ANDA ve AYNI sürede; yalnızca gerektiğinde,
 *  · kuşak yalnızca yayın modunda; tekli modda kayıt kayıt ortaya girip bekleyip çıkar,
 *  · özellik bayrakları: nobet_listesi / yayinlar / kayan_yazi / saat_tarih.
 */
import { computed, reactive, type ComputedRef } from 'vue'

import { Ayarlar, type AyarBelgesi } from '@/veri/ayarlar'
import { adresMetni, cihazKonumunuBul, kaydiEkranBicimineCevir, tarihAralikMetni, type EkranKaydi } from '@/veri/ekran'
import { KusakAnimasyonu, kusakOgeleri, kusakMetni, kusakX } from '@/veri/kusak'
import { VeriKaynagi } from '@/veri/kaynak'
import { gosterilecekKayitlar, type CihazKonumu, type NobetKaydi } from '@/veri/nobet'
import { Onbellek } from '@/veri/onbellek'
import { aktifYayinlar, yayinAdresi, yayinSuresiMs, yayinSirasi, type YayinKaydi } from '@/veri/yayin'
import type { TetikBilgisi } from '@/veri/kaynak'
import { sabit, varsayilanlar, yerlesim } from '@/stiller/olcu'

/* Ortama bağlı olmayan zamanlayıcılar (tarayıcı + test ortamı) */
const zamanla = (islev: () => void, ms: number): number =>
  globalThis.setTimeout(islev, ms) as unknown as number
const aralikla = (islev: () => void, ms: number): number =>
  globalThis.setInterval(islev, ms) as unknown as number
const sonrakiKare = (islev: () => void): number =>
  typeof globalThis.requestAnimationFrame === 'function' ? globalThis.requestAnimationFrame(islev) : (islev(), 0)

export interface KioskSecenekleri {
  kaynak: VeriKaynagi
  onbellek?: Onbellek
  /** test için: zaman kaynağı */
  zaman?: () => Date
}

export interface Kiosk {
  durum: KioskState
  ayarlar: ComputedRef<Ayarlar>
  ozellik: (ad: string) => boolean
  baslat: () => void
  durdur: () => void
  yukle: (zorla?: boolean) => Promise<boolean>
  dongu: () => Promise<void>
  goster: (animasyonlu?: boolean) => void
  yayinaGec: (aktif?: YayinKaydi[]) => Promise<void>
  sonrakiYayin: () => Promise<void>
  yayindanCik: () => void
  saatGuncelle: () => void
  kusakAdimi: () => void
  yaziGenisligiAyarla: (genislik: number) => void
}

export interface KioskState {
  hazir: boolean
  hata: string
  kayitlar: EkranKaydi[]
  konum: CihazKonumu
  gunAnahtari: string
  index: number
  kaydirma: number
  animasyonlu: boolean
  bloklar: Array<EkranKaydi | null>
  aktifBlok: number
  konumlar: number[]
  yayinModu: boolean
  yayinlar: YayinKaydi[]
  yayinIndex: number
  gorselUrl: string
  gorselYukleniyor: boolean
  kusak: { metin: string; x: number; gorunur: boolean; ogeler: string[]; index: number }
  saat: { saat: string; tarih: string; gun: string }
  ozellikler: { nobet_listesi: boolean; yayinlar: boolean; kayan_yazi: boolean; saat_tarih: boolean }
  damga: string
  gunluk: string[]
}

const AYAR_VARSAYILANLARI = varsayilanlar

export function createKiosk(secenekler: KioskSecenekleri): Kiosk {
  const zaman = secenekler.zaman ?? (() => new Date())
  const onbellek = secenekler.onbellek ?? new Onbellek(sabit('ONBELLEK_GORSEL_SAKLAMA_GUN', 2))

  const durum = reactive<KioskState>({
    hazir: false,
    hata: '',
    kayitlar: [],
    konum: { bulundu: false },
    gunAnahtari: '',
    index: 0,
    kaydirma: 0,
    animasyonlu: false,
    bloklar: [null, null],
    aktifBlok: 0,
    konumlar: [0, -2000],
    yayinModu: false,
    yayinlar: [],
    yayinIndex: 0,
    gorselUrl: '',
    gorselYukleniyor: false,
    kusak: { metin: '-', x: 0, gorunur: false, ogeler: ['-'], index: 0 },
    saat: { saat: '', tarih: '', gun: '' },
    ozellikler: { nobet_listesi: true, yayinlar: true, kayan_yazi: true, saat_tarih: true },
    damga: '',
    gunluk: [],
  })

  let ayarBelgesi: AyarBelgesi | null = null
  let kapsamBelgesi: AyarBelgesi | null = null
  let animasyon: KusakAnimasyonu | null = null
  let yaziGenislik = 0
  const zamanlayicilar: number[] = []

  /**
   * DÖNGÜ ZAMANLAYICISI — Qt `timer_manager.cycle_timer` karşılığı (TEK zamanlayıcı).
   *
   * Qt `manage_loop` akışı: nöbet adımı `CYCLE_INTERVAL_MS` ile döner; yayın başlarken
   * `show_current_broadcast()` → `cycle_timer.start(duration)` ile AYNI zamanlayıcı yayının
   * süresine ayarlanır; yayından çıkarken `cycle_timer.start(CYCLE_INTERVAL_MS)` ile geri
   * alınır. Bu yüzden burada da tek, yeniden planlanabilir zamanlayıcı kullanılır.
   *
   * NEDEN ÖNEMLİ: `setInterval(10 sn)` + ayrı `setTimeout(yayın süresi)` birlikte çalışırsa
   * yayınlar süresi dolmadan atlanır, iki zincir üst üste biner ve mod değişiminde eski
   * zamanlayıcı yeni moda adım atlatır ("zamanlama hatası" + "geçişte takılı kalma").
   */
  let donguZamanlayici: number | null = null
  /** Yayın modu boyunca SABİT kalan aktif yayın listesi (Qt `active_yayinlar`). */
  let yayinListesi: YayinKaydi[] = []
  /** Liste (KUSAK_TEKLI=false) modunda bir kez kurulan kuşak metni. */
  let listeMetni = ''
  /** Kuşak liste modunda son adımın zamanı (geçen süreye göre kayma için). */
  let kusakSonZaman = 0
  /** Anlık değişiklik (uzun yoklama) imzası ve son uygulanan tetikleyici zamanı. */
  let degisiklikImzasi = ''
  let sonTetikZamani = ''
  let canliAcik = false

  function donguPlanla(ms: number): void {
    if (donguZamanlayici !== null) globalThis.clearTimeout(donguZamanlayici)
    donguZamanlayici = zamanla(() => {
      donguZamanlayici = null
      void dongu()
    }, Math.max(0, ms))
  }

  const log = (satir: string): void => {
    durum.gunluk.push(`${zaman().toISOString()} ${satir}`)
    if (durum.gunluk.length > 200) durum.gunluk.shift()
  }

  // ---------------------------------------------------------------- ayarlar
  const ayarlar = computed(
    () =>
      new Ayarlar(AYAR_VARSAYILANLARI, ayarBelgesi, kapsamBelgesi, {
        ilceId: durum.konum.ilceId,
        bolgeId: durum.konum.bolgeId,
        clientId: secenekler.kaynak.secenekler.clientID,
      }),
  )

  const ozellik = (ad: string): boolean => {
    if (ad in durum.ozellikler) return durum.ozellikler[ad as keyof KioskState['ozellikler']]
    return ayarlar.value.ozellik(ad)
  }

  function ozellikleriUygula(): void {
    durum.ozellikler = {
      nobet_listesi: ayarlar.value.ozellik('nobet_listesi'),
      yayinlar: ayarlar.value.ozellik('yayinlar'),
      kayan_yazi: ayarlar.value.ozellik('kayan_yazi'),
      saat_tarih: ayarlar.value.ozellik('saat_tarih'),
    }
    // Qt tutarlılık kuralı: nöbet + yayın birlikte kapalı olamaz → nöbet zorla açılır
    if (!durum.ozellikler.nobet_listesi && !durum.ozellikler.yayinlar) {
      durum.ozellikler.nobet_listesi = true
      log('ayar uyarısı: nöbet listesi ve yayınlar birlikte kapalı olamaz; nöbet listesi açıldı')
    }
    // yayınlar kapalıysa kuşak görünmez
    if (!durum.ozellikler.yayinlar) durum.ozellikler.kayan_yazi = false
  }

  // ---------------------------------------------------------------- veri
  /**
   * Veriyi yükler.
   *
   * `zorla = true` → damga aynı olsa da önbellek atlanır (panel/araç kaynaklı değişiklik ya da
   * tetikleyici): "veri değişti ama damga değişmedi" durumunda arayüz eski gövdeyi göstermesin.
   */
  async function yukle(zorla = false): Promise<boolean> {
    try {
      const damga = await secenekler.kaynak.lastupdate()
      const sistem = await secenekler.kaynak.sistemVerisi(damga, zorla)
      if (!sistem) {
        // Cihaz verisi depoda YOK (cihaza özgü, .gitignore). Kullanıcıya ne yapacağını yaz:
        durum.hata =
          'Nöbet verisi bulunamadı: lastSystemData.json. ' +
          'Bu cihazda veri dosyaları yok (depoya girmez). Düzeltme: cihazda bir kez ' +
          '`python3 tools/fetch_nobet.py` çalıştırın ya da eski kurulumdan ' +
          'lastupdate.json, lastSystemData.json, match.json, makinebilgileri.json dosyalarını kiosk/ klasörüne kopyalayın.'
        log('HATA: lastSystemData.json yok (cihaz verisi eksik)')
        return false
      }
      durum.damga = damga
      const match = await secenekler.kaynak.match()
      const clientId = secenekler.kaynak.secenekler.clientID
      if (!match) {
        // match.json hiç okunamadı (403/404/ağ). Sebebi kimlik eşleşmesinden AYRI göster:
        // yoksa "cihaz match.json'da yok" gibi yanıltıcı bir mesaj çıkar.
        durum.hata =
          'match.json okunamadı (ağ hatası ya da erişim reddi). ' +
          `Adres: ${secenekler.kaynak.veriTaban()}/match.json — taban adresinin sonunda çift "/" olmamalı.`
        log('HATA: match.json okunamadı (403/404/ağ)')
        return false
      }
      const konumHam = cihazKonumunuBul(match, clientId)
      if (!konumHam.bulundu) {
        durum.hata =
          `Cihaz kimliği (${clientId || '?'}) match.json içinde bulunamadı. ` +
          'match.json bu cihaza ait değil ya da eksik — cihazda `python3 tools/fetch_nobet.py` ile yeniden üretin.'
        log(`HATA: cihaz kimliği match.json'da yok (clientID=${clientId})`)
        return false
      }

      ayarBelgesi = (await secenekler.kaynak.ayarBelgesi('ayarlar.json')) as AyarBelgesi | null
      kapsamBelgesi = (await secenekler.kaynak.ayarBelgesi('kapsam-ayarlari.json')) as AyarBelgesi | null
      durum.konum = konumHam
      ozellikleriUygula()

      const kapsam = String(sabit('KAPSAM', 'ilce') || 'ilce')
      const an = zaman()
      const secim = gosterilecekKayitlar(sistem, konumHam, an, kapsam)
      durum.gunAnahtari = secim.anahtar

      const enBuyuk = sabit('MAX_GOSTERILEN_ECZANE', 60)
      const kayitlar: EkranKaydi[] = secim.kayitlar
        .slice(0, enBuyuk)
        .map((k) => kaydiEkranBicimineCevir(k, sabit('EKSIK_TELEFON_YERINE_BOLGE', true)))
        .sort((a, b) => a.bolge.toUpperCase().localeCompare(b.bolge.toUpperCase(), 'tr') || a.eczane.toUpperCase().localeCompare(b.eczane.toUpperCase(), 'tr'))

      if (!kayitlar.length) {
        durum.hata = `Cihazın bölgesi için nöbet kaydı yok (ilçe=${konumHam.ilceId} bölge=${konumHam.bolgeId}).`
        log('HATA: bölge için kayıt yok')
        return false
      }

      durum.kayitlar = kayitlar
      // yayın havuzu: Qt `MAX_AKTIF_YAYIN * 10` kadar kayıt bellekte tutulur
      durum.yayinlar = yayinSirasi(sistem).slice(0, sabit('MAX_AKTIF_YAYIN', 20) * 10)
      durum.index = Math.min(durum.index, kayitlar.length - 1)
      durum.kusak.ogeler = kusakOgeleri(
        kayitlar.map((k) => ({ eczane: k.eczane, tel: k.tel, bolge: k.bolge })),
        { eksikTelefonYerineBolge: sabit('EKSIK_TELEFON_YERINE_BOLGE', true) },
      )
      durum.kusak.index = 0

      // önbellek bakımı: veride artık geçmeyen / süresi geçen görselleri sil
      const gecerli = new Set(durum.yayinlar.map((y) => yayinAdresi(y)).filter(Boolean))
      const bakim = await onbellek.bakim(an, gecerli.size ? gecerli : undefined)
      if (bakim.silinen) log(`önbellek bakımı: ${bakim.silinen} görsel silindi`)

      durum.hazir = true
      durum.hata = ''
      log(
        `veri yüklendi: ${secim.anahtar} · ${konumHam.ilceId}/${konumHam.bolgeId} · ` +
          `${kayitlar.length} nöbetçi · ${durum.yayinlar.length} yayın (damga=${damga || '-'})`,
      )
      // MEVCUT kaydı koru (Qt `load_data` → `update_display()`): saatlik yenilemede orta panel
      // 0. kayda dönmez, sol paneldeki seçimle orta panel aynı kaydı gösterir (desenkron olmaz).
      const yukseklik = yerlesim.olculer.viewport_yukseklik
      const diger = durum.aktifBlok === 0 ? 1 : 0
      durum.bloklar[durum.aktifBlok] = durum.kayitlar[durum.index] ?? durum.kayitlar[0] ?? null
      durum.bloklar[diger] = null
      durum.konumlar = durum.aktifBlok === 0 ? [0, -yukseklik] : [-yukseklik, 0]
      durum.animasyonlu = false
      durum.kaydirma = kaydirmaHedefi()
      return true
    } catch (hata) {
      durum.hata = `Veri yüklenemedi: ${(hata as Error).message}`
      log(`HATA: ${(hata as Error).message}`)
      return false
    }
  }

  // ---------------------------------------------------------------- gösterim
  /** Sol panel kaydırma hedefi (Qt `sol_kaydirma_hedefi`, gerektiğinde kayar). */
  function kaydirmaHedefi(): number {
    const item = yerlesim.olculer.satir_yuksekligi
    const bosluk = Number(yerlesim.elle['sol.satir_bosluk'] ?? 10)
    const hedefY = durum.index * (item + bosluk)
    const gorunur = yerlesim.olculer.sol_gorunur_yukseklik
    const konum = durum.kaydirma
    if (hedefY < konum) return hedefY
    if (hedefY + item > konum + gorunur) return hedefY + item - gorunur
    return konum
  }

  /**
   * Orta paneli (ve sol paneli) geçerli kayda göre günceller.
   *
   * GEÇİŞ GÜVENLİĞİ: CSS geçişini tetiklemek için bir sonraki çizim karesi beklenir; ancak
   * `requestAnimationFrame` sayfa görünür değilken (occluded/arka plan) **duraklatılır** ve
   * durum hedefe hiç ulaşmaz → orta panel yarı yolda takılı kalır. Bu yüzden bir yedek
   * zaman aşımı da kurulur: hedef durum HER hâlükârda uygulanır (animasyon çalışmazsa
   * geçiş anlık olur, ama ekran ASLA eski/yarım durumda kalmaz).
   */
  function goster(animasyonlu = true): void {
    const kayit = durum.kayitlar[durum.index]
    if (!kayit) return
    const yukseklik = yerlesim.olculer.viewport_yukseklik
    const yeni = durum.aktifBlok === 0 ? 1 : 0
    const eski = durum.aktifBlok
    durum.animasyonlu = animasyonlu
    durum.bloklar[yeni] = kayit
    if (!animasyonlu) {
      durum.konumlar = yeni === 0 ? [0, -yukseklik] : [-yukseklik, 0]
      durum.aktifBlok = yeni
    } else {
      durum.konumlar[eski] = 0
      durum.konumlar[yeni] = -yukseklik
      // hedefe geçiş (tek sefer): kare (rAF) ya da yedek zaman aşımı ile
      let uygulandi = false
      const hedefeGec = (): void => {
        if (uygulandi) return
        uygulandi = true
        durum.konumlar[eski] = yukseklik
        durum.konumlar[yeni] = 0
        durum.aktifBlok = yeni
      }
      sonrakiKare(() => {
        sonrakiKare(hedefeGec)
      })
      zamanla(hedefeGec, 80) // yedek: rAF duraklatılsa bile hedefe geç
    }
    // sol panel kaydırması orta geçişle AYNI ANDA ve AYNI süreyle başlar
    if (sabit('SOL_PANEL_OTOMATIK_KAYDIRMA', true)) durum.kaydirma = kaydirmaHedefi()
  }

  /** Bir sonraki nöbetçiye geçer (Qt `update_display`). */
  function nobetIlerle(): void {
    if (!durum.ozellikler.nobet_listesi) return
    durum.index = (durum.index + 1) % Math.max(1, durum.kayitlar.length)
    goster(true)
  }

  // ---------------------------------------------------------------- yayın
  /** Yayın moduna geçer (Qt `start_broadcast_mode`). */
  async function yayinaGec(aktif?: YayinKaydi[]): Promise<void> {
    if (!durum.ozellikler.yayinlar) return
    const liste =
      aktif ??
      aktifYayinlar(
        { Yayinlar: Object.fromEntries(durum.yayinlar.map((y, i) => [String(i), y])) },
        zaman(),
        sabit('MAX_AKTIF_YAYIN', 20),
      )
    if (!liste.length) {
      log('yayın moduna geçilemedi: aktif yayın yok')
      return
    }
    // aktif listeyi sabitle: mod boyunca aynı liste kullanılır (Qt `active_yayinlar` gibi);
    // her adımda yeniden hesaplamak, süresi dolan bir yayını listeyi kaydırıp indeksleri
    // bozar → yayın atlanır/takılır.
    yayinListesi = liste
    durum.yayinModu = true
    durum.yayinIndex = 0
    durum.kusak.gorunur = durum.ozellikler.kayan_yazi
    if (durum.ozellikler.kayan_yazi) kusakBaslat()
    await yayiniGoster()
  }

  /**
   * Geçerli yayını gösterir (Qt `show_current_broadcast`).
   *
   * Süre yönetimi Qt ile AYNI: gösterimden sonra **döngü zamanlayıcısı** yayının süresine
   * ayarlanır (`cycle_timer.start(duration)`); ayrı bir zamanlayıcı KURULMAZ.
   */
  async function yayiniGoster(): Promise<void> {
    const yayin = yayinListesi[durum.yayinIndex]
    if (!yayin) {
      yayindanCik()
      return
    }
    const url = yayinAdresi(yayin)
    durum.gorselYukleniyor = true
    const govde = url ? await secenekler.kaynak.gorsel(url, durum.damga) : null
    durum.gorselYukleniyor = false
    if (!govde) {
      log(`yayın görseli alınamadı: ${url || '(adres yok)'} → atlanıyor`)
      await sonrakiYayin()
      return
    }
    durum.gorselUrl = url
    if (url) void onbellek.gorselGosterildi(url)
    donguPlanla(yayinSuresiMs(yayin, ayarlar.value))
  }

  /** Sıradaki yayına geçer; liste bittiyse yayın modundan çıkar (Qt `show_next_broadcast`). */
  async function sonrakiYayin(): Promise<void> {
    durum.yayinIndex += 1
    if (durum.yayinIndex >= yayinListesi.length) {
      yayindanCik()
      return
    }
    await yayiniGoster()
  }

  /** Yayın modundan çıkar (Qt `stop_broadcast_mode`) — döngü 10 sn'ye geri alınır. */
  function yayindanCik(): void {
    durum.yayinModu = false
    durum.yayinIndex = 0
    durum.gorselUrl = ''
    durum.kusak.gorunur = false
    durum.index = 0
    if (durum.ozellikler.nobet_listesi) goster(true)
    else log('yayın listesi bitti; nöbet listesi kapalı olduğu için yayın görünümünde beklenecek')
    donguPlanla(sabit('CYCLE_INTERVAL_MS', 10_000))
  }

  // ---------------------------------------------------------------- döngü
  /**
   * Qt `manage_loop` birebir — her adım SONUNDA bir sonraki adımı planlar (tek zamanlayıcı):
   *  1) yayın modundaysak sonraki yayına geç (süresi `yayiniGoster` içinde planlanır),
   *  2) nöbet listesi kapalıysa yalnız-yayın döngüsü,
   *  3) yayınlar kapalıysa yalnız nöbet listesi döner,
   *  4) liste bittiyse aktif yayın varsa yayına geç, yoksa başa dön.
   */
  async function dongu(): Promise<void> {
    const adim = (): void => donguPlanla(sabit('CYCLE_INTERVAL_MS', 10_000))
    if (durum.yayinModu) {
      await sonrakiYayin()
      return
    }
    if (!durum.ozellikler.nobet_listesi) {
      await yalnizYayinDongusu()
      return
    }
    if (!durum.ozellikler.yayinlar) {
      nobetIlerle()
      adim()
      return
    }
    if (durum.index + 1 >= durum.kayitlar.length) {
      if (aktifYayinListesi().length) {
        await yayinaGec()
      } else {
        durum.index = 0
        goster(true)
        adim()
      }
      return
    }
    nobetIlerle()
    adim()
  }

  /** Nöbet listesi kapalıyken (Qt `_yalniz_yayin_dongusu`). */
  async function yalnizYayinDongusu(): Promise<void> {
    const aktif = durum.ozellikler.yayinlar ? aktifYayinListesi() : []
    if (aktif.length) {
      await yayinaGec(aktif)
      return
    }
    durum.kusak.gorunur = durum.ozellikler.kayan_yazi
    log('aktif yayın yok; nöbet listesi kapalı → yayın görünümünde bekleniyor')
    donguPlanla(sabit('CYCLE_INTERVAL_MS', 10_000))
  }

  // ---------------------------------------------------------------- canlı değişiklik
  /**
   * Damga + tetikleyici yoklaması (`DAMGA_KONTROL_MS`, varsayılan 20 sn).
   *
   * Yalnızca KÜÇÜK dosyalar okunur (`lastupdate.json`, `tetikle.json`); büyük veri
   * dosyaları damga değişmedikçe indirilmez. Anlık uç (`/degisiklik`) yoksa tek yol budur.
   */
  async function damgaKontrol(): Promise<void> {
    if (!durum.hazir) return
    const damga = await secenekler.kaynak.lastupdate()
    if (damga && durum.damga && damga !== durum.damga) {
      log(`nöbet verisi değişti (damga ${durum.damga} → ${damga}) → yenileniyor`)
      await yukle()
      return
    }
    const tetik = await secenekler.kaynak.tetikleyici()
    if (tetikUygulanmali(tetik, durum.konum, sonTetikZamani) && tetik) {
      sonTetikZamani = tetik.zaman
      log(`tetikleyici uygulanıyor (${tetik.zaman}) → tazeleniyor`)
      await yukle(true) // tetikleyici: damga aynı olsa da önbelleği atla
    }
  }

  /**
   * CANLI DÖNGÜ (uzun yoklama): yerel sunucu imza değişene kadar isteği açık tutar →
   * nöbet değişikliği tipik olarak <1 sn içinde ekrana yansır (20 sn beklenmez).
   * Uç yoksa döngü sessizce biter; `damgaKontrol` yoklaması devam eder.
   */
  async function canliBaslat(): Promise<void> {
    canliAcik = true
    let ilkTur = true
    while (canliAcik) {
      const bildirim = await secenekler.kaynak.degisiklikBekle(
        degisiklikImzasi,
        sabit('DEGISIKLIK_BEKLEME_S', 30),
      )
      if (!canliAcik) return
      if (!bildirim) {
        log('anlık değişiklik ucu yok → 20 sn damga yoklaması kullanılıyor')
        return
      }
      const oncekiImza = degisiklikImzasi
      degisiklikImzasi = bildirim.imza
      // HIZLI DÖNME KORUMASI: imza DEĞİŞTİYSE beklemeden işlenir (gerçek değişiklik);
      // aynı imzayla anında yanıt gelirse (sunucu sorunu) kısa bir nefes verilir.
      const ayniImza = Boolean(bildirim.imza) && bildirim.imza === oncekiImza
      const bekleme = !bildirim.imza ? 5_000 : ayniImza ? 800 : 0
      if (bekleme > 0) {
        await new Promise<void>((coz) => {
          zamanla(coz, bekleme)
        })
        if (!canliAcik) return
      }
      const tetikGerekli = tetikUygulanmali(bildirim.tetik, durum.konum, sonTetikZamani)
      if (tetikGerekli && bildirim.tetik) {
        sonTetikZamani = bildirim.tetik.zaman
        log(
          `tetikleyici alındı (${bildirim.tetik.zaman})` +
            (bildirim.tetik.ilceId ? ` · ilçe=${bildirim.tetik.ilceId}` : ' · tüm cihazlar'),
        )
      }
      if (ilkTur) {
        ilkTur = false // ilk tur yalnız imzayı öğrenir (veri biraz önce yüklendi)
        continue
      }
      const damgaDegisti = Boolean(bildirim.damga) && bildirim.damga !== durum.damga
      if (bildirim.degisti && (damgaDegisti || !bildirim.damga)) {
        log(`anlık bildirim: nöbet verisi değişti (damga=${bildirim.damga || '-'}) → yenileniyor`)
        await yukle(!damgaDegisti) // damga değişmediyse yalnız yerel içerik değişti → önbelleği atla
      } else if (bildirim.degisti) {
        log('anlık bildirim: yerel veri değişti (damga aynı) → önbellek atlanıp tazeleniyor')
        await yukle(true)
      } else if (tetikGerekli) {
        log('anlık bildirim: tetikleyici uygulanıyor → tazeleniyor')
        await yukle(true)
      }
    }
  }

  // ---------------------------------------------------------------- kuşak
  const kusakAyar = {
    tekli: () => sabit('KUSAK_TEKLI', true),
    giris: () => sabit('KUSAK_GIRIS_MS', 1200),
    durma: () => sabit('KUSAK_DURMA_MS', 3000),
    cikis: () => sabit('KUSAK_CIKIS_MS', 1200),
    adim: () => sabit('KUSAK_ADIM_ARALIGI_MS', 30),
    hiz: () => sabit('KUSAK_HIZ', 5),
    ayirici: () => String(sabit('KUSAK_AYIRICI', '    |   ')),
  }

  function kusakBaslat(): void {
    animasyon = new KusakAnimasyonu(kusakAyar.giris(), kusakAyar.durma(), kusakAyar.cikis(), kusakAyar.adim())
    durum.kusak.metin = kusakMetni(durum.kusak.ogeler, kusakAyar.tekli(), kusakAyar.ayirici())
    // liste modu metni BİR KEZ kurulur (Qt `_ticker_metnini_yerlestir`): her adımda 60 kaydı
    // birleştirmek tarayıcıda gereksiz CPU yükü ve takılma sebebiydi.
    listeMetni = kusakMetni(durum.kusak.ogeler, false, kusakAyar.ayirici())
    durum.kusak.x = yerlesim.ekran.genislik
    kusakSonZaman = 0
  }

  /**
   * Kuşak tikı (Qt `scroll_ticker`), `KUSAK_ADIM_ARALIGI_MS` (30 ms).
   * Liste modunda kayma **geçen süreye göre** hesaplanır: Qt'de QTimer düzenlidir, tarayıcıda
   * zamanlayıcı yük altında gecikir; sabit "her adımda 5 px" yazıyı düzensiz sıçratır. Nominal
   * hız (`KUSAK_HIZ` px / `KUSAK_ADIM_ARALIGI_MS`) korunur, tek adımda en çok 250 ms'lik kayma
   * uygulanır (uzun bir duraklamadan sonra yazının ekrandan atlamaması için).
   */
  function kusakAdimi(): void {
    if (!durum.yayinModu || !durum.ozellikler.kayan_yazi || !durum.kusak.gorunur) return
    if (kusakAyar.tekli()) {
      if (!animasyon) kusakBaslat()
      const donguBitti = animasyon?.adim() ?? false
      durum.kusak.x = kusakX(yerlesim.ekran.genislik, yaziGenislik, animasyon?.oran() ?? 0)
      if (donguBitti) {
        durum.kusak.index = (durum.kusak.index + 1) % Math.max(1, durum.kusak.ogeler.length)
        durum.kusak.metin = durum.kusak.ogeler[durum.kusak.index] ?? '-'
        animasyon?.sifirla()
        durum.kusak.x = yerlesim.ekran.genislik
      }
      return
    }
    // liste modu: sağdan sola sürekli akış (geçen süreye göre)
    durum.kusak.metin = listeMetni || kusakMetni(durum.kusak.ogeler, false, kusakAyar.ayirici())
    const simdi = globalThis.performance?.now?.() ?? Date.now()
    const adimMs = Math.max(1, kusakAyar.adim())
    const gecen = kusakSonZaman ? Math.min(Math.max(0, simdi - kusakSonZaman), 250) : adimMs
    kusakSonZaman = simdi
    durum.kusak.x -= kusakAyar.hiz() * (gecen / adimMs)
    if (yaziGenislik > 0 && durum.kusak.x < -yaziGenislik) durum.kusak.x = yerlesim.ekran.genislik
  }

  function yaziGenisligiAyarla(genislik: number): void {
    yaziGenislik = Math.max(0, genislik)
  }

  // ---------------------------------------------------------------- saat
  function saatGuncelle(): void {
    if (!durum.ozellikler.saat_tarih) {
      durum.saat = { saat: '', tarih: '', gun: '' }
      return
    }
    const an = zaman()
    const iki = (n: number): string => String(n).padStart(2, '0')
    const gun = an.toLocaleDateString('tr-TR', { weekday: 'long' })
    durum.saat = {
      saat: `${iki(an.getHours())}:${iki(an.getMinutes())}`,
      tarih: `${iki(an.getDate())}.${iki(an.getMonth() + 1)}.${an.getFullYear()}`,
      gun: gun.charAt(0).toUpperCase() + gun.slice(1),
    }
  }

  // ---------------------------------------------------------------- yaşam döngüsü
  function baslat(): void {
    saatGuncelle()
    void yukle().then(() => {
      // ilk adım hemen çalışır ve bir sonrakini kendisi planlar (Qt: yükleme sonrası
      // `manage_loop` çağrısı + `cycle_timer.start(CYCLE_INTERVAL_MS)`).
      void dongu()
    })
    // CANLI DEĞİŞİKLİK: uzun yoklama (anında) — uç yoksa 20 sn damga yoklaması devrede
    void canliBaslat()
    const periyotlar: Array<[number, () => void]> = [
      [sabit('REFRESH_INTERVAL_MS', 3_600_000), () => void yukle()],
      [sabit('DAMGA_KONTROL_MS', 20_000), () => void damgaKontrol()],
      [1000, saatGuncelle],
      [sabit('KUSAK_ADIM_ARALIGI_MS', 30), kusakAdimi],
    ]
    for (const [ms, islev] of periyotlar) zamanlayicilar.push(aralikla(islev, ms))
  }

  function durdur(): void {
    canliAcik = false
    if (donguZamanlayici !== null) {
      globalThis.clearTimeout(donguZamanlayici)
      donguZamanlayici = null
    }
    for (const kimlik of zamanlayicilar.splice(0)) {
      globalThis.clearInterval(kimlik)
      globalThis.clearTimeout(kimlik)
    }
  }

  // aktif yayın listesi (pencere kuralı: ilk yayın moduna girişte de bu kullanılır)
  function aktifYayinListesi(): YayinKaydi[] {
    const sozluk: Record<string, YayinKaydi> = {}
    durum.yayinlar.forEach((y, i) => {
      sozluk[String(i)] = y
    })
    return aktifYayinlar({ Yayinlar: sozluk }, zaman(), sabit('MAX_AKTIF_YAYIN', 20))
  }

  return {
    durum,
    ayarlar,
    ozellik,
    baslat,
    durdur,
    yukle,
    dongu,
    goster: (animasyonlu?: boolean): void => goster(animasyonlu),
    yayinaGec: () => yayinaGec(),
    sonrakiYayin: () => sonrakiYayin(),
    yayindanCik,
    saatGuncelle,
    kusakAdimi,
    yaziGenisligiAyarla,
  }
}

/**
 * NÖBET DEĞİŞİKLİĞİ TETİKLEYİCİSİ KURALI (saf işlev; arayüz + testler aynı kuralı kullanır).
 *
 * Panel bir nöbet değişikliği yaptığında `tetikle.json` yazar:
 * `{"zaman": "2026-10-17T09:12:00", "ilceId": "...", "bolgeId": "...", "aciklama": "..."}`
 * Cihaz yalnızca KENDİSİNİ ilgilendiren tetikleyiciyi hemen uygular:
 *  · `ilceId` boş/"*" → tüm cihazlar,
 *  · `ilceId`/`bolgeId` kendi konumuyla eşleşiyorsa → bu cihaz,
 *  · başka ilçe → hemen yenilenmez (20 sn damga yoklaması + saatlik kontrol yine çalışır).
 * Aynı tetikleyici iki kez uygulanmaz (zaman damgası karşılaştırılır).
 */
export function tetikUygulanmali(
  tetik: TetikBilgisi | null,
  konum: { ilceId?: string; bolgeId?: string },
  sonUygulanan: string,
): boolean {
  if (!tetik || !tetik.zaman) return false
  if (sonUygulanan && tetik.zaman <= sonUygulanan) return false
  const ilce = tetik.ilceId.trim()
  const bolge = tetik.bolgeId.trim()
  if (!ilce || ilce === '*') return true
  if (konum.ilceId && ilce === konum.ilceId) return true
  if (bolge && konum.bolgeId && bolge === konum.bolgeId) return true
  return false
}

/** Orta panelin göstereceği metinler (App bileşenleri kullanır). */
export function ortaMetinler(kayit: EkranKaydi): { ad: string; adres: string; telefon: string; aralik: string } {
  return {
    ad: `${kayit.eczane.toUpperCase()} ECZANESİ`,
    adres: adresMetni(kayit),
    telefon: kayit.ikincil,
    aralik: tarihAralikMetni(kayit),
  }
}

/** Kaydın kuşak metni (test/günlük). */
export function kayitKusakMetni(kayit: EkranKaydi, ayirici = '    |   ', tekli = true, ogeler?: string[]): string {
  return kusakMetni(ogeler ?? [`${kayit.eczane.toUpperCase()} - ${kayit.ikincil}`], tekli, ayirici)
}

export type { NobetKaydi }
