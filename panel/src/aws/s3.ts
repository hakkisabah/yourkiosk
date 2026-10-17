/**
 * S3 veri katmanı — kiosk dosyaları doğrudan S3'ten okunur/yazılır.
 *
 * Kimlik: Cognito Identity Pool'dan alınan geçici AWS anahtarları (tarayıcıda
 * uzun ömürlü anahtar YOK). Yazma öncesi ETag karşılaştırılır: dosya bu arada
 * başkası tarafından değiştiyse yazma yapılmaz, uyarı döner (veri kaybını önler).
 */
import {
  DeleteObjectCommand,
  GetObjectCommand,
  HeadObjectCommand,
  ListObjectsV2Command,
  PutObjectCommand,
  S3Client,
} from '@aws-sdk/client-s3'
import { fromCognitoIdentityPool } from '@aws-sdk/credential-provider-cognito-identity'
import { DOSYALAR, s3Anahtar, saglayiciAnahtari, type PanelConfig } from './config'

export interface OkumaSonucu<T> {
  veri: T
  etag?: string
  boyut?: number
  sonDegisiklik?: string
  anahtar: string
}

export interface YazmaSonucu {
  etag?: string
  uyari?: string
  anahtar: string
}

export interface DosyaBilgisi {
  ad: string
  anahtar: string
  varMi: boolean
  boyut?: number
  sonDegisiklik?: string
  etag?: string
}

/** ID token ile S3 istemcisi kurar (geçici kimlik bilgileriyle). */
export function istemci(cfg: PanelConfig, idToken: string): S3Client {
  return new S3Client({
    region: cfg.region,
    credentials: fromCognitoIdentityPool({
      clientConfig: { region: cfg.region },
      identityPoolId: cfg.identityPoolId,
      logins: { [saglayiciAnahtari(cfg)]: idToken },
    }),
  })
}

const _metne = async (govde: unknown): Promise<string> => {
  if (!govde) return ''
  const bayt = await (govde as { transformToByteArray: () => Promise<Uint8Array> }).transformToByteArray()
  return new TextDecoder('utf-8').decode(bayt)
}

/** JSON dosyasını okur; dosya yoksa `null` döner (yeni kurulum senaryosu). */
export async function jsonOku<T>(s3: S3Client, cfg: PanelConfig, ad: string): Promise<OkumaSonucu<T> | null> {
  const anahtar = s3Anahtar(ad, cfg.prefix)
  try {
    const yanit = await s3.send(new GetObjectCommand({ Bucket: cfg.bucket, Key: anahtar }))
    const metin = await _metne(yanit.Body)
    return {
      veri: JSON.parse(metin) as T,
      etag: yanit.ETag,
      boyut: yanit.ContentLength,
      sonDegisiklik: yanit.LastModified?.toISOString(),
      anahtar,
    }
  } catch (hata) {
    const ad2 = (hata as { name?: string })?.name ?? ''
    if (ad2 === 'NoSuchKey' || ad2 === 'NotFound') return null
    throw hata
  }
}

/**
 * JSON dosyasını yazar. `beklenenEtag` verilmişse ve dosya değişmişse yazmaz.
 * (Kiosk ile aynı biçim: okunabilir JSON + son satırbaşı.)
 */
export async function jsonYaz(
  s3: S3Client,
  cfg: PanelConfig,
  ad: string,
  veri: unknown,
  beklenenEtag?: string,
): Promise<YazmaSonucu> {
  const anahtar = s3Anahtar(ad, cfg.prefix)
  if (beklenenEtag) {
    const guncel = await dosyaBilgisi(s3, cfg, ad)
    if (guncel.varMi && guncel.etag && guncel.etag !== beklenenEtag) {
      return {
        anahtar,
        uyari:
          'Dosya siz düzenlerken değişmiş (başka bir panel/otomasyon yazmış olabilir). ' +
          'Kaydetmek için sayfayı yenileyip değişiklikleri yeniden uygulayın.',
      }
    }
  }
  const govde = JSON.stringify(veri, null, 2) + '\n'
  const yanit = await s3.send(
    new PutObjectCommand({
      Bucket: cfg.bucket,
      Key: anahtar,
      Body: govde,
      ContentType: 'application/json; charset=utf-8',
      CacheControl: 'no-store',
    }),
  )
  return { etag: yanit.ETag, anahtar }
}

/** Dosyanın kovadaki durumu (boyut/tarih) — panel "Durum" ekranı için. */
export async function dosyaBilgisi(s3: S3Client, cfg: PanelConfig, ad: string): Promise<DosyaBilgisi> {
  const anahtar = s3Anahtar(ad, cfg.prefix)
  try {
    const yanit = await s3.send(new HeadObjectCommand({ Bucket: cfg.bucket, Key: anahtar }))
    return {
      ad,
      anahtar,
      varMi: true,
      boyut: yanit.ContentLength,
      sonDegisiklik: yanit.LastModified?.toISOString(),
      etag: yanit.ETag,
    }
  } catch {
    return { ad, anahtar, varMi: false }
  }
}

/** Tanımlı tüm kiosk dosyalarının durumu. */
export async function tumDosyaBilgileri(s3: S3Client, cfg: PanelConfig): Promise<DosyaBilgisi[]> {
  return Promise.all(Object.values(DOSYALAR).map((ad) => dosyaBilgisi(s3, cfg, ad)))
}

/** Ön ek altındaki tüm nesneleri listeler (öksüz dosya/ek yayınları görmek için). */
export async function listele(s3: S3Client, cfg: PanelConfig): Promise<Array<{ anahtar: string; boyut?: number; sonDegisiklik?: string }>> {
  const yanit = await s3.send(new ListObjectsV2Command({ Bucket: cfg.bucket, Prefix: cfg.prefix }))
  return (yanit.Contents ?? []).map((o) => ({
    anahtar: o.Key ?? '',
    boyut: o.Size,
    sonDegisiklik: o.LastModified?.toISOString(),
  }))
}

export async function sil(s3: S3Client, cfg: PanelConfig, ad: string): Promise<void> {
  await s3.send(new DeleteObjectCommand({ Bucket: cfg.bucket, Key: s3Anahtar(ad, cfg.prefix) }))
}

/**
 * Ön ekin DIŞINDAKİ ekleri (ör. yayın görselleri) tam anahtarıyla siler.
 *
 * Güvenlik: yalnızca kendi ön ekimiz altındaki anahtarlar silinebilir; kök nesneler
 * (kiosk veri dosyaları) bu yoldan ASLA silinemez — kaza ile veri kaybını önler.
 * Ayrıca anahtar `..` içeremez.
 */
export async function nesneSil(s3: S3Client, cfg: PanelConfig, anahtar: string): Promise<void> {
  const temiz = String(anahtar ?? '').replace(/^\/+/, '')
  if (!temiz || temiz.includes('..')) {
    throw new Error(`geçersiz nesne anahtarı: ${anahtar}`)
  }
  if (cfg.prefix && !temiz.startsWith(cfg.prefix)) {
    throw new Error(`önek dışındaki nesne silinemez (${cfg.prefix} ile başlamalı): ${temiz}`)
  }
  await s3.send(new DeleteObjectCommand({ Bucket: cfg.bucket, Key: temiz }))
}
