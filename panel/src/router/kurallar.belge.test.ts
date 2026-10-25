/**
 * BELGE ↔ MENÜ TUTARLILIĞI (kullanıcı geri bildirimi).
 *
 * NEDEN: Talimat verirken "panelde VeriView'de ..." denildi; oysa menüde görünen ad
 * "Nöbet ve Yayınlar", `VeriView.vue` yalnız dosya adı. Kullanıcı ekranda öyle bir menü
 * bulamadı. Bu test, README'deki ekran adları ile `MENU` tanımının ayrışmasını engeller.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { MENU } from './kurallar'

describe('MENU ↔ panel/README', () => {
  const readme = readFileSync(fileURLToPath(new URL('../../README.md', import.meta.url)), 'utf8')

  it('her menü başlığı README ekran tablosunda geçer', () => {
    const eksik = MENU.filter((oge) => !readme.includes(`**${oge.baslik}**`)).map((o) => o.baslik)
    expect(eksik).toEqual([])
  })

  it('her menü rotası gerçek bir sayfaya bağlıdır', () => {
    for (const oge of MENU) {
      expect(oge.yol.startsWith('/')).toBe(true)
      expect(oge.aciklama.length).toBeGreaterThan(10)
    }
  })

  it('README dosya adlarının menüde görünmediğini açıkça yazar', () => {
    expect(readme).toContain('dosya adları menüde görünmez')
  })
})
