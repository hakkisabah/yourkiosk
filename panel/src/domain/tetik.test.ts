/** Tetikleyici kuralları: hangi dosyalar yayın sayılır, gövde biçimi doğru mu. */
import { describe, expect, it } from 'vitest'

import { TETIK_DOSYALARI, tetikBelgesi, tetikGerekir } from './tetik'

describe('tetikGerekir', () => {
  it('ekranda görüneni değiştiren dosyalar tetik gerektirir', () => {
    for (const ad of TETIK_DOSYALARI) expect(tetikGerekir(ad)).toBe(true)
  })

  it('makine kimliği / tetikleyicinin kendisi / görseller tetik gerektirmez', () => {
    for (const ad of ['makinebilgileri.json', 'tetikle.json', 'yayin-gorselleri/a.png', 'bilinmeyen.json']) {
      expect(tetikGerekir(ad)).toBe(false)
    }
  })

  it('gövde: kapsam boş (tüm cihazlar), zaman ISO, açıklama dosya adını taşır', () => {
    const belge = tetikBelgesi('ayarlar.json', '2026-10-22T09:00:00.000Z')
    expect(belge).toEqual({
      zaman: '2026-10-22T09:00:00.000Z',
      ilceId: '',
      bolgeId: '',
      aciklama: 'panel: ayarlar.json',
    })
  })
})
