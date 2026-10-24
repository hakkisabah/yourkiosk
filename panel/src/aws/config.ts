/**
 * Panel yapılandırması — tüm değerler derleme zamanındaki `.env.local` dosyasından.
 * Kimlik bilgisi (şifre/anahtar) TUTULMAZ; S3 erişimi Cognito üzerinden alınan
 * GEÇİCİ AWS anahtarlarıyla yapılır (kiosk deposunda gizli anahtar yoktur).
 */

export interface PanelConfig {
  region: string
  userPoolId: string
  userPoolClientId: string
  identityPoolId: string
  bucket: string
  prefix: string
  /** Kimlik/veri erişim modu (bkz. MAALIYET.md) */
  authModu: AuthModu
  /** Lambda modunda panel API adresi (Function URL) */
  apiUrl: string
}

export type HamEnv = Record<string, string | undefined>

/** Kimlik/veri erişim modu: Cognito (varsayılan) veya Lambda+cookie (bkz. MAALIYET.md). */
export type AuthModu = 'cognito' | 'lambda'

/** Kiosk ile panelin paylaştığı dosya adları (aynı S3 ön eki altında). */
export const DOSYALAR = {
  ayarlar: 'ayarlar.json',
  kapsam: 'kapsam-ayarlari.json',
  sistem: 'lastSystemData.json',
  durum: 'durum.json',
  sablon: 'sablon.json',
  match: 'match.json',
  lastupdate: 'lastupdate.json',
  makine: 'makinebilgileri.json',
} as const

export type DosyaAdi = (typeof DOSYALAR)[keyof typeof DOSYALAR]

const GEREKLI_COGNITO: Array<[alan: keyof PanelConfig, degisken: string]> = [
  ['region', 'VITE_AWS_REGION'],
  ['userPoolId', 'VITE_USER_POOL_ID'],
  ['userPoolClientId', 'VITE_USER_POOL_CLIENT_ID'],
  ['identityPoolId', 'VITE_IDENTITY_POOL_ID'],
  ['bucket', 'VITE_BUCKET'],
]

const GEREKLI_LAMBDA: Array<[alan: keyof PanelConfig, degisken: string]> = [
  ['bucket', 'VITE_BUCKET'],
  ['apiUrl', 'VITE_API_URL'],
]

/** Seçili moda göre zorunlu ortam değişkenleri. */
export function gerekliDegiskenler(mod: AuthModu): Array<[alan: keyof PanelConfig, degisken: string]> {
  return mod === 'lambda' ? GEREKLI_LAMBDA : GEREKLI_COGNITO
}

/** Ortamdan modu okur (tanınmayan değer → cognito). */
export function authModu(env: HamEnv = import.meta.env): AuthModu {
  const ham = String(env.VITE_AUTH_MODU ?? '').trim().toLowerCase()
  if (ham === 'lambda') return 'lambda'
  if (ham && ham !== 'cognito') {
    throw new Error(`VITE_AUTH_MODU tanınmıyor: ${ham} (cognito | lambda olmalı)`)
  }
  return 'cognito'
}

/** Eksik ortam değişkenlerini bulur (panelde anlaşılır bir hata göstermek için). */
export function eksikDegiskenler(env: HamEnv): string[] {
  const mod = authModu(env)
  return gerekliDegiskenler(mod)
    .filter(([, degisken]) => !String(env[degisken] ?? '').trim())
    .map(([, degisken]) => degisken)
}

/** Örnek dosyadan kopyalanmış yer tutucu değerler (gerçek kurulum yapılmamış demektir). */
export function yerTutucuMu(deger: string, degisken = ''): boolean {
  const d = String(deger ?? '').trim()
  if (!d) return false
  if (/X{4,}/i.test(d)) return true // XXXXXXXXX
  if (d.includes('1234567890')) return true

  // Identity Pool kimliği: <bölge>:<uuid>. Örnek dosyadaki gibi "desenli" uuid'ler
  // (tüm basamakları aynı olan grup) yer tutucudur; gerçek uuid'ler rastgeledir.
  const eslesme = d.match(/^[\w-]+:([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})$/i)
  if (eslesme) {
    const tekrarli = (grup: string): boolean => new Set(grup.toLowerCase()).size === 1
    const [, g1, g2, , , g5] = eslesme
    if (tekrarli(g1) || tekrarli(g2) || tekrarli(g5)) return true
  }
  if (degisken === 'VITE_BUCKET' && d === 'yourkiosk-veri') return false // gerçekçi bir ad olabilir
  return false
}

/** Yer tutucu kalan değişkenler (panel "değerleri doldurun" uyarısı gösterir). */
export function yerTutucuDegiskenler(env: HamEnv): string[] {
  const mod = authModu(env)
  return gerekliDegiskenler(mod)
    .filter(([, degisken]) => yerTutucuMu(String(env[degisken] ?? ''), degisken))
    .map(([, degisken]) => degisken)
}

/** Ortam değişkenlerini doğrulayıp yapılandırmayı döner; eksikse açık hata verir. */
export function panelConfig(env: HamEnv = import.meta.env): PanelConfig {
  const mod = authModu(env)
  const eksik = eksikDegiskenler(env)
  if (eksik.length) {
    throw new Error(
      `Eksik ortam değişkeni (${mod} modu): ${eksik.join(', ')}. ` +
        'Panel kökünde .env.ornek dosyasını .env.local olarak kopyalayıp doldurun.',
    )
  }
  return {
    region: String(env.VITE_AWS_REGION ?? '').trim(),
    userPoolId: String(env.VITE_USER_POOL_ID ?? '').trim(),
    userPoolClientId: String(env.VITE_USER_POOL_CLIENT_ID ?? '').trim(),
    identityPoolId: String(env.VITE_IDENTITY_POOL_ID ?? '').trim(),
    bucket: String(env.VITE_BUCKET).trim(),
    prefix: normalizePrefix(String(env.VITE_PREFIX ?? '')),
    authModu: mod,
    apiUrl: String(env.VITE_API_URL ?? '').trim().replace(/\/+$/, ''),
  }
}

/** Kova içindeki anahtar: "kiosk/" + "ayarlar.json" → "kiosk/ayarlar.json". */
export function s3Anahtar(ad: string, prefix = ''): string {
  const p = normalizePrefix(prefix)
  const temiz = ad.replace(/^\/+/, '')
  return `${p}${temiz}`
}

/** Ön eki tek biçime getirir: ya boş ya da sonu "/" ile biten. */
export function normalizePrefix(prefix: string): string {
  const p = prefix.trim().replace(/^\/+/, '')
  if (!p) return ''
  return p.endsWith('/') ? p : `${p}/`
}

/** Cognito Identity Pool'a verilecek oturum açma anahtarı (tek yönetici kullanıcı). */
export function saglayiciAnahtari(cfg: Pick<PanelConfig, 'region' | 'userPoolId'>): string {
  return `cognito-idp.${cfg.region}.amazonaws.com/${cfg.userPoolId}`
}

/** Cognito hatalarını panelde okunur Türkçe mesaja çevirir. */
export function hataMesaji(hata: unknown): string {
  const ham = hata instanceof Error ? hata.message : String(hata)
  const kod = (hata as { code?: string })?.code ?? ''
  const tablo: Record<string, string> = {
    NotAuthorizedException: 'E-posta veya şifre hatalı.',
    UserNotFoundException: 'Kullanıcı bulunamadı (Cognito’da oluşturulmuş mu?).',
    UserNotConfirmedException: 'Kullanıcı doğrulanmamış; Cognito konsolundan onaylayın.',
    PasswordResetRequiredException: 'Şifre sıfırlama gerekiyor.',
    InvalidParameterException: 'Eksik/geçersiz alan: e-posta ve şifre gerekli.',
    NetworkError: 'Ağa ulaşılamadı (bölge/Cognito adresi doğru mu?).',
    AccessDenied: 'Bu işlem için IAM izni yok (infra/iam-policy.json dosyasına bakın).',
    AccessDeniedException: 'Bu işlem için IAM izni yok (infra/iam-policy.json dosyasına bakın).',
    NoSuchKey: 'Dosya kovada bulunamadı (ön ek/kovadaki yol doğru mu?).',
    NoSuchBucket: 'Kova bulunamadı.',
  }
  if (kod && tablo[kod]) return tablo[kod]
  for (const [anahtar, mesaj] of Object.entries(tablo)) if (ham.includes(anahtar)) return mesaj
  return ham
}
