/**
 * İki veri kaynağı uygulaması:
 *
 *  • `s3Kaynagi`     — Cognito modu: Identity Pool'dan alınan geçici AWS anahtarıyla S3'e doğrudan.
 *  • `lambdaKaynagi` — Lambda modu: HttpOnly cookie oturumu + presigned S3 URL'leri (tarayıcıda anahtar YOK).
 *
 * İkisi de aynı güvenceleri verir: yazma öncesi ETag karşılaştırması (dosya bu arada
 * değiştiyse kaydetme reddedilir) ve yalnızca bilinen kiosk dosyaları.
 */
import { DOSYALAR, s3Anahtar, type PanelConfig } from './config'
import { EtagUyusmazligi, type DosyaBilgisi, type LambdaYanit, type VeriKaynagi } from './veriKaynagi'
import {
  dosyaBilgisi as s3Bilgi,
  jsonOku,
  jsonYaz,
  listele as s3Listele,
  nesneSil as s3NesneSil,
  sil as s3Sil,
  tumDosyaBilgileri,
} from './s3'
import { LambdaIstemcisi } from './lambda'
import type { S3Client } from '@aws-sdk/client-s3'

// ------------------------------------------------------------------ Cognito modu
export function s3Kaynagi(cfg: PanelConfig, istemci: S3Client): VeriKaynagi {
  return {
    mod: 'cognito',
    silDesteklenir: true,
    async oku<T>(ad: string): Promise<LambdaYanit<T> | null> {
      const sonuc = await jsonOku<T>(istemci, cfg, ad)
      if (!sonuc) return null
      return {
        veri: sonuc.veri,
        etag: sonuc.etag,
        boyut: sonuc.boyut,
        sonDegisiklik: sonuc.sonDegisiklik,
        anahtar: sonuc.anahtar,
      }
    },
    yaz: (ad, veri, etag) => jsonYaz(istemci, cfg, ad, veri, etag),
    bilgi: (ad) => s3Bilgi(istemci, cfg, ad),
    tumBilgiler: () => tumDosyaBilgileri(istemci, cfg),
    liste: () => s3Listele(istemci, cfg),
    sil: (ad) => s3Sil(istemci, cfg, ad),
    nesneSil: (anahtar) => s3NesneSil(istemci, cfg, anahtar),
  }
}

// ------------------------------------------------------------------ Lambda modu
export function lambdaKaynagi(cfg: PanelConfig, istemci = new LambdaIstemcisi(cfg)): VeriKaynagi {
  /** Presigned GET ile okur; `etag` verilirse koşullu (If-Match) okuma yapılır. */
  async function _oku<T>(ad: string, etag?: string): Promise<LambdaYanit<T> | null> {
    const imza = await istemci.imzala({ dosya: ad, islem: 'oku', etag })
    const yanit = await istemci.s3Istek(imza.url, {
      method: 'GET',
      headers: etag ? { 'If-Match': etag } : undefined,
    })
    if (yanit.status === 404) return null
    if (yanit.status === 412) throw new EtagUyusmazligi(ad)
    if (!yanit.ok) throw new Error(`S3 okuma hatası (${yanit.status})`)
    const metin = await yanit.text()
    let veri: T
    try {
      veri = JSON.parse(metin) as T
    } catch {
      throw new Error(`${ad}: JSON çözülemedi (dosya bozuk olabilir)`)
    }
    return {
      veri,
      etag: yanit.headers.get('ETag') ?? undefined,
      boyut: new TextEncoder().encode(metin).length,
      sonDegisiklik: yanit.headers.get('Last-Modified') ?? undefined,
      anahtar: s3Anahtar(ad, cfg.prefix),
    }
  }

  return {
    mod: 'lambda',
    silDesteklenir: false,
    oku: _oku,
    async yaz(ad, veri, etag) {
      if (etag) {
        // Koşullu okuma: dosya değiştiyse EtagUyusmazligi fırlar (Cognito modundaki korumanın eşdeğeri)
        await _oku(ad, etag)
      }
      const govde = JSON.stringify(veri, null, 2) + '\n'
      const imza = await istemci.imzala({ dosya: ad, islem: 'yaz', boyut: new TextEncoder().encode(govde).length })
      const yanit = await istemci.s3Istek(imza.url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
        body: govde,
      })
      if (!yanit.ok) throw new Error(`S3 yazma hatası (${yanit.status})`)
      return { etag: yanit.headers.get('ETag') ?? undefined, anahtar: s3Anahtar(ad, cfg.prefix) }
    },
    async bilgi(ad) {
      try {
        const sonuc = await _oku(ad)
        return {
          ad,
          anahtar: s3Anahtar(ad, cfg.prefix),
          varMi: sonuc !== null,
          boyut: sonuc?.boyut,
          sonDegisiklik: sonuc?.sonDegisiklik,
          etag: sonuc?.etag,
        }
      } catch {
        return { ad, anahtar: s3Anahtar(ad, cfg.prefix), varMi: false }
      }
    },
    async tumBilgiler(): Promise<DosyaBilgisi[]> {
      return Promise.all(Object.values(DOSYALAR).map((ad) => this.bilgi(ad)))
    },
    async liste() {
      const bilgiler = await Promise.all(Object.values(DOSYALAR).map((ad) => this.bilgi(ad)))
      return bilgiler
        .filter((b) => b.varMi)
        .map((b) => ({ anahtar: b.anahtar, boyut: b.boyut, sonDegisiklik: b.sonDegisiklik }))
    },
    async sil(_ad) {
      throw new Error(
        'Lambda modunda dosya silme kapalıdır (imzalama yalnızca okuma/yazma içindir). ' +
          'Silmek için AWS konsolunu kullanın veya Cognito moduna geçin.',
      )
    },
    async nesneSil(_anahtar) {
      throw new Error(
        'Lambda modunda nesne silme kapalıdır (presigned imza yalnızca okuma/yazma içindir). ' +
          'Süresi geçen yayınların görselleri için kovada bir S3 yaşam döngüsü kuralı tanımlayın ' +
          '(bkz. panel/README.md) ya da Cognito moduna geçin.',
      )
    },
  }
}
