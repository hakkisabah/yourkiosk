import { describe, expect, it } from 'vitest'

import {
  AZAMI_CIHAZ,
  AZAMI_GOVDE_BAYT,
  AZAMI_KIMLIK_UZUNLUK,
  AZAMI_YENIDEN_BAGLANMA,
  VARSAYILAN_ESIK_DK,
  cevrimiciMi,
  durumEkle,
  durumEtiketi,
  durumKonusu,
  izlemeBaslat,
  izlemeOzeti,
  kalpAtisiCoz,
  konudanCihaz,
} from './cihazIzleme'

const SIMDI = new Date('2026-10-25T12:00:00.000Z')

describe('durumKonusu / konudanCihaz', () => {
  it('yayın konusundan durum joker konusunu üretir', () => {
    expect(durumKonusu('yourkiosk/yayin')).toBe('yourkiosk/durum/+')
    expect(durumKonusu('yourkiosk/yayin/')).toBe('yourkiosk/durum/+')
    expect(durumKonusu('kurum/alt/yayin')).toBe('kurum/alt/durum/+')
    // tek parçalı konu: taban konunun kendisidir (kiosk `push.durum_konusu` ile AYNI kural)
    expect(durumKonusu('yayin')).toBe('yayin/durum/+')
    expect(durumKonusu('')).toBe('yourkiosk/durum/+')
  })

  it('konudan cihaz kimliğini çıkarır', () => {
    expect(konudanCihaz('yourkiosk/durum/C1')).toBe('C1')
    expect(konudanCihaz('')).toBe('')
  })
})

describe('kalpAtisiCoz', () => {
  it('geçerli gövdeyi çözer (geliş anı damgasıyla)', () => {
    const durum = kalpAtisiCoz(
      'yourkiosk/durum/C1',
      '{"cevrimici":true,"zaman":"2026-10-25T11:58:00Z","mod":"qt"}',
      SIMDI.getTime(),
    )
    expect(durum).toEqual({
      cihazId: 'C1',
      cevrimici: true,
      zaman: '2026-10-25T11:58:00Z',
      mod: 'qt',
      alindi: SIMDI.getTime(),
    })
  })

  it('Uint8Array gövdeyi de çözer (mqtt.js böyle verir)', () => {
    const govde = new TextEncoder().encode('{"cevrimici":false,"zaman":"2026-10-25T11:00:00Z"}')
    expect(kalpAtisiCoz('yourkiosk/durum/C2', govde)?.cevrimici).toBe(false)
  })

  it('bozuk/eksik gövdede null (panel çökmez)', () => {
    expect(kalpAtisiCoz('yourkiosk/durum/C1', 'bozuk')).toBeNull()
    expect(kalpAtisiCoz('yourkiosk/durum/C1', '[]')).toBeNull()
    expect(kalpAtisiCoz('yourkiosk/durum/C1', '{}')).toBeNull()
    expect(kalpAtisiCoz('', '{"cevrimici":true,"zaman":"2026-10-25T11:00:00Z"}')).toBeNull()
  })

  it('zaman alanı yoksa ama cevrimici=true ise kabul eder (alindi yine de damgalanır)', () => {
    const durum = kalpAtisiCoz('yourkiosk/durum/C3', '{"cevrimici":true}', SIMDI.getTime())
    expect(durum?.zaman).toBe('')
    expect(durum?.alindi).toBe(SIMDI.getTime())
  })
})

describe('cevrimiciMi / durumEtiketi', () => {
  const simdiMs = SIMDI.getTime()

  it('eşik içindeki kalp atışı çevrimiçi, eskisi değil', () => {
    expect(cevrimiciMi('2026-10-25T11:50:00Z', SIMDI)).toBe(true) // 10 dk
    expect(cevrimiciMi('2026-10-25T11:40:00Z', SIMDI)).toBe(false) // 20 dk
    expect(cevrimiciMi('bozuk', SIMDI)).toBe(false)
    expect(VARSAYILAN_ESIK_DK).toBe(15)
  })

  it('cihaz saati kaymış olsa da GELİŞ ANI taze ise çevrimiçi (i5 bulgusu)', () => {
    // Cihazın RTC'si yok: 3 saat geride damga atıyor ama mesaj şimdi geldi.
    const durum = { cihazId: 'C1', cevrimici: true, zaman: '2026-10-25T09:00:00Z', mod: 'qt', alindi: simdiMs }
    expect(cevrimiciMi(durum.zaman, SIMDI)).toBe(false) // eski davranış: yanlış "çevrimdışı"
    expect(durumEtiketi(durum, SIMDI).metin).toBe('çevrimiçi') // yeni davranış: doğru
  })

  it('geliş anı eşikten eskiyse (mesaj akmıyorsa) çevrimdışı', () => {
    const durum = {
      cihazId: 'C1',
      cevrimici: true,
      zaman: SIMDI.toISOString(),
      mod: 'qt',
      alindi: simdiMs - 30 * 60_000,
    }
    expect(durumEtiketi(durum, SIMDI).metin).toBe('çevrimdışı')
  })

  it('LWT ile çevrimdışı işaretlenen cihaz "çevrimdışı" görünür', () => {
    const durum = { cihazId: 'C1', cevrimici: false, zaman: '2026-10-25T11:59:00Z', mod: 'qt', alindi: simdiMs }
    expect(durumEtiketi(durum, SIMDI).metin).toBe('çevrimdışı')
  })

  it('taze kalp atışı gelse bile cevrimici=false ise çevrimdışı kalır', () => {
    const durum = { cihazId: 'C1', cevrimici: false, zaman: SIMDI.toISOString(), mod: 'qt', alindi: simdiMs }
    expect(durumEtiketi(durum, SIMDI).metin).toBe('çevrimdışı')
  })

  it('hiç kalp atışı yoksa "bilinmiyor"', () => {
    expect(durumEtiketi(undefined, SIMDI)).toEqual({ metin: 'bilinmiyor', renk: 'grey' })
  })

  it('bayat kalp atışı (cevrimici=true ama eski) çevrimdışı sayılır', () => {
    const durum = {
      cihazId: 'C1',
      cevrimici: true,
      zaman: '2026-10-25T09:00:00Z',
      mod: 'qt',
      alindi: simdiMs - 3 * 3_600_000,
    }
    expect(durumEtiketi(durum, SIMDI).metin).toBe('çevrimdışı')
  })
})

describe('izlemeOzeti', () => {
  it('cihaz listesine göre çevrimiçi/çevrimdışı/bilinmiyor sayar', () => {
    const alindi = SIMDI.getTime()
    const durumlar = new Map([
      ['C1', { cihazId: 'C1', cevrimici: true, zaman: '2026-10-25T11:58:00Z', mod: 'qt', alindi }],
      ['C2', { cihazId: 'C2', cevrimici: false, zaman: '2026-10-25T11:58:00Z', mod: 'qt', alindi }],
      ['C9', { cihazId: 'C9', cevrimici: true, zaman: '2026-10-25T11:58:00Z', mod: 'qt', alindi }],
    ])
    const ozet = izlemeOzeti(durumlar, ['C1', 'C2', 'C3'], SIMDI)
    expect(ozet).toEqual({ cevrimici: 1, cevrimdisi: 1, bilinmiyor: 1 })
  })
})

/**
 * i5 bulguları (25.10 15:14) — girdi sınırları ve sonsuz yeniden bağlanma.
 * Bu testler düzeltme kaldırıldığında KIRMIZI olmalı; sınır yoksa 1 MB gövde ve 5000
 * karakterlik kimlik kabul ediliyordu (i5 ölçtü).
 */
describe('girdi sınırları (i5 bulgusu)', () => {
  it('512 bayttan büyük gövde JSON.parse edilmeden reddedilir', () => {
    const buyuk = JSON.stringify({ cevrimici: true, zaman: '2026-10-25T12:00:00Z', sisirme: 'x'.repeat(2000) })
    expect(new TextEncoder().encode(buyuk).length).toBeGreaterThan(AZAMI_GOVDE_BAYT)
    expect(kalpAtisiCoz('yourkiosk/durum/C1', buyuk, SIMDI.getTime())).toBeNull()
  })

  it('sınırın altındaki normal kalp atışı kabul edilir', () => {
    const govde = JSON.stringify({ cevrimici: true, zaman: '2026-10-25T12:00:00Z', mod: 'qt', surum: '1.0.0' })
    expect(new TextEncoder().encode(govde).length).toBeLessThanOrEqual(AZAMI_GOVDE_BAYT)
    expect(kalpAtisiCoz('yourkiosk/durum/C1', govde, 1234)?.cihazId).toBe('C1')
  })

  it('uzun ya da bozuk karakterli cihaz kimliği yok sayılır', () => {
    expect(konudanCihaz('yourkiosk/durum/' + 'a'.repeat(AZAMI_KIMLIK_UZUNLUK + 1))).toBe('')
    expect(konudanCihaz('yourkiosk/durum/C1')).toBe('C1')
    expect(konudanCihaz('yourkiosk/durum/kötü#id')).toBe('')
    expect(konudanCihaz('yourkiosk/durum/boşluk lu')).toBe('')
    expect(kalpAtisiCoz('yourkiosk/durum/' + 'a'.repeat(500), '{"cevrimici":true}', 1)).toBeNull()
  })
})

describe('durumEkle — sınırlı harita (i5 bulgusu)', () => {
  const durum = (id: string) => ({ cihazId: id, cevrimici: true, zaman: '', mod: 'qt', alindi: 1 })

  it('yeni Map döndürür, eskisini değiştirmez', () => {
    const eski = new Map([['C1', durum('C1')]])
    const yeni = durumEkle(eski, durum('C2'), 10)
    expect(eski.size).toBe(1)
    expect(yeni.size).toBe(2)
    expect(yeni.get('C2')?.cihazId).toBe('C2')
  })

  it('tavan aşılınca EN ESKİ kayıt düşer, yeni kimlik girer', () => {
    let harita = new Map<string, ReturnType<typeof durum>>()
    for (const id of ['C1', 'C2', 'C3']) harita = durumEkle(harita, durum(id), 2)
    expect([...harita.keys()]).toEqual(['C2', 'C3'])
    // aynı cihazın güncellemesi tavanı büyütmez, sırasını tazeler
    harita = durumEkle(harita, durum('C2'), 2)
    expect([...harita.keys()]).toEqual(['C3', 'C2'])
    expect(harita.size).toBe(2)
  })

  it('varsayılan tavan 2000 kayıttır', () => {
    let harita = new Map<string, ReturnType<typeof durum>>()
    for (let i = 0; i < AZAMI_CIHAZ + 50; i += 1) harita = durumEkle(harita, durum(`C${i}`))
    expect(harita.size).toBe(AZAMI_CIHAZ)
    expect(harita.has('C0')).toBe(false)
    expect(harita.has(`C${AZAMI_CIHAZ + 49}`)).toBe(true)
  })
})

describe('izlemeBaslat — yeniden bağlanma sınırı (i5 bulgusu)', () => {
  function sahteIstemci() {
    const dinleyiciler: Record<string, Array<(...a: never[]) => void>> = {}
    const kapatma = { sayi: 0 }
    const istemci = {
      on: (olay: string, dinleyici: (...a: never[]) => void) => {
        ;(dinleyiciler[olay] ??= []).push(dinleyici)
        return istemci
      },
      subscribe: () => istemci,
      end: () => {
        kapatma.sayi += 1
        return istemci
      },
    }
    const tetikle = (olay: string) => (dinleyiciler[olay] ?? []).forEach((f) => (f as () => void)())
    return { istemci, tetikle, kapatma }
  }

  it('5 başarısız denemeden sonra oturumu kapatır ve hata bildirir', async () => {
    const { istemci, tetikle, kapatma } = sahteIstemci()
    const olaylar: string[] = []
    let hataMetni = ''
    const oturum = await izlemeBaslat(
      () => undefined,
      { url: 'wss://ornek:8084/mqtt', kullanici: 'panel-izleme', parola: 'x' },
      {
        baglan: () => istemci,
        durum: (durum, ayrinti) => {
          olaylar.push(durum)
          if (durum === 'hata') hataMetni = ayrinti ?? ''
        },
      },
    )
    expect(oturum).not.toBeNull()
    for (let i = 0; i < AZAMI_YENIDEN_BAGLANMA; i += 1) tetikle('reconnect')
    expect(kapatma.sayi).toBe(0) // sınırın altında kapatmaz
    tetikle('reconnect') // sınırı aşan deneme
    expect(kapatma.sayi).toBe(1)
    expect(olaylar.at(-1)).toBe('hata')
    expect(hataMetni).toContain('yeniden bağlanılamadı')
  })
})
