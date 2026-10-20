/**
 * Cihaz verisine **çalışma anında** erişim — derleme zamanında modül çözmeye gerek YOK.
 *
 * Neden: `lastSystemData.json`, `match.json`, `lastupdate.json`, `makinebilgileri.json` cihaza
 * özgüdür ve **depoya girmez** (`.gitignore`). Testlerde `import '../../kiosk/…json'` yazılırsa
 * `vue-tsc --noEmit` bu dosyaları derleme anında arar ve temiz bir klonda `TS2307` ile patlar
 * (`npm run build` bunu çalıştırır → kurulum yapılamaz).
 *
 * Çözüm: `import.meta.glob` — yol listesi **derleme zamanında dosya çözmaz**; dosya yoksa anahtar
 * hiç oluşmaz. Böylece:
 *   · temiz klonda `npm run build` ve `npm test` geçer (gerçek-veri testleri atlanır),
 *   · cihazda veri varsa testler gerçek veriyle koşar.
 *
 * `node:fs`/`node:path` KULLANILMAZ: jsdom ortamında (bkz. `render.test.ts`) node modülleri
 * düzgün çalışmıyor (`fileURLToPath is not a function`, `resolve is not a function`).
 */

const HAM = import.meta.glob('../../../kiosk/*.json') as Record<string, () => Promise<{ default: unknown }>>

/** Kiosk JSON dosyasını (varsa) okur; yoksa `null`. */
export async function cihazDosyasi<T>(ad: string): Promise<T | null> {
  const anahtar = Object.keys(HAM).find((yol) => yol.endsWith(`/${ad}`))
  if (!anahtar) return null
  try {
    const modul = await HAM[anahtar]?.()
    return (modul?.default ?? null) as T | null
  } catch {
    return null
  }
}

/** Gerçek veriyle koşan testler için: gerekli dosyaların hepsi var mı? */
export const cihazVerisiVar = ['lastSystemData.json', 'match.json', 'lastupdate.json', 'makinebilgileri.json'].every(
  (ad) => Object.keys(HAM).some((yol) => yol.endsWith(`/${ad}`)),
)

/** Bulunan cihaz dosyalarının listesi (atlandıysa nedeni görünsün diye). */
export const bulunanDosyalar = Object.keys(HAM).map((yol) => yol.split('/').pop() ?? yol)
