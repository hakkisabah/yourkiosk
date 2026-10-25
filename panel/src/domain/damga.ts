/**
 * VERİ DAMGASI (`lastupdate`) — biçim doğrulaması ve güvenli "en yeni" seçimi.
 *
 * NEDEN: panel `durum.json`a yazdığı `lastupdate` damgasını sunucudan taze okur ve bellekteki
 * değerle karşılaştırır. Düz sözlüksel karşılaştırma (`sunucu > bellek`) beklenmeyen bir değerde
 * yanlış sonuç veriyordu: nesne → `String()` → `"[object Object]"` ve `"[" (91) > "2" (50)`.
 * Damga geri sarılırsa cihazlar her turda gereksiz `lastupdate.json` çeker (i5 bulgusu).
 *
 * Kural: YALNIZ `YYYY-AA-GG[ T]SS:dd:ss` biçimindeki metinler damga sayılır; aynı biçimde
 * sözlüksel karşılaştırma tarih sırasıyla aynıdır.
 */
const DAMGA_KALIBI = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}/

/** Damga metnini döndürür; geçersiz/boş/nesne değerlerde `''`. */
export function damgaMetni(deger: unknown): string {
  if (typeof deger !== 'string') return ''
  const metin = deger.trim()
  return DAMGA_KALIBI.test(metin) ? metin : ''
}

/** Adaylardan GEÇERLİ ve EN YENİ damgayı seçer (hiçbiri geçerli değilse `''`). */
export function enYeniDamga(...adaylar: unknown[]): string {
  let enYeni = ''
  for (const aday of adaylar) {
    const metin = damgaMetni(aday)
    if (metin && metin > enYeni) enYeni = metin
  }
  return enYeni
}
