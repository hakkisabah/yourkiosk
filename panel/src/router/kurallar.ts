/**
 * Yönlendirme KURALLARI (yan etkisiz) — menü tanımı ve oturum izinleri.
 *
 * Router'ın kendisinden ayrı tutulur: bu dosya tarayıcı (window) gerektirmez, bu yüzden
 * testlerde doğrudan doğrulanabilir. `router/index.ts` bunu kullanır.
 */

export const MENU = [
  { yol: '/durum', baslik: 'Durum', ikon: 'mdi-monitor-dashboard', aciklama: 'Bağlantı, dosyalar, cihazın şu an ne gösterdiği' },
  { yol: '/ayarlar', baslik: 'Genel Ayarlar', ikon: 'mdi-cog', aciklama: 'ayarlar.json — tüm varsayılanlar' },
  { yol: '/kapsam', baslik: 'Kapsam Ayarları', ikon: 'mdi-sitemap', aciklama: 'İlçe / bölge / cihaz bazında özellik yönetimi' },
  { yol: '/veri', baslik: 'Nöbet ve Yayınlar', ikon: 'mdi-calendar-clock', aciklama: 'lastSystemData.json düzenleme' },
  { yol: '/cihazlar', baslik: 'Cihazlar', ikon: 'mdi-devices', aciklama: 'match.json — cihazın ilçe/bölge eşlemesi' },
  { yol: '/sablon', baslik: 'Şablon', ikon: 'mdi-file-code-outline', aciklama: 'sablon.json — veri şablonu' },
  { yol: '/gelismis', baslik: 'Gelişmiş', ikon: 'mdi-tune-variant', aciklama: 'JSON boyut/derinlik/düğüm sınırları (opsiyonel)' },
] as const

export interface OturumDurumu {
  hazir: boolean
  yapilandirmaHatasi: string | null
  girisYapildi: boolean
}

/**
 * Oturum kuralları:
 *  1. yapılandırma eksik/yer tutucu → /kurulum (beyaz ekran yerine yönlendirme),
 *  2. giriş yapılmamış → /giris,
 *  3. giriş yapılmışken /giris → /durum.
 */
export function rotaIzni(
  yol: { name?: unknown; meta?: { genel?: unknown } },
  durum: OturumDurumu,
): true | { name: string } {
  if (!durum.hazir) return true
  if (durum.yapilandirmaHatasi) return yol.name === 'kurulum' ? true : { name: 'kurulum' }
  if (!durum.girisYapildi && !yol.meta?.genel) return { name: 'giris' }
  if (durum.girisYapildi && yol.name === 'giris') return { name: 'durum' }
  return true
}
