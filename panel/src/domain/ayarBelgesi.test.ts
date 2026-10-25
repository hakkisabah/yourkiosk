import { describe, expect, it } from 'vitest'

import { anahtarSayisi, eksikAnahtarlar, tamBelge } from './ayarBelgesi'
import { gruplar, tumAnahtarlar, varsayilanBelge } from './sema'

describe('tamBelge — ayarlar.json TAM belge kuralı', () => {
  it('şemadaki her anahtarı yazar (sparse taslak tamamlanır)', () => {
    const belge = tamBelge({ ozellikler: { nobet_listesi: false } })
    expect(eksikAnahtarlar(belge)).toEqual([])
    expect(anahtarSayisi(belge)).toBe(tumAnahtarlar.length)
    for (const g of gruplar) expect(belge[g.ad]).toBeTypeOf('object')
  })

  it('verilen değeri korur, verilmeyeni şema varsayılanıyla doldurur', () => {
    const belge = tamBelge({ ozellikler: { nobet_listesi: false } })
    expect(belge.ozellikler.nobet_listesi).toBe(false)
    const varsayilan = varsayilanBelge()
    // dokunulmayan bir anahtar varsayılanıyla gelir
    expect(belge.tetik.push_aktif).toBe(varsayilan.tetik.push_aktif)
    expect(belge.gelismis.max_json_bayt).toBe(varsayilan.gelismis.max_json_bayt)
  })

  it('boş/undefined taslak tam bir varsayılan belgesi üretir', () => {
    expect(tamBelge(undefined)).toEqual(varsayilanBelge())
    expect(tamBelge({})).toEqual(varsayilanBelge())
  })

  it('şemada olmayan anahtarları ve _açıklama alanlarını YAZMAZ (kiosk bunları yok sayar)', () => {
    const belge = tamBelge({
      ozellikler: { nobet_listesi: true, _nobet_listesi_aciklama: 'eski belgeden', eski_anahtar: 5 },
      bilinmeyen_grup: { x: 1 },
    })
    expect(belge.ozellikler.eski_anahtar).toBeUndefined()
    expect(Object.keys(belge.ozellikler).some((k) => k.startsWith('_'))).toBe(false)
    expect(belge.bilinmeyen_grup).toBeUndefined()
  })

  it('eksikAnahtarlar eksik belgeyi raporlar (kural denetimi)', () => {
    const eksik = eksikAnahtarlar({ ozellikler: { nobet_listesi: true } })
    expect(eksik.length).toBe(tumAnahtarlar.length - 1)
    expect(eksik).toContain('gelismis.max_json_bayt')
  })
})
