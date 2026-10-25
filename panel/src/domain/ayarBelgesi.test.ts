import { describe, expect, it } from 'vitest'

import { anahtarSayisi, CIHAZA_OZGU, eksikAnahtarlar, tamBelge, yayinaGirer } from './ayarBelgesi'
import { gruplar, tumAnahtarlar, varsayilanBelge } from './sema'

describe('tamBelge — ayarlar.json TAM belge kuralı', () => {
  const yayinAnahtarlari = tumAnahtarlar.map((a) => a.tam).filter(yayinaGirer)

  it('şemadaki her YAYIN anahtarını yazar (sparse taslak tamamlanır)', () => {
    const belge = tamBelge({ ozellikler: { nobet_listesi: false } })
    expect(eksikAnahtarlar(belge)).toEqual([])
    expect(anahtarSayisi(belge)).toBe(yayinAnahtarlari.length)
    for (const g of gruplar) expect(belge[g.ad]).toBeTypeOf('object')
  })

  it('verilen değeri korur, verilmeyeni şema varsayılanıyla doldurur', () => {
    const belge = tamBelge({ ozellikler: { nobet_listesi: false } })
    expect(belge.ozellikler.nobet_listesi).toBe(false)
    const varsayilan = varsayilanBelge()
    // dokunulmayan bir anahtar varsayılanıyla gelir
    expect(belge.gelismis.max_json_bayt).toBe(varsayilan.gelismis.max_json_bayt)
  })

  it('boş/undefined taslak tam bir varsayılan belgesi üretir', () => {
    expect(tamBelge(undefined)).toEqual(tamBelge(varsayilanBelge()))
    expect(tamBelge({})).toEqual(tamBelge(varsayilanBelge()))
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
    expect(eksik.length).toBe(yayinAnahtarlari.length - 1)
    expect(eksik).toContain('gelismis.max_json_bayt')
    expect(eksik).not.toContain('tetik.push_parola')
  })
})

describe('CIHAZA_OZGU — cihaza özgü anahtarlar yayına yazılmaz (i5 bulgusu)', () => {
  it('MQTT kimliği ve X.509 yolları belgeye HİÇ girmez', () => {
    const belge = tamBelge(varsayilanBelge())
    for (const anahtar of [
      'push_aktif',
      'push_broker',
      'push_port',
      'push_konu',
      'push_kullanici',
      'push_parola',
      'push_ca',
      'push_sertifika',
      'push_anahtar',
    ]) {
      expect(belge.tetik[anahtar]).toBeUndefined()
    }
  })

  it('taslakta açıkça verilse bile sır/komut anahtarı yayına taşınmaz', () => {
    const belge = tamBelge({
      tetik: { push_aktif: true, push_parola: 'cihazin-parolasi' },
      calistirma: { komut_imza_zorunlu: false, komut_yeniden_baslat: 'systemctl reboot' },
    })
    expect(belge.tetik.push_parola).toBeUndefined()
    expect(belge.tetik.push_aktif).toBeUndefined()
    expect(belge.calistirma.komut_imza_zorunlu).toBeUndefined()
    expect(belge.calistirma.komut_yeniden_baslat).toBeUndefined()
  })

  it('CIHAZA_OZGU şemada var olan anahtarlardan oluşur (yazım hatası sessizce yutulmaz)', () => {
    const semaAnahtarlari = tumAnahtarlar.map((a) => a.tam)
    for (const tam of CIHAZA_OZGU) {
      expect(semaAnahtarlari, `${tam} şemada yok`).toContain(tam)
    }
  })

  it('kiosk YEREL_ONCELIKLI listesiyle aynı sırları korur (iki katman)', () => {
    // kiosk tarafı bu kümeyi `ayarlar.YEREL_ONCELIKLI` ile ayrıca uygular; burada en az
    // sır/komut anahtarlarının panelde de kapalı olduğunu garantiliyoruz.
    expect([...CIHAZA_OZGU].filter((k) => k.startsWith('tetik.push_')).length).toBe(9)
    expect([...CIHAZA_OZGU].filter((k) => k.startsWith('calistirma.komut_')).length).toBe(6)
  })
})
