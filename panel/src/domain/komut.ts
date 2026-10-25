/**
 * `komut.json` — panelde SON UZAKTAN KOMUTUN gösterimi (kullanıcı kararı, 25 Ekim).
 *
 * Panel komut GÖNDERMEZ (istemcide HMAC anahtarı tutulmaz; gönderim `kiosk/tools/
 * komut_gonder.py` ya da sunucu tarafı Lambda ile yapılır). Buradaki iş, kovadaki
 * `komut.json`u okuyup "cihaza ne gönderilmiş, cihaz bunu kabul eder mi?" sorusunu
 * yanıtlamaktır.
 *
 * Cihaz kuralları (`kiosk/core/komut.py`) ile AYNI beyaz liste kullanılır; imza
 * DOĞRULANAMAZ (anahtar yalnız cihazda) — bu yüzden "imza var/yok" denir, "geçerli" DENMEZ.
 */

/** Cihazın kabul ettiği komut adları (`kiosk/core/komut.py::IZINLI_KOMUTLAR`). */
export const IZINLI_KOMUTLAR = ['yeniden-baslat', 'uygulamayi-yeniden-baslat', 'ekrani-yenile'] as const

/** Komutun "taze" sayıldığı süre: bundan eskisi cihazda zaten uygulanmış olmalı. */
export const KOMUT_ESKI_SAAT = 24

export interface KomutOzeti {
  varMi: boolean
  id: string
  komut: string
  /** `''` ya da `*` = tüm cihazlar */
  hedef: string
  zaman: string
  /** imza alanı dolu mu (geçerliliği panel doğrulayamaz) */
  imzali: boolean
  /** cihazın kural setine göre kabul edilir mi (imza doğrulanamadığı için "engel yok" anlamında) */
  engelYok: boolean
  uyarilar: string[]
}

const metin = (deger: unknown): string => (typeof deger === 'string' ? deger.trim() : '')

/**
 * `komut.json` gövdesini panel için özete çevirir.
 *
 * @param cihazId panelde görüntülenen cihazın kimliği (verilirse hedef uyuşmazlığı uyarısı eklenir)
 * @param simdi yaş hesabı için "şimdi" (test edilebilirlik)
 */
export function komutOzeti(belge: unknown, cihazId = '', simdi: Date = new Date()): KomutOzeti {
  const uyarilar: string[] = []
  if (!belge || typeof belge !== 'object' || Array.isArray(belge)) {
    return {
      varMi: false,
      id: '',
      komut: '',
      hedef: '',
      zaman: '',
      imzali: false,
      engelYok: false,
      uyarilar: ['komut.json yok ya da bir nesne değil (cihaz komut almıyor).'],
    }
  }
  const belgeNesne = belge as Record<string, unknown>
  const komut = metin(belgeNesne.komut).toLowerCase()
  const id = metin(belgeNesne.id)
  const hedef = metin(belgeNesne.cihazId)
  const zaman = metin(belgeNesne.zaman)
  const imzali = Boolean(metin(belgeNesne.imza))

  if (!komut) uyarilar.push('komut adı boş — cihaz bu dosyayı yok sayar.')
  else if (!(IZINLI_KOMUTLAR as readonly string[]).includes(komut))
    uyarilar.push(`"${komut}" beyaz listede değil — cihaz reddeder ve günlüğe yazar.`)

  // Cihaz kimliği olmayan komutu reddeder (tekrar engeli kurulamaz).
  if (!id) uyarilar.push('komut kimliği (id) yok — cihaz reddeder (tekrar engeli kurulamaz).')

  // Cihaz imza denetimini `calistirma.komut_imza_zorunlu` ayarından okur (varsayılan true;
  // bu anahtar cihaza özgüdür ve yayınla değiştirilemez). Metin koşullu olmalı: ayar kapatılmış
  // bir cihazda "uygulanmaz" demek yanlış olurdu.
  if (!imzali)
    uyarilar.push(
      'imza alanı yok — cihazda imza zorunluysa (varsayılan) uygulanmaz; göndermeden önce imzalayın.',
    )

  if (hedef && hedef !== '*' && cihazId && hedef !== cihazId)
    uyarilar.push(`komut başka cihaz için (${hedef}); bu cihaz uygulamaz.`)

  const yas = komutYasiSaat(zaman, simdi)
  if (yas !== null && yas > KOMUT_ESKI_SAAT)
    uyarilar.push(`komut ${Math.round(yas)} saat önce gönderilmiş; cihaz uyguladıysa tekrar uygulamaz (tek seferlik).`)

  return {
    varMi: true,
    id,
    komut,
    hedef,
    zaman,
    imzali,
    engelYok: uyarilar.length === 0,
    uyarilar,
  }
}

/** Komutun yaşı (saat) — zaman okunamıyorsa `null`. */
export function komutYasiSaat(zaman: string, simdi: Date = new Date()): number | null {
  const t = Date.parse(zaman)
  if (!Number.isFinite(t)) return null
  const fark = (simdi.getTime() - t) / 3_600_000
  return fark < 0 ? 0 : fark
}

/** Hedefin okunur adı. */
export function hedefMetni(hedef: string): string {
  if (!hedef || hedef === '*') return 'tüm cihazlar'
  return hedef
}
