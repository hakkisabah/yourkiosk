/**
 * Tetikleyici (panel → cihaz) — hangi yayınların cihazı ANINDA yenilemesi gerektiği.
 *
 * Kural: ekranda görüneni değiştiren her dosya yazıldıktan sonra `tetikle.json` yazılır.
 * Cihaz tarafında `tetik.aktif` ve `tetik.modlar` ayarları bunu kullanıp kullanmayacağını belirler.
 */
export const TETIK_DOSYALARI = [
  'ayarlar.json',
  'kapsam-ayarlari.json',
  'sablon.json',
  'lastSystemData.json',
  'match.json',
  'lastupdate.json',
] as const

/** Bu dosyanın değişmesi cihazın ekranını değiştirebilir mi? */
export function tetikGerekir(ad: string): boolean {
  return (TETIK_DOSYALARI as readonly string[]).includes(ad)
}

/** `tetikle.json` gövdesi — kapsam boş = tüm cihazlar. */
export function tetikBelgesi(ad: string, zaman: string = new Date().toISOString()): Record<string, unknown> {
  return { zaman, ilceId: '', bolgeId: '', aciklama: `panel: ${ad}` }
}
