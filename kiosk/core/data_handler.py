"""Veri işleyici: lastupdate kontrolü -> match ile yer bulma -> ekran listesi.

AKIŞ (kullanıcı spec'i)
-----------------------
1. `lastupdate.json` okunur. Cihazın sakladığı değerden farklıysa devam edilir;
   aynıysa veri yeniden yüklenmez (ekran gereksiz yere kurulmaz).
2. `lastSystemData.json` + `match.json` okunur.
3. `match.json` içinde bu cihazın clientID'si aranır -> ilçe/bölge kimlikleri.
4. Nöbet günü 08:30 kuralıyla seçilir; cihazın ilçesine/bölgesine
   (`config.KAPSAM`) ait kayıtlar ekranın beklediği düz listeye çevrilir.

EKRAN ALANLARI
--------------
Sol liste : eczane + tel
Orta kısım: eczane + tel + adres + adres_tarifi (ve nöbet tarih aralığı)
"""

from __future__ import annotations

import logging
from datetime import datetime

import config
import ayarlar
from core import onbellek, sync, veri_kaynagi
from core.sync import CihazKonumu
from security.veri_dogrulama import kimlik_ozeti, liste_sinirla, temiz_metin

log = logging.getLogger("kiosk.veri")


def kaydi_ekran_bicimine_cevir(kayit: dict) -> dict:
    """Şablondaki kaydı ekranın kullandığı alanlara çevirir.

    GÜVENLİK: sunucudan gelen metinler `temiz_metin` ile süzülür — denetim
    karakterleri ve çift yönlü yazı kontrolleri (U+202E ile görüntüyü ters
    çevirme) atılır, satır sonları sadeleştirilir, uzunluk sınırlanır.
    Ekranı yanıltacak/sıkıştıracak veri doğrudan gösterilemez.
    """
    sinir = getattr(config, "MAX_METIN_UZUNLUK", 160)
    return {
        "eczane": temiz_metin(kayit.get("eczane"), en_buyuk=80, tek_satir=True),
        "tel": temiz_metin(kayit.get("tel"), en_buyuk=32, tek_satir=True),
        "adres": temiz_metin(kayit.get("adres"), en_buyuk=sinir),
        "adres_tarifi": temiz_metin(kayit.get("adres_tarifi"), en_buyuk=sinir),
        "baslangic": temiz_metin(kayit.get("start") or kayit.get("baslangic"), en_buyuk=40, tek_satir=True),
        "bitis": temiz_metin(kayit.get("end") or kayit.get("bitis"), en_buyuk=40, tek_satir=True),
        "bolge": temiz_metin(kayit.get("bolge"), en_buyuk=80, tek_satir=True),
        "ilce": temiz_metin(kayit.get("ilce"), en_buyuk=80, tek_satir=True),
        "bolgeId": temiz_metin(kayit.get("bolgeId"), en_buyuk=32, tek_satir=True),
        "ilceId": temiz_metin(kayit.get("ilceId"), en_buyuk=32, tek_satir=True),
    }


class DataHandler:
    """Ekranın veri kaynağı (referans sınıf adı ve arayüzü korunur)."""

    def __init__(self, kapsam: str | None = None):
        self.pharmacies: list[dict] = []
        self.yayinlar: list[dict] = []
        self.nobet_gunu = ""
        self.konum = CihazKonumu()
        self.lastupdate = ""
        self.kapsam = (kapsam or getattr(config, "KAPSAM", "ilce")).lower()

    # ------------------------------------------------------------------ #
    def _onbellek_bakimi(self, damga: str) -> None:
        """Önbellek bakımı: damga değiştiyse geçersizleştir, süresi geçenleri sil.

        * `lastupdate` değişti → yayın görselleri "bayat" işaretlenir (bir kez tazelenir)
          ve günlüğe yazılır; veri önbelleği zaten damga ile geçersiz sayılır.
        * Veride artık geçmeyen ya da son gösterimi eskimiş görseller cihazdan silinir
          (yayının `end` alanı = son gösterim tarihi geçtikten sonra temizlenir).
        """
        if not onbellek.aktif():
            return
        try:
            if damga and onbellek.damgayi_kaydet(damga):
                gecerli = {
                    str(y.get("contentUrl") or y.get("contentURL") or "")
                    for y in self.yayinlar
                    if isinstance(y, dict)
                }
                gecerli.discard("")
                sayi = onbellek.gorselleri_bayat_isaretle(gecerli or None)
                log.info("veri değişti: önbellek geçersizleştirildi (%d görsel tazelenecek)", sayi)
            gecerli_url = {
                str(y.get("contentUrl") or y.get("contentURL") or "")
                for y in self.yayinlar
                if isinstance(y, dict)
            }
            gecerli_url.discard("")
            # Boş küme = "veri yüklenemedi/henüz yok" olabilir: o durumda artık-temizliği
            # ATLA (yanlışlıkla tüm görsel önbelleğini silip gereksiz indirmeye yol açmasın).
            # Süre bazlı temizlik (son gösterim + saklama günü) her hâlükârda çalışır.
            ozet = onbellek.bakim(gecerli_url_kumesi=gecerli_url or None)
            if ozet.get("silinen") or ozet.get("oksuz_dosya"):
                log.info(
                    "önbellek bakımı: %d görsel silindi (%.1f MB), %d öksüz dosya; kalan %.1f MB",
                    ozet.get("silinen", 0),
                    ozet.get("silinen_bayt", 0) / 1024 / 1024,
                    ozet.get("oksuz_dosya", 0),
                    ozet.get("kalan_bayt", 0) / 1024 / 1024,
                )
        except Exception:  # bakım hiçbir zaman veri yüklemeyi engellememeli
            log.warning("önbellek bakımı yapılamadı", exc_info=True)

    # ------------------------------------------------------------------ #
    @property
    def kaynak_ozeti(self) -> dict:
        return {
            "nobet_gunu": self.nobet_gunu,
            "ilce": self.konum.ilce,
            "ilceId": self.konum.ilce_id,
            "bolge": self.konum.bolge,
            "bolgeId": self.konum.bolge_id,
            "lastupdate": self.lastupdate,
            "kapsam": self.kapsam,
            "kayit": len(self.pharmacies),
        }

    def load_data(self, zorla: bool = False) -> bool:
        """Saatte bir çağrılır: lastupdate değiştiyse veriyi yeniler.

        `zorla=True` → damga değişmemiş olsa da yeniler (panel tetikleyicisi bu yolu kullanır:
        nöbet değişikliği aynı damgayla gelebilir).
        """
        yeni_damga = sync.lastupdate_oku(veri_kaynagi.lastupdate_yukle())
        if not zorla and not sync.degisti_mi(yeni_damga, self.lastupdate) and self.pharmacies:
            log.debug("lastupdate değişmedi (%s); veri yenilenmedi", yeni_damga)
            return True
        if zorla:
            # tetikleyici: damga değişmemiş olsa da kaynağı tazele (panel veriyi güncelledi)
            onbellek.veri_temizle(config.SISTEM_VERISI_DOSYASI)
            log.info("veri ZORLA yenileniyor (tetikleyici)")

        sistem_verisi = veri_kaynagi.sistem_verisi_yukle()
        if not isinstance(sistem_verisi, dict):
            log.error("nöbet verisi okunamadı (%s)", config.SISTEM_VERISI_DOSYASI)
            return False

        match = veri_kaynagi.match_yukle()
        client = veri_kaynagi.client_id()
        konum = sync.cihaz_konumunu_bul(match, client)
        if not konum.bulundu:
            log.error(
                "cihaz kimliği (%s) match.json içinde bulunamadı; gösterilecek veri yok",
                kimlik_ozeti(client) if getattr(config, "LOG_CLIENT_ID_GIZLE", True) else client,
            )
            return False
        konum = sync.konum_adlarini_bul(sistem_verisi, konum)

        # Kapsam (ilçe/bölge/cihaz) bazlı özellik ayarları: en özel kapsam kazanır
        kapsam_ozeti = ayarlar.kapsam_uygula(
            ilce_id=konum.ilce_id, bolge_id=konum.bolge_id, client_id=client
        )
        if kapsam_ozeti.get("uygulanan"):
            log.info("kapsam ayarları: %s", "; ".join(kapsam_ozeti["uygulanan"]))

        anahtar, kayitlar = sync.gosterilecek_kayitlar(sistem_verisi, konum, kapsam=self.kapsam)
        self.nobet_gunu = anahtar
        self.konum = konum
        self.lastupdate = yeni_damga
        # Kayıt sayısı sınırlanır: bozuk/aşırı veri ekranı kilitlemesin
        kayitlar = liste_sinirla(
            kayitlar, en_buyuk=getattr(config, "MAX_GOSTERILEN_ECZANE", 60), etiket="nöbet kaydı"
        )
        self.pharmacies = sorted(
            (kaydi_ekran_bicimine_cevir(k) for k in kayitlar),
            key=lambda s: (s["bolge"].upper(), s["eczane"].upper()),
        )

        yayinlar = sistem_verisi.get("Yayinlar", {})
        if isinstance(yayinlar, dict):
            havuz = [
                yayinlar[k] for k in sorted(yayinlar.keys(), key=lambda x: int(x) if x.isdigit() else -1)
            ]
            self.yayinlar = liste_sinirla(havuz, en_buyuk=getattr(config, "MAX_AKTIF_YAYIN", 20) * 10, etiket="yayın")
        else:
            self.yayinlar = []

        self._onbellek_bakimi(yeni_damga)

        if not self.pharmacies:
            log.error(
                "cihazın bölgesi için nöbet kaydı yok (ilçe=%s bölge=%s, anahtar=%s)",
                konum.ilce or konum.ilce_id,
                konum.bolge or konum.bolge_id,
                anahtar,
            )
            return False

        log.info(
            "veri yüklendi: %s · %s / %s · %d nöbetçi eczane · %d yayın (lastupdate=%s)",
            anahtar,
            konum.ilce,
            konum.bolge,
            len(self.pharmacies),
            len(self.yayinlar),
            yeni_damga or "-",
        )
        return True
