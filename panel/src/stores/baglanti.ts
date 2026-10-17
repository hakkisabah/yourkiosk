/** Tüm panel durumunun ortak girişi: bağlantı (Cognito/S3) + veri + ayarlar. */
import { defineStore } from 'pinia'

import { cikisYap, girisYap, oturumTokeni } from '@/aws/auth'
import { eksikDegiskenler, hataMesaji, panelConfig, yerTutucuDegiskenler, type PanelConfig } from '@/aws/config'
import { lambdaKaynagi, s3Kaynagi } from '@/aws/kaynaklar'
import { LambdaIstemcisi } from '@/aws/lambda'
import { istemci } from '@/aws/s3'
import type { VeriKaynagi } from '@/aws/veriKaynagi'

interface Durum {
  yapilandirma: PanelConfig | null
  yapilandirmaHatasi: string | null
  yerTutucular: string[]
  idToken: string | null
  eposta: string
  hazir: boolean
  mesgul: boolean
  hata: string | null
}

export const useBaglanti = defineStore('baglanti', {
  state: (): Durum => ({
    yapilandirma: null,
    yapilandirmaHatasi: null,
    yerTutucular: [],
    idToken: null,
    eposta: '',
    hazir: false,
    mesgul: false,
    hata: null,
  }),
  getters: {
    girisYapildi: (s) => Boolean(s.idToken),
    mod: (s) => s.yapilandirma?.authModu ?? 'cognito',
    /**: Etkin veri kaynağı (Cognito → S3 doğrudan, Lambda → presigned URL). */
    kaynak: (s): VeriKaynagi | null => {
      if (!s.yapilandirma) return null
      if (s.yapilandirma.authModu === 'lambda') {
        return s.idToken ? lambdaKaynagi(s.yapilandirma) : null
      }
      return s.idToken ? s3Kaynagi(s.yapilandirma, istemci(s.yapilandirma, s.idToken)) : null
    },
    kova: (s) => s.yapilandirma?.bucket ?? '',
    onEk: (s) => s.yapilandirma?.prefix ?? '',
  },
  actions: {
    /** Ortam değişkenlerini okur ve açık oturumu (varsa) geri yükler. */
    async baslat(): Promise<void> {
      this.hata = null
      const eksik = eksikDegiskenler(import.meta.env)
      const yerTutucu = yerTutucuDegiskenler(import.meta.env)
      this.yerTutucular = yerTutucu
      if (eksik.length || yerTutucu.length) {
        const parcalar: string[] = []
        if (eksik.length) parcalar.push(`eksik: ${eksik.join(', ')}`)
        if (yerTutucu.length) parcalar.push(`örnek dosyadan kopyalanmış yer tutucu: ${yerTutucu.join(', ')}`)
        this.yapilandirmaHatasi = `${parcalar.join(' · ')} — .env.ornek dosyasını .env.local olarak kopyalayıp gerçek değerleri girin.`
        this.hazir = true
        return
      }
      try {
        this.yapilandirma = panelConfig(import.meta.env)
      } catch (hata) {
        this.yapilandirmaHatasi = hataMesaji(hata)
        this.hazir = true
        return
      }
      try {
        if (this.yapilandirma.authModu === 'lambda') {
          const { giris } = await new LambdaIstemcisi(this.yapilandirma).oturumKontrol()
          this.idToken = giris ? 'cookie-oturumu' : null
        } else {
          this.idToken = await oturumTokeni(this.yapilandirma)
        }
      } catch (hata) {
        // Oturum okunamadı: kritik değil, giriş ekranına düşülür
        this.idToken = null
        this.hata = hataMesaji(hata)
      }
      this.hazir = true
    },
    /** Giriş: Cognito modunda e-posta+şifre, Lambda modunda yalnızca şifre. */
    async giris(eposta: string, sifre: string): Promise<boolean> {
      if (!this.yapilandirma) return false
      this.mesgul = true
      this.hata = null
      try {
        if (this.yapilandirma.authModu === 'lambda') {
          await new LambdaIstemcisi(this.yapilandirma).giris(sifre)
          this.idToken = 'cookie-oturumu'
          this.eposta = 'yönetici'
        } else {
          this.idToken = await girisYap(this.yapilandirma, eposta, sifre)
          this.eposta = eposta.trim()
        }
        return true
      } catch (hata) {
        this.hata = hataMesaji(hata)
        return false
      } finally {
        this.mesgul = false
      }
    },
    async cikis(): Promise<void> {
      const mod = this.yapilandirma?.authModu
      try {
        if (mod === 'lambda' && this.yapilandirma) {
          await new LambdaIstemcisi(this.yapilandirma).cikis()
        } else if (this.yapilandirma) {
          cikisYap(this.yapilandirma, this.eposta)
        }
      } catch {
        /* çıkışta hata olsa da yerel oturumu kapatıyoruz */
      }
      this.idToken = null
      this.eposta = ''
    },
    hataAyikla(hata: unknown): string {
      const mesaj = hataMesaji(hata)
      this.hata = mesaj
      return mesaj
    },
  },
})
