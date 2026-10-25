import { describe, expect, it } from 'vitest'

import {
  VARSAYILAN_ESIK_DK,
  cevrimiciMi,
  durumEtiketi,
  durumKonusu,
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
  it('geçerli gövdeyi çözer', () => {
    const durum = kalpAtisiCoz(
      'yourkiosk/durum/C1',
      '{"cevrimici":true,"zaman":"2026-10-25T11:58:00Z","mod":"qt"}',
    )
    expect(durum).toEqual({ cihazId: 'C1', cevrimici: true, zaman: '2026-10-25T11:58:00Z', mod: 'qt' })
  })

  it('Uint8Array gövdeyi de çözer (mqtt.js böyle verir)', () => {
    const govde = new TextEncoder().encode('{"cevrimici":false,"zaman":"2026-10-25T11:00:00Z"}')
    expect(kalpAtisiCoz('yourkiosk/durum/C2', govde)?.cevrimici).toBe(false)
  })

  it('bozuk/eksik gövdede null (panel çökmez)', () => {
    expect(kalpAtisiCoz('yourkiosk/durum/C1', 'bozuk')).toBeNull()
    expect(kalpAtisiCoz('yourkiosk/durum/C1', '[]')).toBeNull()
    expect(kalpAtisiCoz('yourkiosk/durum/C1', '{"cevrimici":true}')).toBeNull()
    expect(kalpAtisiCoz('', '{"cevrimici":true,"zaman":"2026-10-25T11:00:00Z"}')).toBeNull()
  })
})

describe('cevrimiciMi / durumEtiketi', () => {
  it('eşik içindeki kalp atışı çevrimiçi, eskisi değil', () => {
    expect(cevrimiciMi('2026-10-25T11:50:00Z', SIMDI)).toBe(true) // 10 dk
    expect(cevrimiciMi('2026-10-25T11:40:00Z', SIMDI)).toBe(false) // 20 dk
    expect(cevrimiciMi('bozuk', SIMDI)).toBe(false)
    expect(VARSAYILAN_ESIK_DK).toBe(15)
  })

  it('LWT ile çevrimdışı işaretlenen cihaz "çevrimdışı" görünür', () => {
    const durum = { cihazId: 'C1', cevrimici: false, zaman: '2026-10-25T11:59:00Z', mod: 'qt' }
    expect(durumEtiketi(durum, SIMDI).metin).toBe('çevrimdışı')
  })

  it('taze kalp atışı gelse bile cevrimici=false ise çevrimdışı kalır', () => {
    const durum = { cihazId: 'C1', cevrimici: false, zaman: SIMDI.toISOString(), mod: 'qt' }
    expect(durumEtiketi(durum, SIMDI).metin).toBe('çevrimdışı')
  })

  it('hiç kalp atışı yoksa "bilinmiyor"', () => {
    expect(durumEtiketi(undefined, SIMDI)).toEqual({ metin: 'bilinmiyor', renk: 'grey' })
  })

  it('bayat kalp atışı (cevrimici=true ama eski) çevrimdışı sayılır', () => {
    const durum = { cihazId: 'C1', cevrimici: true, zaman: '2026-10-25T09:00:00Z', mod: 'qt' }
    expect(durumEtiketi(durum, SIMDI).metin).toBe('çevrimdışı')
  })
})

describe('izlemeOzeti', () => {
  it('cihaz listesine göre çevrimiçi/çevrimdışı/bilinmiyor sayar', () => {
    const durumlar = new Map([
      ['C1', { cihazId: 'C1', cevrimici: true, zaman: '2026-10-25T11:58:00Z', mod: 'qt' }],
      ['C2', { cihazId: 'C2', cevrimici: false, zaman: '2026-10-25T11:58:00Z', mod: 'qt' }],
      ['C9', { cihazId: 'C9', cevrimici: true, zaman: '2026-10-25T11:58:00Z', mod: 'qt' }],
    ])
    const ozet = izlemeOzeti(durumlar, ['C1', 'C2', 'C3'], SIMDI)
    expect(ozet).toEqual({ cevrimici: 1, cevrimdisi: 1, bilinmiyor: 1 })
  })
})
