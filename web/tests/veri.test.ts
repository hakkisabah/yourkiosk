/**
 * Veri kaynağı + önbellek testleri (tarayıcı sürümü).
 *
 * Kritik sözleşmeler (Qt ile aynı):
 *  • `lastupdate` damgası değişmediyse büyük veri dosyası AĞDAN ÇEKİLMEZ,
 *  • damga değiştiyse yeniden alınır,
 *  • ayarlar dosyaları her zaman yerel kaynaktan okunur,
 *  • görseller bir kez indirilir, sonra önbellekten gelir.
 */
import { describe, expect, it, vi } from 'vitest'

import { Ayarlar, kapsamCoz } from '@/veri/ayarlar'
import { ayarOnbellegiTemizle, parametreleriOku, VeriKaynagi } from '@/veri/kaynak'
import { Onbellek, type OnbellekDeposu, type Yanit } from '@/veri/onbellek'
import { aktifYayinlar, yayinAktifMi, yayinAdresi, yayinSirasi, yayinSuresiMs } from '@/veri/yayin'

// ------------------------------------------------------------------ sahte depo
class SahteDepo implements OnbellekDeposu {
  kayitlar = new Map<string, Yanit>()
  async match(sorgu: string): Promise<Yanit | undefined> {
    return this.kayitlar.get(sorgu)
  }
  async put(sorgu: string, yanit: Yanit): Promise<void> {
    // gövdeyi tüketip sakla (gerçek Cache gibi davranır)
    const basliklar = new Map<string, string>()
    for (const ad of ['content-type', 'x-damga', 'x-sha256', 'x-url', 'x-alindi', 'x-son-gosterim', 'x-gosterim']) {
      const deger = yanit.headers.get(ad)
      if (deger !== null) basliklar.set(ad, deger)
    }
    const govde = await yanit.arrayBuffer()
    this.kayitlar.set(sorgu, {
      headers: { get: (ad: string) => basliklar.get(ad.toLowerCase()) ?? null },
      arrayBuffer: async () => govde,
      text: async () => new TextDecoder().decode(govde),
      ok: true,
      status: 200,
    })
  }
  async delete(sorgu: string): Promise<boolean> {
    return this.kayitlar.delete(sorgu)
  }
  async keys(): Promise<readonly string[]> {
    return [...this.kayitlar.keys()]
  }
}

const jsonYanit = (veri: unknown) =>
  new Response(JSON.stringify(veri), { headers: { 'Content-Type': 'application/json' } }) as unknown as Response

function sahteDepo(): { onbellek: Onbellek; depo: SahteDepo } {
  const depo = new SahteDepo()
  return { onbellek: new Onbellek(2, depo), depo }
}

// ------------------------------------------------------------------ parametreler
describe('parametreleriOku', () => {
  it('cihaz kimliğini ve veri modunu okur', () => {
    const s = parametreleriOku('?clientID=CIHAZ-1&veri=https&taban=https://sunucu/veri')
    expect(s.clientID).toBe('CIHAZ-1')
    expect(s.veri).toBe('https')
    expect(s.taban).toBe('https://sunucu/veri')
  })

  it('varsayılanlar: yerel mod, boş kimlik', () => {
    expect(parametreleriOku('')).toEqual({ clientID: '', veri: 'yerel', taban: '', yerlesim: undefined })
  })

  it('tanınmayan veri modunu yerel kabul eder', () => {
    expect(parametreleriOku('?veri=abc').veri).toBe('yerel')
  })

  it('yerleşim ölçeğini yalnızca sayıysa uygular', () => {
    expect(parametreleriOku('?yerlesim=0.5').yerlesim).toBe(0.5)
    expect(parametreleriOku('?yerlesim=abc').yerlesim).toBeUndefined()
  })
})

// ------------------------------------------------------------------ veri kaynağı
describe('VeriKaynagi — lastupdate ile önbellek', () => {
  const veri = { Nobetler: { T20261015: {} }, Yayinlar: {} }

  function kaynak(depo: SahteDepo, govdeler: Record<string, unknown>) {
    const cagrilar: string[] = []
    const getir = vi.fn(async (adres: string) => {
      cagrilar.push(String(adres))
      const ad = String(adres).split('/').pop() ?? ''
      if (!(ad in govdeler)) return new Response('yok', { status: 404 })
      return jsonYanit(govdeler[ad])
    }) as unknown as typeof fetch
    const onbellek = new Onbellek(2, depo)
    return {
      kaynak: new VeriKaynagi({ secenekler: { clientID: 'C1', veri: 'yerel', taban: '' }, onbellek, getir }),
      cagrilar,
    }
  }

  it('damga değişmediyse büyük dosya ağdan çekilmez', async () => {
    const depo = new SahteDepo()
    const { kaynak: k, cagrilar } = kaynak(depo, { 'lastupdate.json': { lastupdate: 'D1' }, 'lastSystemData.json': veri })

    expect(await k.sistemVerisi()).toEqual(veri)
    expect(cagrilar.filter((u) => u.includes('lastSystemData')).length).toBe(1)

    // ikinci tur: aynı damga → önbellekten
    expect(await k.sistemVerisi()).toEqual(veri)
    expect(cagrilar.filter((u) => u.includes('lastSystemData')).length).toBe(1)
    expect(cagrilar.filter((u) => u.includes('lastupdate')).length).toBe(2)
  })

  it('damga değiştiyse veriyi yeniden alır ve yeni damgayı saklar', async () => {
    const depo = new SahteDepo()
    const govdeler: Record<string, unknown> = { 'lastupdate.json': { lastupdate: 'D1' }, 'lastSystemData.json': veri }
    const { kaynak: k, cagrilar } = kaynak(depo, govdeler)

    await k.sistemVerisi()
    govdeler['lastupdate.json'] = { lastupdate: 'D2' }
    await k.sistemVerisi()

    expect(cagrilar.filter((u) => u.includes('lastSystemData')).length).toBe(2)
    // damga kaydı: anahtar geçerli bir http(s) adresidir (Cache Storage kuralı)
    const anahtarlar = await depo.keys()
    const meta = anahtarlar.find((a) => a.includes('__onbellek/meta/lastupdate'))
    expect(meta).toBeDefined()
    expect(String(meta)).toMatch(/^https?:\/\//)
  })

  it('https modunda büyük veri tabandan, ayarlar yerelden okunur', async () => {
    const depo = new SahteDepo()
    const cagrilar: string[] = []
    const getir = vi.fn(async (adres: string) => {
      cagrilar.push(String(adres))
      if (String(adres).endsWith('lastupdate.json')) return jsonYanit({ lastupdate: 'D1' })
      if (String(adres).endsWith('lastSystemData.json')) return jsonYanit(veri)
      if (String(adres).endsWith('ayarlar.json')) return jsonYanit({ varsayilan: { ozellikler: { yayinlar: false } } })
      return new Response('yok', { status: 404 })
    }) as unknown as typeof fetch
    const k = new VeriKaynagi({
      secenekler: { clientID: 'C1', veri: 'https', taban: 'https://sunucu/veri' },
      onbellek: new Onbellek(2, depo),
      getir,
      yerelTaban: 'http://127.0.0.1:8090',
    })

    await k.sistemVerisi()
    await k.ayarBelgesi('ayarlar.json')

    expect(cagrilar.some((u) => u.startsWith('https://sunucu/veri/lastSystemData.json'))).toBe(true)
    // ayarlar da YAYINDAN gelir (panel → cihaz); yerel kopya yalnız çevrimdışı yedeği
    expect(cagrilar.some((u) => u.startsWith('https://sunucu/veri/ayarlar.json'))).toBe(true)
  })

  it('https modunda uzak ayarlar okunamazsa yerel dosyaya düşer (çevrimdışı)', async () => {
    ayarOnbellegiTemizle()
    const depo = new SahteDepo()
    const getir = vi.fn(async (adres: string) => {
      if (String(adres).startsWith('https://sunucu/veri/ayarlar.json')) return new Response('yok', { status: 403 })
      if (String(adres).endsWith('/ayarlar.json')) return jsonYanit({ veri: { kaynak: 'dosya' } })
      return new Response('yok', { status: 404 })
    }) as unknown as typeof fetch
    const k = new VeriKaynagi({
      secenekler: { clientID: 'C1', veri: 'https', taban: 'https://sunucu/veri' },
      onbellek: new Onbellek(2, depo),
      getir,
      yerelTaban: 'http://127.0.0.1:8090',
    })
    expect(await k.ayarBelgesi('ayarlar.json')).toEqual({ veri: { kaynak: 'dosya' } })
  })

  it('https modunda ayarlar bir kez alınınca çevrimdışı önbellekten gelir', async () => {
    const depo = new SahteDepo()
    let cevrimici = true
    const getir = vi.fn(async (adres: string) => {
      if (!cevrimici) throw new Error('ağ yok')
      if (String(adres).endsWith('/ayarlar.json')) return jsonYanit({ veri: { kaynak: 'https' }, ozellikler: { yayinlar: false } })
      return new Response('yok', { status: 404 })
    }) as unknown as typeof fetch
    const k = new VeriKaynagi({
      secenekler: { clientID: 'C1', veri: 'https', taban: 'https://sunucu/veri' },
      onbellek: new Onbellek(2, depo),
      getir,
      yerelTaban: 'http://127.0.0.1:8090',
    })
    expect(await k.ayarBelgesi('ayarlar.json')).toMatchObject({ veri: { kaynak: 'https' } })
    cevrimici = false
    expect(await k.ayarBelgesi('ayarlar.json')).toMatchObject({ veri: { kaynak: 'https' } })
  })

  it('ayar dosyası olarak yalnızca bilinen adları kabul eder', async () => {
    const depo = new SahteDepo()
    const { kaynak: k } = kaynak(depo, {})
    expect(await k.ayarBelgesi('gizli.json')).toBeNull()
  })

  it('görsel ÖNCE yerel sunucu köprüsünden alınır (CORS engeli yok)', async () => {
    const depo = new SahteDepo()
    const cagrilar: string[] = []
    const png = new Uint8Array([137, 80, 78, 71]).buffer
    const getir = vi.fn(async (adres: string) => {
      cagrilar.push(String(adres))
      return new Response(png, { headers: { 'Content-Type': 'image/png' } })
    }) as unknown as typeof fetch
    const k = new VeriKaynagi({
      secenekler: { clientID: 'C1', veri: 'yerel', taban: '' },
      onbellek: new Onbellek(2, depo),
      getir,
    })

    const url = 'https://ornek.example/yayin/a.png'
    expect(await k.gorsel(url)).not.toBeNull()
    // köprü çağrıldı, görsel doğrudan ÇEKİLMEDİ (tarayıcı CORS'u devreye girmesin)
    expect(cagrilar.some((u) => u.startsWith('/gorsel?u='))).toBe(true)
    expect(cagrilar.includes(url)).toBe(false)
    expect(cagrilar[0]).toContain(encodeURIComponent(url))
  })

  it('zorla=true: damga aynı olsa da önbellek atlanır (yerel değişiklik görünür olur)', async () => {
    // Panel/araç `lastSystemData.json`'u değiştirip damgayı tazelemezse eski gövde önbellekten
    // geliyordu → "5'ten fazla nöbetçi" testinde ekranda hiçbir şey değişmiyordu.
    const depo = new SahteDepo()
    let surum = 1
    const getir = vi.fn(
      async () =>
        new Response(JSON.stringify({ Nobetler: {}, Yayinlar: {}, surum }), {
          headers: { 'Content-Type': 'application/json' },
        }),
    ) as unknown as typeof fetch
    const k = new VeriKaynagi({
      secenekler: { clientID: 'C1', veri: 'yerel', taban: '' },
      onbellek: new Onbellek(2, depo),
      getir,
    })

    const a = (await k.sistemVerisi('D1')) as unknown as { surum: number }
    expect(a.surum).toBe(1)
    surum = 2 // yerelde veri değişti, DAMGA AYNI
    const b = (await k.sistemVerisi('D1')) as unknown as { surum: number }
    expect(b.surum).toBe(1) // önbellekten (beklenen davranış)
    const c = (await k.sistemVerisi('D1', true)) as unknown as { surum: number }
    expect(c.surum).toBe(2) // zorla → taze indirildi
    expect(getir).toHaveBeenCalledTimes(2)
  })

  it('köprü yoksa tarayıcı önbelleği → doğrudan indirme sırasına düşülür', async () => {
    const depo = new SahteDepo()
    const cagrilar: string[] = []
    const png = new Uint8Array([137, 80, 78, 71]).buffer
    const getir = vi.fn(async (adres: string) => {
      cagrilar.push(String(adres))
      // köprü yok (statik sunucu): 404
      if (String(adres).startsWith('/gorsel')) return new Response('', { status: 404 })
      return new Response(png, { headers: { 'Content-Type': 'image/png' } })
    }) as unknown as typeof fetch
    const k = new VeriKaynagi({
      secenekler: { clientID: 'C1', veri: 'yerel', taban: '' },
      onbellek: new Onbellek(2, depo),
      getir,
    })

    const url = 'https://ornek.example/yayin/a.png'
    expect(await k.gorsel(url)).not.toBeNull()
    expect(await k.gorsel(url)).not.toBeNull() // ikinci kez tarayıcı önbelleğinden
    expect(cagrilar.filter((u) => u === url).length).toBe(1)
  })
})

// ------------------------------------------------------------------ önbellek bakım
describe('Onbellek — süre sonu ve artık temizliği', () => {
  it('süresi geçen görseli siler, tazesini korur', async () => {
    const { onbellek, depo } = sahteDepo()
    const taze = new Uint8Array([1, 2, 3]).buffer
    const eski = new Uint8Array([4, 5, 6]).buffer
    await onbellek.gorselYaz('https://x/taze.png', taze, 'image/png', 'D1')
    await onbellek.gorselYaz('https://x/eski.png', eski, 'image/png', 'D1')

    // eski kaydın son gösterimini 5 gün öncesine çek: kaydı bul, gövdeyi olduğu gibi bırak
    const anahtarlar = await depo.keys()
    const eskiAnahtar = anahtarlar.find((a) => a.includes('__onbellek/gorsel/') && a !== anahtarlar[0])
    expect(eskiAnahtar).toBeDefined()
    const eskiKayit = await depo.match(String(eskiAnahtar))
    expect(eskiKayit).toBeDefined()
    const bilgi = await onbellek.gorselBilgileri()
    expect(bilgi.length).toBe(2)

    // Kayıtların son gösterimini geçmişe çek (bakım süresi 2 gün)
    for (const k of bilgi) {
      await onbellek.gorselGosterildi(k.url) // sayaç/son gösterim alanı yazılabiliyor mu
    }
    const sonuc = await onbellek.bakim(new Date(Date.now() + 10 * 86400000))
    expect(sonuc.silinen).toBe(2)
  })

  it('veride geçmeyen görseli siler', async () => {
    const { onbellek } = sahteDepo()
    await onbellek.gorselYaz('https://x/1.png', new Uint8Array([1]).buffer, 'image/png')
    await onbellek.gorselYaz('https://x/2.png', new Uint8Array([2]).buffer, 'image/png')
    const sonuc = await onbellek.bakim(new Date(), new Set(['https://x/1.png']))
    expect(sonuc.silinen).toBe(1)
    expect((await onbellek.gorselBilgileri()).map((k) => k.url)).toEqual(['https://x/1.png'])
  })

  it('gösterim sayacı ve son gösterim zamanı tutulur', async () => {
    const { onbellek } = sahteDepo()
    await onbellek.gorselYaz('https://x/1.png', new Uint8Array([1]).buffer, 'image/png')
    await onbellek.gorselGosterildi('https://x/1.png')
    await onbellek.gorselGosterildi('https://x/1.png')
    const [kayit] = await onbellek.gorselBilgileri()
    expect(kayit.gosterim).toBe(2)
    expect(kayit.sonGosterim).not.toBe('')
  })

  it('Cache.keys() Request döndürse de çalışır (gerçek tarayıcı davranışı)', async () => {
    // Gerçek Cache API `keys()` Request nesnesi döndürür (string DEĞİL): `k.includes(...)`
    // çağrısı bu yüzden patlıyordu ("n.includes is not a function").
    const icDepo = new SahteDepo()
    const requestDonen: OnbellekDeposu = {
      match: (s) => icDepo.match(s),
      put: (s, y) => icDepo.put(s, y),
      delete: (s) => icDepo.delete(s),
      keys: async () => (await icDepo.keys()).map((k) => ({ url: k })),
    }
    const onbellek = new Onbellek(2, requestDonen)
    await onbellek.gorselYaz('https://x/1.png', new Uint8Array([1]).buffer, 'image/png')
    await onbellek.gorselYaz('https://x/2.png', new Uint8Array([2]).buffer, 'image/png')

    const bilgi = await onbellek.gorselBilgileri()
    expect(bilgi.map((k) => k.url).sort()).toEqual(['https://x/1.png', 'https://x/2.png'])
    // veride yalnızca 1.png var → 2.png silinir
    expect(await onbellek.bakim(new Date(), new Set(['https://x/1.png']))).toEqual({ silinen: 1 })
    expect(await onbellek.bosalt()).toBe(1)
  })

  it('bozuk kayıt okunmaz (sha256 tutmuyorsa)', async () => {
    const { onbellek, depo } = sahteDepo()
    await onbellek.gorselYaz('https://x/1.png', new Uint8Array([1, 2]).buffer, 'image/png')
    // gövdeyi değiştir ama sha256'yı bırak (bozulma benzetimi): kaydı anahtarından bul
    const anahtar = (await depo.keys()).find((a) => a.includes('__onbellek/gorsel/'))
    expect(anahtar).toBeDefined()
    await depo.put(String(anahtar), {
      headers: { get: (ad: string) => (ad.toLowerCase() === 'x-sha256' ? 'yanlis' : null) },
      arrayBuffer: async () => new Uint8Array([9, 9]).buffer,
      text: async () => '',
      ok: true,
      status: 200,
    })
    expect(await onbellek.gorselOku('https://x/1.png')).toBeNull()
  })
})

// ------------------------------------------------------------------ ayarlar/kapsam
describe('kapsamCoz — varsayilan → ilce → bolge → cihaz', () => {
  const belge = {
    varsayilan: { ozellikler: { yayinlar: true } },
    ilceler: { I1: { ozellikler: { yayinlar: false } } },
    bolgeler: { B1: { kusak: { hiz: 9 } } },
    cihazlar: { C1: { ozellikler: { saat_tarih: false } } },
  }

  it('en özel katman kazanır', () => {
    const { degerler, uygulanan } = kapsamCoz(belge, { ilceId: 'I1', bolgeId: 'B1', clientId: 'C1' })
    expect(degerler.ozellikler.yayinlar).toBe(false)
    expect(degerler.kusak.hiz).toBe(9)
    expect(degerler.ozellikler.saat_tarih).toBe(false)
    expect(uygulanan).toEqual(['varsayilan', 'ilce:I1', 'bolge:B1', 'cihaz:C1'])
  })

  it('cihaz katmanı ilçe katmanını geçersiz kılar', () => {
    const { degerler } = kapsamCoz(belge, { ilceId: 'I1', clientId: 'C1' })
    expect(degerler.ozellikler.yayinlar).toBe(false)
  })

  it('kapsam grupları dışındaki gruplar yok sayılır', () => {
    const { degerler } = kapsamCoz({ varsayilan: { veri: { kaynak: 'https' } } as never }, {})
    expect(degerler.veri).toBeUndefined()
  })

  it('boş belge güvenle çözülür', () => {
    expect(kapsamCoz(null, {}).degerler).toEqual({})
  })
})

describe('Ayarlar — dosya + kapsam birleşimi', () => {
  const varsayilanlar = { ozellikler: { yayinlar: true, saat_tarih: true }, gorunum: { sol_panel_satir: 5 } }

  it('dosya değerleri varsayılanların üzerine yazar', () => {
    // ayarlar.json DÜZ grup haritasıdır (kapsam dosyası iç içedir)
    const a = new Ayarlar(varsayilanlar, { ozellikler: { yayinlar: false } })
    expect(a.ozellik('yayinlar')).toBe(false)
    expect(a.ozellik('saat_tarih')).toBe(true)
    expect(a.sayi('gorunum', 'sol_panel_satir', 5)).toBe(5)
  })

  it('kapsam ayarları en son uygulanır', () => {
    const a = new Ayarlar(
      varsayilanlar,
      { gorunum: { sol_panel_satir: 5 } },
      { ilceler: { I1: { gorunum: { sol_panel_satir: 8 } } } },
      { ilceId: 'I1' },
    )
    expect(a.sayi('gorunum', 'sol_panel_satir', 5)).toBe(8)
  })

  it('bilinmeyen anahtar yedeği döner', () => {
    const a = new Ayarlar(varsayilanlar)
    expect(a.metin('kusak', 'olmayan', 'x')).toBe('x')
  })
})

// ------------------------------------------------------------------ yayınlar
describe('yayınlar — pencere, sıra, süre', () => {
  const AN = new Date(2026, 9, 15, 12, 0, 0)
  const veri = {
    Yayinlar: {
      '10': { start: '2026-10-15T10:00:00', end: '2026-10-15T13:00:00', contentUrl: 'https://x/10.png', duration: '30' },
      '2': { start: '2026-10-15T10:00:00', end: '2026-10-15T13:00:00', contentUrl: 'https://x/2.png', duration: '20' },
      '3': { start: '2026-10-15T13:00:00', end: '2026-10-15T14:00:00', contentUrl: 'https://x/3.png' },
      '4': { contentUrl: 'https://x/4.png' },
    },
  }

  it('anahtarları Qt ile aynı sıraya dizer (sayısal artan; sayısal olmayan başta)', () => {
    expect(yayinSirasi(veri).map((y) => yayinAdresi(y).split('/').pop())).toEqual([
      '2.png',
      '3.png',
      '4.png',
      '10.png',
    ])
    // sayısal olmayan anahtar başa gelir (Qt: int(x) if x.isdigit() else -1)
    const karisik = { Yayinlar: { b: { contentUrl: 'https://x/b.png' }, '2': { contentUrl: 'https://x/2.png' } } }
    expect(yayinSirasi(karisik).map((y) => yayinAdresi(y).split('/').pop())).toEqual(['b.png', '2.png'])
  })

  it('yalnızca penceresi şu anı kapsayanları döner', () => {
    const aktif = aktifYayinlar(veri, AN)
    expect(aktif.map((y) => yayinAdresi(y))).toEqual(['https://x/2.png', 'https://x/10.png'])
  })

  it('yarı açık aralık: bitiş anında yayın düşer', () => {
    const y = { start: '2026-10-15T10:00:00', end: '2026-10-15T13:00:00' }
    expect(yayinAktifMi(y, new Date(2026, 9, 15, 12, 59, 59))).toBe(true)
    expect(yayinAktifMi(y, new Date(2026, 9, 15, 13, 0, 0))).toBe(false)
  })

  it('penceresi okunamayan yayın gösterilmez', () => {
    expect(yayinAktifMi({ contentUrl: 'https://x/4.png' }, AN)).toBe(false)
  })

  it('süre sınırlara kıstırılır, okunamazsa varsayılan', () => {
    const a = new Ayarlar({ veri: { yayin_sure_en_az_s: 5, yayin_sure_en_cok_s: 60, yayin_sure_varsayilan_s: 10 } })
    expect(yayinSuresiMs({ duration: '30' }, a)).toBe(30000)
    expect(yayinSuresiMs({ duration: '1' }, a)).toBe(5000)
    expect(yayinSuresiMs({ duration: '9999' }, a)).toBe(60000)
    expect(yayinSuresiMs({}, a)).toBe(10000)
    expect(yayinSuresiMs({ duration: 'bozuk' })).toBe(10000)
  })
})

/**
 * Regresyon: `DOSYA_ADRESI` sonunda `/` varken `${taban}/match.json` **çift slash** üretiyordu
 * (`…//match.json` → S3/CloudFront 403) → match.json okunamıyor → "cihaz kimliği match.json içinde
 * bulunamadı" beyaz ekranı. Qt tarafı zaten `rstrip('/')` yapıyordu; tarayıcı yapmıyordu.
 */
describe('veri tabanı adresi (çift slash)', () => {
  function kaynak(taban: string, toplanan: string[]) {
    const getir = vi.fn(async (adres: string | URL | Request) => {
      toplanan.push(String(adres))
      return {
        ok: true,
        status: 200,
        arrayBuffer: async () => new TextEncoder().encode('{}').buffer,
        text: async () => '{}',
      } as unknown as Response
    }) as unknown as typeof fetch
    return new VeriKaynagi({
      secenekler: { clientID: 'C1', veri: 'https', taban },
      onbellek: new Onbellek(2, new SahteDepo()),
      getir,
      yerelTaban: 'http://127.0.0.1:8090',
    })
  }

  it('sondaki / temizlenir', async () => {
    const adresler: string[] = []
    const k = kaynak('https://sunucu/veri/', adresler)
    expect(k.veriTaban()).toBe('https://sunucu/veri')
    await k.match()
    expect(adresler).toContain('https://sunucu/veri/match.json')
  })

  it('çoklu / temizlenir', () => {
    expect(kaynak('https://sunucu/veri///', []).veriTaban()).toBe('https://sunucu/veri')
  })

  it('slash yoksa değişmez', () => {
    expect(kaynak('https://sunucu/veri', []).veriTaban()).toBe('https://sunucu/veri')
  })
})
