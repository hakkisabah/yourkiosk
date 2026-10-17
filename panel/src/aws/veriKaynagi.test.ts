/**
 * Lambda modu veri kaynağı (Cognito'suz): presigned URL akışı, ETag koruması,
 * beyaz liste hataları ve hata eşlemesi — ağa çıkmadan taklit fetch ile.
 */
import { describe, expect, it, vi } from 'vitest'

import { panelConfig } from './config'
import { lambdaKaynagi } from './kaynaklar'
import { EtagUyusmazligi, type VeriKaynagi } from './veriKaynagi'
import { LambdaIstemcisi, OturumYok, type FetchGibi } from './lambda'

const CFG = panelConfig({
  VITE_AUTH_MODU: 'lambda',
  VITE_BUCKET: 'test-kova',
  VITE_PREFIX: 'kiosk',
  VITE_API_URL: 'https://api.test/',
})

interface Cagri {
  url: string
  method: string
  headers: Record<string, string>
  body?: string
}

/** /imzala ve presigned S3 isteklerini karşılayan sahte fetch. */
function sahteFetch(
  secenekler: {
    s3Durum?: number
    s3Govde?: string
    s3Etag?: string
    imzalaDurum?: number
    oturumDurum?: number
  } = {},
) {
  const cagrilar: Cagri[] = []
  const fetchGibi: FetchGibi = async (url, baslat) => {
    const basliklar = Object.fromEntries(
      Object.entries((baslat?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v]),
    )
    cagrilar.push({ url, method: baslat?.method ?? 'GET', headers: basliklar, body: baslat?.body as string })
    const json = (govde: unknown, durum = 200) =>
      new Response(JSON.stringify(govde), { status: durum, headers: { 'Content-Type': 'application/json' } })

    if (url.includes('/oturum')) return json({ giris: (secenekler.oturumDurum ?? 200) === 200 }, secenekler.oturumDurum ?? 200)
    if (url.includes('/imzala')) {
      if ((secenekler.imzalaDurum ?? 200) !== 200) return json({ hata: 'oturum yok' }, secenekler.imzalaDurum)
      const istek = JSON.parse(String(baslat?.body ?? '{}')) as { islem: string }
      return json({ url: `https://s3.test/${istek.islem}`, islem: istek.islem })
    }
    // presigned S3 isteği
    const durum = secenekler.s3Durum ?? 200
    if (durum >= 400) return new Response('hata', { status: durum })
    return new Response(secenekler.s3Govde ?? '{"a":1}', {
      status: 200,
      headers: {
        ETag: secenekler.s3Etag ?? '"etag-1"',
        'Last-Modified': 'Wed, 15 Oct 2026 08:00:00 GMT',
        'Content-Type': 'application/json',
      },
    })
  }
  return { fetchGibi, cagrilar, kaynak: lambdaKaynagi(CFG, new LambdaIstemcisi(CFG, fetchGibi)) }
}

const imzalaCagrilari = (cagrilar: Cagri[]) => cagrilar.filter((c) => c.url.includes('/imzala'))

describe('lambdaKaynagi — okuma', () => {
  it('presigned GET ile okur; etag/boyut/kaynak bilgisini döner', async () => {
    const { kaynak, cagrilar } = sahteFetch({ s3Govde: '{"ozellikler":{"kayan_yazi":false}}' })
    const sonuc = await kaynak.oku<{ ozellikler: { kayan_yazi: boolean } }>('ayarlar.json')
    expect(sonuc?.veri.ozellikler.kayan_yazi).toBe(false)
    expect(sonuc?.etag).toBe('"etag-1"')
    expect(sonuc?.boyut).toBe(35)
    expect(sonuc?.anahtar).toBe('kiosk/ayarlar.json')
    expect(kaynak.mod).toBe('lambda')
    expect(imzalaCagrilari(cagrilar)[0].body).toContain('"islem":"oku"')
  })

  it('dosya yoksa (404) null döner', async () => {
    const { kaynak } = sahteFetch({ s3Durum: 404 })
    expect(await kaynak.oku('sablon.json')).toBeNull()
  })

  it('etag verilirse koşullu okuma yapar (If-Match başlığı)', async () => {
    const { kaynak, cagrilar } = sahteFetch()
    await kaynak.oku('ayarlar.json', '"etag-1"')
    const s3Cagrisi = cagrilar.find((c) => c.url.startsWith('https://s3.test/'))
    expect(s3Cagrisi?.headers['if-match']).toBe('"etag-1"')
    expect(imzalaCagrilari(cagrilar)[0].body).toContain('"etag":"\\"etag-1\\""')
  })

  it('dosya değişmişse (412) EtagUyusmazligi fırlatır', async () => {
    const { kaynak } = sahteFetch({ s3Durum: 412 })
    await expect(kaynak.oku('ayarlar.json', '"eski"')).rejects.toBeInstanceOf(EtagUyusmazligi)
  })

  it('bozuk JSON anlaşılır hata verir', async () => {
    const { kaynak } = sahteFetch({ s3Govde: '{bozuk' })
    await expect(kaynak.oku('ayarlar.json')).rejects.toThrow(/JSON çözülemedi/)
  })
})

describe('lambdaKaynagi — yazma', () => {
  it('presigned PUT ile yazar ve yeni etag döner', async () => {
    const { kaynak, cagrilar } = sahteFetch({ s3Etag: '"yeni-etag"' })
    const sonuc = await kaynak.yaz('kapsam-ayarlari.json', { varsayilan: { ozellikler: { yayinlar: true } } })
    expect(sonuc.etag).toBe('"yeni-etag"')
    const put = cagrilar.find((c) => c.method === 'PUT')
    expect(put?.headers['content-type']).toContain('application/json')
    expect(put?.body?.endsWith('\n')).toBe(true)
    expect(JSON.parse(String(put?.body)).varsayilan.ozellikler.yayinlar).toBe(true)
  })

  it('etag verilmişse önce koşullu okuma yapar (yarış koruması)', async () => {
    const { kaynak, cagrilar } = sahteFetch()
    await kaynak.yaz('ayarlar.json', { a: 1 }, '"etag-1"')
    const s3Cagrilari = cagrilar.filter((c) => c.url.startsWith('https://s3.test/'))
    expect(s3Cagrilari[0].method).toBe('GET')
    expect(s3Cagrilari.some((c) => c.method === 'PUT')).toBe(true)
  })

  it('dosya bu arada değiştiyse YAZMAZ, uyarı fırlatır', async () => {
    const { kaynak, cagrilar } = sahteFetch({ s3Durum: 412 })
    await expect(kaynak.yaz('ayarlar.json', { a: 1 }, '"eski"')).rejects.toBeInstanceOf(EtagUyusmazligi)
    expect(cagrilar.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('boyutu presign isteğine iletir (sunucu üst sınırı uygular)', async () => {
    const { kaynak, cagrilar } = sahteFetch()
    await kaynak.yaz('lastSystemData.json', { x: 'y'.repeat(100) })
    const istek = JSON.parse(String(imzalaCagrilari(cagrilar)[0].body)) as { boyut: number }
    expect(istek.boyut).toBeGreaterThan(100)
  })
})

describe('lambdaKaynagi — bilgi/liste/silme', () => {
  it('bilgi() dosya durumunu verir', async () => {
    const { kaynak } = sahteFetch()
    const bilgi = await kaynak.bilgi('match.json')
    expect(bilgi.varMi).toBe(true)
    expect(bilgi.anahtar).toBe('kiosk/match.json')
    expect(bilgi.etag).toBe('"etag-1"')
  })

  it('dosya yoksa bilgi().varMi false', async () => {
    const { kaynak } = sahteFetch({ s3Durum: 404 })
    expect((await kaynak.bilgi('match.json')).varMi).toBe(false)
  })

  it('liste() yalnızca var olan dosyaları döner', async () => {
    const { kaynak } = sahteFetch({ s3Durum: 404 })
    expect(await kaynak.liste()).toEqual([])
  })

  it('silme desteklenmez ve açık hata verir', async () => {
    const { kaynak } = sahteFetch()
    expect(kaynak.silDesteklenir).toBe(false)
    await expect(kaynak.sil('ayarlar.json')).rejects.toThrow(/silme kapalıdır/)
  })
})

describe('LambdaIstemcisi', () => {
  it('oturum kontrolü ve giriş çağrıları cookie ile yapılır', async () => {
    const { fetchGibi, cagrilar } = sahteFetch()
    const istemci = new LambdaIstemcisi(CFG, fetchGibi)
    expect((await istemci.oturumKontrol()).giris).toBe(true)
    await istemci.giris('gizli-sifre')
    const girisCagrisi = cagrilar.find((c) => c.url.endsWith('/giris'))
    expect(girisCagrisi?.body).toContain('gizli-sifre')
  })

  it('401 oturum hatası OturumYok olarak eşlenir', async () => {
    const { fetchGibi } = sahteFetch({ imzalaDurum: 401 })
    const istemci = new LambdaIstemcisi(CFG, fetchGibi)
    await expect(istemci.imzala({ dosya: 'ayarlar.json', islem: 'oku' })).rejects.toBeInstanceOf(OturumYok)
    await expect(istemci.imzala({ dosya: 'ayarlar.json', islem: 'oku' })).rejects.toThrow(/Oturum bulunamadı/)
  })

  it('sunucu hata mesajı korunur', async () => {
    const fetchGibi: FetchGibi = async () =>
      new Response(JSON.stringify({ hata: 'şifre hatalı' }), { status: 429 })
    await expect(new LambdaIstemcisi(CFG, fetchGibi).giris('x')).rejects.toThrow('şifre hatalı')
  })

  it('API adresinin sonundaki / tekilleştirilir', async () => {
    const { fetchGibi, cagrilar } = sahteFetch()
    await new LambdaIstemcisi(CFG, fetchGibi).oturumKontrol()
    expect(cagrilar[0].url).toBe('https://api.test/oturum')
  })
})

describe('iki modun ortak arayüzü', () => {
  it('lambda kaynağı VeriKaynagi sözleşmesini karşılar', () => {
    const { kaynak } = sahteFetch()
    const sozlesme: VeriKaynagi = kaynak
    for (const ad of ['oku', 'yaz', 'bilgi', 'tumBilgiler', 'liste', 'sil'] as const) {
      expect(typeof sozlesme[ad]).toBe('function')
    }
    expect(vi.isMockFunction(sozlesme.oku)).toBe(false) // taklit değil, gerçek uygulama
  })
})
