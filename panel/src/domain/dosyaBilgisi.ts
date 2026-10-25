/** Panelde gösterilen kiosk dosyalarının kısa açıklamaları. */
export const DOSYA_ACIKLAMALARI: Record<string, string> = {
  'ayarlar.json': 'Genel ayarlar (özellikler, kuşak, görünüm, veri kaynağı, ağ)',
  'kapsam-ayarlari.json': 'İlçe / bölge / cihaz bazında özellik geçersiz kılmaları',
  'lastSystemData.json': 'Nöbet + yayın verisi (cihazın ekranda kullandığı dosya)',
  'sablon.json': 'Şablon: cihazın doldurduğu veri iskeleti',
  'match.json': 'Cihaz → ilçe/bölge eşlemesi',
  'lastupdate.json': 'Veri değişiklik damgası (cihaz saatlik kontrol eder)',
  'makinebilgileri.json': 'Cihaz kimliği (clientID) — her cihazda ayrı',
  'komut.json': 'Son uzaktan komut (imzalı; cihaz beyaz listeye göre uygular)',
}
