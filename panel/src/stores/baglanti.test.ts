/**
 * Bağlantı/oturum akışı testleri — "beyaz ekran" yerine ANLAŞILIR DURUM üretmeli.
 *
 * Kapsanan senaryolar:
 *   • .env.local yok  → kurulum uyarısı, AWS'ye HİÇ istek atılmaz
 *   • yer tutucu değerler (örnek dosyadan kopyalanmış) → aynı uyarı + hangi değişkenler
 *   • geçerli cognito yapılandırması, oturum yok → giriş ekranı akışı, kaynak yok
 *   • geçerli lambda yapılandırması → cookie oturumu kontrol edilir, kaynak hazır
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

import { rotaIzni } from '@/router/kurallar'
import { useBaglanti } from './baglanti'

const COGNITO = {
  VITE_AUTH_MODU: 'cognito',
  VITE_AWS_REGION: 'eu-central-1',
  VITE_USER_POOL_ID: 'eu-central-1_AbCdEfGhI',
  VITE_USER_POOL_CLIENT_ID: '1a2b3c4d5e6f7g8h9i0j',
  VITE_IDENTITY_POOL_ID: 'eu-central-1:e0a1b2c3-4d5e-6f70-8192-a3b4c5d6e7f8',
  VITE_BUCKET: 'yourkiosk-veri',
  VITE_PREFIX: 'kiosk/',
}

const LAMBDA = {
  VITE_AUTH_MODU: 'lambda',
  VITE_BUCKET: 'yourkiosk-veri',
  VITE_PREFIX: 'kiosk/',
  VITE_API_URL: 'https://api.test',
}

/** import.meta.env'i verilen değerlerle değiştirir (Vite stubEnv). */
function ortamiAyarla(degerler: Record<string, string>): void {
  for (const anahtar of [
    'VITE_AUTH_MODU',
    'VITE_AWS_REGION',
    'VITE_USER_POOL_ID',
    'VITE_USER_POOL_CLIENT_ID',
    'VITE_IDENTITY_POOL_ID',
    'VITE_BUCKET',
    'VITE_PREFIX',
    'VITE_API_URL',
  ]) {
    vi.stubEnv(anahtar, degerler[anahtar] ?? '')
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('yapılandırma eksikse', () => {
  it('kurulum uyarısı verir, hata fırlatmaz ve AWS isteği yapmaz', async () => {
    ortamiAyarla({})
    const fetchTaklit = vi.fn()
    vi.stubGlobal('fetch', fetchTaklit)

    const baglanti = useBaglanti()
    await baglanti.baslat()

    expect(baglanti.hazir).toBe(true)
    expect(baglanti.yapilandirmaHatasi).toContain('eksik:')
    expect(baglanti.yapilandirma).toBeNull()
    expect(baglanti.kaynak).toBeNull()
    expect(fetchTaklit).not.toHaveBeenCalled()
  })

  it('yer tutucu değerleri ayrı ayrı bildirir', async () => {
    ortamiAyarla({
      ...COGNITO,
      VITE_USER_POOL_ID: 'eu-central-1_XXXXXXXXX',
      VITE_USER_POOL_CLIENT_ID: 'XXXXXXXXXXXXXXXXXXXXXXXXXX',
    })
    const baglanti = useBaglanti()
    await baglanti.baslat()

    expect(baglanti.yerTutucular).toEqual(['VITE_USER_POOL_ID', 'VITE_USER_POOL_CLIENT_ID'])
    expect(baglanti.yapilandirmaHatasi).toContain('yer tutucu')
    expect(baglanti.kaynak).toBeNull()
  })
})

describe('geçerli cognito yapılandırması', () => {
  it('oturum yoksa kaynak oluşturulmaz (giriş ekranı akışı)', async () => {
    ortamiAyarla(COGNITO)
    const baglanti = useBaglanti()
    await baglanti.baslat()

    expect(baglanti.yapilandirmaHatasi).toBeNull()
    expect(baglanti.mod).toBe('cognito')
    expect(baglanti.girisYapildi).toBe(false)
    expect(baglanti.kaynak).toBeNull()
  })
})

describe('geçerli lambda yapılandırması', () => {
  it('cookie oturumu varsa kaynak hazır olur', async () => {
    ortamiAyarla(LAMBDA)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ giris: true }), { status: 200 })))

    const baglanti = useBaglanti()
    await baglanti.baslat()

    expect(baglanti.mod).toBe('lambda')
    expect(baglanti.yapilandirmaHatasi).toBeNull()
    expect(baglanti.girisYapildi).toBe(true)
    expect(baglanti.kaynak?.mod).toBe('lambda')
  })

  it('cookie oturumu yoksa giriş gerekir', async () => {
    ortamiAyarla(LAMBDA)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ giris: false }), { status: 200 })))

    const baglanti = useBaglanti()
    await baglanti.baslat()

    expect(baglanti.girisYapildi).toBe(false)
    expect(baglanti.kaynak).toBeNull()
  })
})

describe('rota izinleri (beyaz ekran yerine yönlendirme)', () => {
  const durum = (kismi: Partial<{ hazir: boolean; yapilandirmaHatasi: string | null; girisYapildi: boolean }> = {}) => ({
    hazir: true,
    yapilandirmaHatasi: null,
    girisYapildi: false,
    ...kismi,
  })

  it('hazır değilken bekler (yönlendirme yok)', () => {
    expect(rotaIzni({ name: 'durum' }, durum({ hazir: false }))).toBe(true)
  })

  it('yapılandırma hatasında kurulum ekranına gönderir', () => {
    expect(rotaIzni({ name: 'durum' }, durum({ yapilandirmaHatasi: 'eksik: VITE_BUCKET' }))).toEqual({ name: 'kurulum' })
    expect(rotaIzni({ name: 'kurulum' }, durum({ yapilandirmaHatasi: 'x' }))).toBe(true)
  })

  it('giriş yoksa giriş ekranına gönderir', () => {
    expect(rotaIzni({ name: 'durum' }, durum())).toEqual({ name: 'giris' })
    expect(rotaIzni({ name: 'giris', meta: { genel: true } }, durum())).toBe(true)
    expect(rotaIzni({ name: 'kurulum', meta: { genel: true } }, durum())).toBe(true)
  })

  it('giriş varsa giriş ekranından panele döner', () => {
    expect(rotaIzni({ name: 'giris', meta: { genel: true } }, durum({ girisYapildi: true }))).toEqual({ name: 'durum' })
    expect(rotaIzni({ name: 'durum' }, durum({ girisYapildi: true }))).toBe(true)
  })
})
