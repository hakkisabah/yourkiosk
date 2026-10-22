/**
 * Kiosk dosyalarının panel durumu: okuma, yerel düzenleme, S3'e yazma.
 * Her dosya için S3 ETag'i saklanır; kaydetme sırasında dosya değişmişse uyarı döner.
 */
import { defineStore } from 'pinia'

import { DOSYALAR } from '@/aws/config'
import { okumaPlani } from '@/domain/dosyaSecimi'
import { tetikBelgesi, tetikGerekir } from '@/domain/tetik'
import type { VeriKaynagi } from '@/aws/veriKaynagi'
import type { KapsamBelgesi } from '@/domain/kapsam'
import type { SistemVerisi } from '@/domain/veri'
import {
  silinecekYayinlar,
  VARSAYILAN_EK_SAAT,
  zamanDamgasi,
  type TemizlikSonucu,
} from '@/domain/temizlik'

import { useBaglanti } from './baglanti'

export type AyarBelgesi = Record<string, Record<string, unknown>>

interface DosyaDurumu<T> {
  veri: T | null
  etag?: string
  boyut?: number
  sonDegisiklik?: string
  yuklendi: boolean
}

interface Durum {
  ayarlar: DosyaDurumu<AyarBelgesi>
  kapsam: DosyaDurumu<KapsamBelgesi>
  sistem: DosyaDurumu<SistemVerisi>
  sablon: DosyaDurumu<Record<string, unknown>>
  match: DosyaDurumu<Record<string, unknown>>
  lastupdate: DosyaDurumu<Record<string, unknown>>
  makine: DosyaDurumu<Record<string, unknown>>
  mesgul: boolean
  sonUyari: string | null
  sonBasari: string | null
}

const bos = <T,>(): DosyaDurumu<T> => ({ veri: null, yuklendi: false })

export const useDosyalar = defineStore('dosyalar', {
  state: (): Durum => ({
    ayarlar: bos<AyarBelgesi>(),
    kapsam: bos<KapsamBelgesi>(),
    sistem: bos<SistemVerisi>(),
    sablon: bos<Record<string, unknown>>(),
    match: bos<Record<string, unknown>>(),
    lastupdate: bos<Record<string, unknown>>(),
    makine: bos<Record<string, unknown>>(),
    mesgul: false,
    sonUyari: null,
    sonBasari: null,
  }),
  getters: {
    ayarlarBelgesi: (s): AyarBelgesi => s.ayarlar.veri ?? {},
    kapsamBelgesi: (s): KapsamBelgesi => s.kapsam.veri ?? {},
    sistemVerisi: (s): SistemVerisi => s.sistem.veri ?? {},
    clientId: (s): string => String((s.makine.veri as { clientID?: unknown })?.clientID ?? ''),
  },
  actions: {
    /** Veri kaynağını döner; oturum/yapılandırma yoksa null (hata FIRLATMAZ). */
    _baglan(): { kaynak: VeriKaynagi; baglanti: ReturnType<typeof useBaglanti> } | null {
      const baglanti = useBaglanti()
      const kaynak = baglanti.kaynak
      if (!kaynak) {
        this.sonUyari =
          baglanti.yapilandirmaHatasi ?? 'Oturum yok: veriler yüklenmedi (önce giriş yapın).'
        return null
      }
      return { kaynak, baglanti }
    },
    async dosyaYukle<T>(anahtar: keyof Durum, ad: string): Promise<void> {
      const baglan = this._baglan()
      if (!baglan) return
      const sonuc = await baglan.kaynak.oku<T>(ad)
      const hedef = this[anahtar] as DosyaDurumu<T>
      hedef.veri = sonuc?.veri ?? null
      hedef.etag = sonuc?.etag
      hedef.boyut = sonuc?.boyut
      hedef.sonDegisiklik = sonuc?.sonDegisiklik
      hedef.yuklendi = true
    },
    /** Tüm kiosk dosyalarını S3'ten okur. */
    async hepsiniYukle(): Promise<void> {
      const baglan = this._baglan()
      if (!baglan) return
      this.mesgul = true
      this.sonUyari = null
      this.sonBasari = null
      try {
        // TEK liste isteği: kovada olmayan dosya için GET atmayız (boş kovada 7 × 404 üretiyordu).
        // Liste alınamazsa eski davranışa düşeriz (tek tek dene).
        let anahtarlar: string[] | null = null
        try {
          anahtarlar = (await baglan.kaynak.liste()).map((e) => e.anahtar)
        } catch {
          anahtarlar = null
        }
        const plan = new Map(okumaPlani(anahtarlar, baglan.baglanti.onEk).map((k) => [k.ad, k.varMi]))
        const adlar = Object.entries(DOSYALAR) as Array<[keyof Durum, string]>
        await Promise.all(
          adlar.map(async ([anahtar, ad]) => {
            if (plan.get(ad) === false) {
              const hedef = this[anahtar] as unknown as DosyaDurumu<unknown>
              hedef.veri = null
              hedef.etag = undefined
              hedef.boyut = undefined
              hedef.sonDegisiklik = undefined
              hedef.yuklendi = true
              return
            }
            await this.dosyaYukle(anahtar, ad)
          }),
        )
      } catch (hata) {
        this.sonUyari = baglan.baglanti.hataAyikla(hata)
      } finally {
        this.mesgul = false
      }
    },
    /** Tek bir dosyayı yazar (ETag denetimiyle) ve durumu tazeler. */
    async kaydet(
      anahtar: 'ayarlar' | 'kapsam' | 'sistem' | 'sablon' | 'match' | 'lastupdate' | 'makine',
      ad: string,
      veri: unknown,
    ): Promise<boolean> {
      const baglan = this._baglan()
      if (!baglan) return false
      this.mesgul = true
      this.sonUyari = null
      this.sonBasari = null
      try {
        const hedef = this[anahtar] as DosyaDurumu<unknown>
        const sonuc = await baglan.kaynak.yaz(ad, veri, hedef.etag)
        if (sonuc.uyari) {
          this.sonUyari = sonuc.uyari
          return false
        }
        hedef.veri = veri
        hedef.etag = sonuc.etag
        hedef.yuklendi = true
        // Ekranda görüneni değiştiren her yayın cihazı tetikler (cihazda `tetik.aktif` /
        // `tetik.modlar` ile filtrelenir). Tetik yazılamazsa kayıt yine geçerli sayılır.
        if (tetikGerekir(ad)) {
          try {
            await baglan.kaynak.yaz('tetikle.json', tetikBelgesi(ad))
          } catch {
            /* tetikleyici yazılamadı: cihaz normal aralıkta güncellenir */
          }
        }
        this.sonBasari = `${ad} kaydedildi (${sonuc.anahtar})`
        return true
      } catch (hata) {
        this.sonUyari = baglan.baglanti.hataAyikla(hata)
        return false
      } finally {
        this.mesgul = false
      }
    },
    /** Yerel düzenlemeyi (kaydetmeden) duruma yazar. */
    yerelAyarla(anahtar: 'ayarlar' | 'kapsam' | 'sistem' | 'sablon' | 'match', veri: unknown): void {
      const hedef = this[anahtar] as DosyaDurumu<unknown>
      hedef.veri = veri
    },
    /**
     * SÜRESİ GEÇEN YAYINLARI TEMİZLE (S3 + veri dosyası) — kullanıcı isteği:
     * "hem cihazda hem de S3'te görsel yayınlarının son gösterim tarihi olduğu için
     * iki tarafta da otomatik silinmesini sağlayan kurgu".
     *
     * Sıra: (1) kendi kovamızdaki görsel nesneleri silinir, (2) `lastSystemData.json`
     * yalnızca süresi geçen kayıtlar çıkarılarak yeniden yazılır (ETag denetimiyle),
     * (3) `lastupdate.json` damgası güncellenir → cihazlar saatlik kontrolde yeni veriyi
     * alır ve kendi görsel önbelleğini buna göre temizler.
     *
     * `kuru = true` yalnızca ÖNİZLEME yapar (hiçbir şey silinmez/yazılmaz).
     */
    async yayinlariTemizle(kuru = false, ekSaat = VARSAYILAN_EK_SAAT): Promise<TemizlikSonucu | null> {
      const baglan = this._baglan()
      if (!baglan) return null
      const cfg = baglan.baglanti.yapilandirma
      const sonuc = silinecekYayinlar(
        this.sistem.veri,
        new Date(),
        ekSaat,
        cfg?.bucket ?? '',
        cfg?.prefix ?? '',
      )
      if (!sonuc.silinenler.length) {
        this.sonBasari =
          sonuc.atlananlar > 0
            ? `Süresi geçen yayın yok (${sonuc.atlananlar} kaydın son gösterim tarihi okunamadı, korundu).`
            : 'Süresi geçen yayın yok.'
        return sonuc
      }
      if (kuru) return sonuc

      const hatalar: string[] = []
      let silinenNesne = 0
      for (const yayin of sonuc.silinenler) {
        if (!yayin.anahtar) continue // dış adres → nesne bizim kovamızda değil
        if (!baglan.kaynak.silDesteklenir) {
          hatalar.push(`${yayin.anahtar}: bu modda nesne silme kapalı`)
          continue
        }
        try {
          await baglan.kaynak.nesneSil(yayin.anahtar)
          silinenNesne += 1
        } catch (hata) {
          hatalar.push(`${yayin.anahtar}: ${(hata as Error).message}`)
        }
      }

      const yazildi = await this.kaydet('sistem', DOSYALAR.sistem, sonuc.kalanlar)
      if (!yazildi) return sonuc // ETag uyuşmazlığı vb.: sonUyari `kaydet` içinde dolduruldu

      await this.kaydet('lastupdate', DOSYALAR.lastupdate, { lastupdate: zamanDamgasi(new Date()) })
      this.sonBasari =
        `${sonuc.silinenler.length} süresi geçen yayın silindi` +
        ` (S3 nesnesi: ${silinenNesne}); cihazlar güncelleme damgasıyla haberdar edildi.`
      if (hatalar.length) {
        this.sonUyari = `Bazı nesneler silinemedi: ${hatalar.slice(0, 3).join(' | ')}`
      }
      return sonuc
    },
    async silDosya(ad: string): Promise<void> {
      const baglan = this._baglan()
      if (!baglan) return
      if (!baglan.kaynak.silDesteklenir) {
        this.sonUyari = 'Dosya silme bu modda kapalıdır (Lambda modu yalnızca oku/yaz izni verir).'
        return
      }
      try {
        await baglan.kaynak.sil(ad)
        this.sonBasari = `${ad} silindi`
      } catch (hata) {
        this.sonUyari = baglan.baglanti.hataAyikla(hata)
      }
    },
  },
})
