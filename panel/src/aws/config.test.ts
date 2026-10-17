/** Yapılandırma ve yardımcılar — eksik .env durumunda anlaşılır hata vermeli. */
import { describe, expect, it } from 'vitest'

import { authModu, eksikDegiskenler, hataMesaji, normalizePrefix, panelConfig, s3Anahtar, saglayiciAnahtari, yerTutucuDegiskenler, yerTutucuMu } from './config'

const TAM = {
  VITE_AWS_REGION: 'eu-central-1',
  VITE_USER_POOL_ID: 'eu-central-1_ABC',
  VITE_USER_POOL_CLIENT_ID: 'client123',
  VITE_IDENTITY_POOL_ID: 'eu-central-1:0000-1111',
  VITE_BUCKET: 'yourkiosk-veri',
  VITE_PREFIX: 'kiosk',
}

describe('panelConfig', () => {
  it('eksik değişkenleri listeler ve açık hata verir', () => {
    expect(eksikDegiskenler({})).toHaveLength(5)
    expect(() => panelConfig({})).toThrow(/Eksik ortam değişkeni/)
    expect(eksikDegiskenler({ ...TAM, VITE_BUCKET: '  ' })).toEqual(['VITE_BUCKET'])
  })

  it('tam ortamda yapılandırmayı döner ve ön eki normalize eder', () => {
    const cfg = panelConfig(TAM)
    expect(cfg.bucket).toBe('yourkiosk-veri')
    expect(cfg.prefix).toBe('kiosk/')
    expect(cfg.authModu).toBe('cognito')
  })

  it('VITE_PREFIX boş olabilir (kova kökü)', () => {
    expect(panelConfig({ ...TAM, VITE_PREFIX: '' }).prefix).toBe('')
  })
})

describe('kimlik modu (bkz. MAALIYET.md)', () => {
  const LAMBDA = {
    VITE_AUTH_MODU: 'lambda',
    VITE_BUCKET: 'yourkiosk-veri',
    VITE_PREFIX: 'kiosk',
    VITE_API_URL: 'https://api.test/',
  }

  it('varsayılan mod cognito; tanınmayan değer hata verir', () => {
    expect(authModu({})).toBe('cognito')
    expect(authModu({ VITE_AUTH_MODU: 'COGNITO' })).toBe('cognito')
    expect(authModu({ VITE_AUTH_MODU: 'lambda' })).toBe('lambda')
    expect(() => authModu({ VITE_AUTH_MODU: 'basic' })).toThrow(/tanınmıyor/)
  })

  it('lambda modu Cognito değişkenlerini GEREKTİRMEZ', () => {
    expect(eksikDegiskenler(LAMBDA)).toEqual([])
    const cfg = panelConfig(LAMBDA)
    expect(cfg.authModu).toBe('lambda')
    expect(cfg.apiUrl).toBe('https://api.test')
    expect(cfg.userPoolId).toBe('')
  })

  it('lambda modunda API adresi eksikse uyarır', () => {
    expect(eksikDegiskenler({ ...LAMBDA, VITE_API_URL: '' })).toEqual(['VITE_API_URL'])
  })

  it('cognito modunda kova/pool değişkenleri eksikse uyarır', () => {
    expect(eksikDegiskenler({ ...LAMBDA, VITE_AUTH_MODU: 'cognito' })).toEqual([
      'VITE_AWS_REGION',
      'VITE_USER_POOL_ID',
      'VITE_USER_POOL_CLIENT_ID',
      'VITE_IDENTITY_POOL_ID',
    ])
  })

  it('örnek dosyadan kopyalanmış yer tutucuları yakalar', () => {
    expect(yerTutucuMu('eu-central-1_XXXXXXXXX')).toBe(true)
    expect(yerTutucuMu('XXXXXXXXXXXXXXXXXXXXXXXXXX')).toBe(true)
    expect(yerTutucuMu('eu-central-1:11111111-2222-3333-4444-000000000000')).toBe(true) // örnek dosyadaki
    expect(yerTutucuMu('eu-central-1:e0a1b2c3-4d5e-6f70-8192-a3b4c5d6e7f8')).toBe(false) // gerçek görünümlü
    expect(yerTutucuMu('eu-central-1_9f8e7d6c5b4a')).toBe(false)
    expect(yerTutucuMu('')).toBe(false)
    expect(yerTutucuMu('yourkiosk-veri', 'VITE_BUCKET')).toBe(false)

    const yerTutucu = yerTutucuDegiskenler({ ...TAM, VITE_USER_POOL_ID: 'eu-central-1_XXXXXXXXX' })
    expect(yerTutucu).toEqual(['VITE_USER_POOL_ID'])
    expect(yerTutucuDegiskenler(TAM)).toEqual([])
  })
})

describe('s3Anahtar / normalizePrefix', () => {
  it('ön eki tek biçime getirir', () => {
    expect(normalizePrefix('kiosk')).toBe('kiosk/')
    expect(normalizePrefix('/kiosk/')).toBe('kiosk/')
    expect(normalizePrefix('')).toBe('')
  })

  it('kova anahtarını üretir', () => {
    expect(s3Anahtar('ayarlar.json', 'kiosk/')).toBe('kiosk/ayarlar.json')
    expect(s3Anahtar('/ayarlar.json', '')).toBe('ayarlar.json')
  })

  it('Cognito sağlayıcı anahtarı', () => {
    expect(saglayiciAnahtari({ region: 'eu-central-1', userPoolId: 'eu-central-1_ABC' })).toBe(
      'cognito-idp.eu-central-1.amazonaws.com/eu-central-1_ABC',
    )
  })
})

describe('hataMesaji', () => {
  it('bilinen Cognito/AWS hatalarını Türkçeleştirir', () => {
    expect(hataMesaji({ code: 'NotAuthorizedException', message: 'x' })).toContain('şifre hatalı')
    expect(hataMesaji(new Error('AccessDenied: ...'))).toContain('IAM izni')
    expect(hataMesaji(new Error('NoSuchKey'))).toContain('bulunamadı')
  })

  it('bilinmeyen hatayı olduğu gibi geçirir', () => {
    expect(hataMesaji(new Error('tuhaf hata'))).toBe('tuhaf hata')
  })
})
