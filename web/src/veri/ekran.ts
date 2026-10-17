/**
 * EKRAN BİÇİMİ — Qt `data_handler.kaydi_ekran_bicimine_cevir` + `utils` ile aynı kurallar.
 *
 * Metin temizliği kritik: panel/kiosk/web üçü de aynı metni göstermelidir. `temizMetin`
 * NFC normalleştirir, bidi/denetim karakterlerini atar, satır sonlarını boşluğa çevirir,
 * boşlukları sadeleştirir ve sınırı aşarsa "…" ile kısaltır.
 */
import { tarihCoz, type CihazKonumu, type NobetKaydi } from './nobet'
import { formatTelefon } from './kusak'

const DENETIM_KARAKTERLERI = /[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]/g

/** Qt `veri_dogrulama.temiz_metin` ile aynı temizlik (tek satır, NFC, kısaltma). */
export function temizMetin(deger: unknown, azami = 160): string {
  if (deger === null || deger === undefined) return ''
  const ham = String(deger).normalize('NFC').replace(DENETIM_KARAKTERLERI, ' ')
  const tek = ham.replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  if (azami > 0 && tek.length > azami) return `${tek.slice(0, Math.max(1, azami - 1)).trimEnd()}…`
  return tek
}

/** Alan sınırları (Qt: eczane/tel/bölge/ilçe 80-32, adres 160, start/end 40). */
export const ALAN_SINIRLARI = {
  eczane: 80,
  ikincil: 32,
  bolge: 80,
  ilce: 80,
  adres: 160,
  tarih: 40,
} as const

/** Ekranda kullanılan kayıt biçimi (Qt `kaydi_ekran_bicimine_cevir`). */
export interface EkranKaydi {
  eczane: string
  tel: string
  ikincil: string
  adres: string
  adresTarifi: string
  bolge: string
  ilce: string
  start: string
  end: string
  ham: NobetKaydi
}

/** Ham nöbet kaydını ekran biçimine çevirir (temizlik + sınırlar). */
export function kaydiEkranBicimineCevir(kayit: NobetKaydi, eksikTelefonYerineBolge = true): EkranKaydi {
  const eczane = temizMetin(kayit.eczane, ALAN_SINIRLARI.eczane)
  const bolge = temizMetin(kayit.bolge, ALAN_SINIRLARI.bolge)
  const ilce = temizMetin(kayit.ilce, ALAN_SINIRLARI.ilce)
  const telHam = temizMetin(kayit.tel, ALAN_SINIRLARI.ikincil)
  const tel = formatTelefon(telHam)
  let ikincil = tel
  if ((!tel || tel === '-') && eksikTelefonYerineBolge) ikincil = bolge || '-'
  return {
    eczane,
    tel,
    ikincil,
    adres: temizMetin(kayit.adres, ALAN_SINIRLARI.adres),
    adresTarifi: temizMetin(kayit.adres_tarifi, ALAN_SINIRLARI.adres),
    bolge,
    ilce,
    start: temizMetin(kayit.start ?? kayit.baslangic, ALAN_SINIRLARI.tarih),
    end: temizMetin(kayit.end ?? kayit.bitis, ALAN_SINIRLARI.tarih),
    ham: kayit,
  }
}

/** "15.10.26 08:30:00" biçimi (Qt: `%d.%m.%y %H:%M:%S`). */
export function tarihMetni(deger: unknown): string {
  const tarih = tarihCoz(deger)
  if (!tarih) return '-'
  const iki = (n: number): string => String(n).padStart(2, '0')
  return (
    `${iki(tarih.getDate())}.${iki(tarih.getMonth() + 1)}.${String(tarih.getFullYear()).slice(2)} ` +
    `${iki(tarih.getHours())}:${iki(tarih.getMinutes())}:${iki(tarih.getSeconds())}`
  )
}

/** Orta paneldeki tarih aralığı etiketi (Qt `_nobet_araligi_metni`). */
export function tarihAralikMetni(kayit: EkranKaydi | NobetKaydi): string {
  const bas = tarihMetni((kayit as EkranKaydi).start ?? (kayit as NobetKaydi).start)
  const bit = tarihMetni((kayit as EkranKaydi).end ?? (kayit as NobetKaydi).end)
  if (bas === '-' || bit === '-') return '-'
  return `${bas} - ${bit} TARİHLER ARASI NÖBETÇİ!`
}

/** Orta paneldeki adres bloğu: adres + (varsa) adres tarifi, büyük harf (Qt). */
export function adresMetni(kayit: EkranKaydi): string {
  const parcalar = [kayit.adres, kayit.adresTarifi].filter((p) => p)
  return parcalar.join('\n').toUpperCase()
}

/**
 * `match.json` içinden cihazın ilçesi/bölgesi (Qt `sync.cihaz_konumunu_bul`).
 *
 * Yapı: `{ "<ilceId>": [ { "<bolgeId>": ["makine1", "makine2"] } ] }` (`lastupdate` atlanır)
 */
export function cihazKonumunuBul(
  match: Record<string, unknown> | null | undefined,
  clientId: string,
): CihazKonumu {
  const kimlik = String(clientId ?? '').trim()
  const sonuc: CihazKonumu = { bulundu: false }
  if (!match || !kimlik) return sonuc
  for (const [ilceId, ilceListesi] of Object.entries(match)) {
    if (ilceId.toLowerCase() === 'lastupdate' || !Array.isArray(ilceListesi)) continue
    for (const kutu of ilceListesi) {
      if (!kutu || typeof kutu !== 'object') continue
      for (const [bolgeId, makineler] of Object.entries(kutu as Record<string, unknown>)) {
        if (!Array.isArray(makineler)) continue
        if (makineler.some((m) => String(m) === kimlik)) {
          return { ilceId: String(ilceId), bolgeId: String(bolgeId), bulundu: true }
        }
      }
    }
  }
  return sonuc
}
