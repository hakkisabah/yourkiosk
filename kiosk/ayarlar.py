"""Çalışma zamanı ayarları: `ayarlar.json` → `config` (yönetim paneline hazır).

NEDEN
-----
Proje açık kaynak ve genel amaçlı: ekranı kullanan kişi/kurum eczane olmayabilir
(ör. yalnızca görsel yayını yapmak isteyen biri nöbet listesini ve kayan yazıyı
kapatmak ister). Ayrıca veri hacmi büyüyebilir (20–30 MB JSON) → JSON boyut/derinlik/
düğüm gibi sınırlar **gelişmiş** ayar olarak dışarıdan verilebilmelidir.

TASARIM
-------
* `config.py` **varsayılanların** yeridir; `ayarlar.json` yalnızca verilen anahtarları
  geçersiz kılar. Dosya yoksa davranış aynen bugünkü gibidir.
* Dosya okuması da güvenlik kapısından geçer (boyut/derinlik/düğüm) — ayar dosyası bir
  saldırı vektörü olmasın; içerik tip/boyut denetiminden sonra `config`'e yazılır.
* Her anahtarın **aralığı** vardır: panelden yanlışlıkla 0 veya 10 GB girilirse
  değer sessizce kabul edilmez, gerekçesiyle birlikte varsayılana düşer.
* `yaz()` atomik yazar (0600) — yönetim paneli bunu kullanacak.
"""

from __future__ import annotations

import logging
from pathlib import Path

import config
from security.veri_dogrulama import VeriHatasi, atomik_yaz, json_yukle

log = logging.getLogger("kiosk.ayarlar")

AYARLAR_DOSYASI = "ayarlar.json"
EN_BUYUK_AYAR_BAYT = 256 * 1024

#: (grup, anahtar) -> (config adı, tip, alt sınır, üst sınır)
#: tip: bool | int | float | str | "secim" (izinli değerler) | "liste" | "sayi_listesi"
KURALLAR: dict[tuple[str, str], tuple] = {
    # ---- özellikler (aç/kapa) ----
    ("ozellikler", "nobet_listesi"): ("OZELLIK_NOBET_LISTESI", bool, None, None),
    ("ozellikler", "yayinlar"): ("OZELLIK_YAYINLAR", bool, None, None),
    ("ozellikler", "kayan_yazi"): ("OZELLIK_KAYAN_YAZI", bool, None, None),
    ("ozellikler", "saat_tarih"): ("OZELLIK_SAAT_TARIH", bool, None, None),
    # ---- kuşak (kayan yazı) ----
    ("kusak", "yukseklik"): ("KUSAK_YUKSEKLIK", int, 20, 400),
    ("kusak", "alt_bosluk"): ("KUSAK_ALT_BOSLUK", int, 0, 400),
    ("kusak", "yazi_punto"): ("KUSAK_YAZI_PUNTO", int, 8, 160),
    ("kusak", "giris_ms"): ("KUSAK_GIRIS_MS", int, 100, 20000),
    ("kusak", "durma_ms"): ("KUSAK_DURMA_MS", int, 0, 60000),
    ("kusak", "cikis_ms"): ("KUSAK_CIKIS_MS", int, 100, 20000),
    ("kusak", "hiz"): ("KUSAK_HIZ", int, 1, 100),
    ("kusak", "adim_araligi_ms"): ("KUSAK_ADIM_ARALIGI_MS", int, 5, 500),
    ("kusak", "tekli"): ("KUSAK_TEKLI", bool, None, None),
    # ---- görünüm ----
    ("gorunum", "sol_panel_satir"): ("MAKS_GORUNUR_SATIR", int, 1, 20),
    ("gorunum", "sol_panel_otomatik_kaydirma"): ("SOL_PANEL_OTOMATIK_KAYDIRMA", bool, None, None),
    ("gorunum", "sol_panel_kaydirma_sure_ms"): ("SOL_PANEL_KAYDIRMA_SURE_MS", int, 100, 10000),
    ("gorunum", "kaydirma_cubugu_genislik"): ("SOL_PANEL_KAYDIRMA_CUBUGU_GENISLIK", int, 0, 60),
    ("gorunum", "kaydirma_cubugu_renk"): ("SOL_PANEL_KAYDIRMA_CUBUGU_RENK", str, 0, 16),
    ("gorunum", "kaydirma_tutamak_renk"): ("SOL_PANEL_KAYDIRMA_TUTAMAK_RENK", str, 0, 16),
    # ---- veri kaynağı ----
    ("veri", "kaynak"): ("KAYNAK", "secim", ("dosya", "https"), None),
    ("veri", "dosya_adresi"): ("DOSYA_ADRESI", str, 0, 2048),
    # ---- ağ ----
    ("ag", "izinli_hostlar"): ("ALLOWED_HOSTS", "liste", None, None),
    ("ag", "izinli_portlar"): ("AG_IZINLI_PORTLAR", "sayi_listesi", 1, 65535),
    ("ag", "yonlendirme_izinli"): ("AG_YONLENDIRME_IZINLI", bool, None, None),
    ("ag", "http_timeout_s"): ("HTTP_TIMEOUT_S", float, 1, 300),
    # ---- çalıştırma modu (Qt / tarayıcı) ----
    ("calistirma", "mod"): ("CALISTIRMA_MODU", "secim", ("qt", "tarayici"), None),
    ("calistirma", "tarayici_yolu"): ("TARAYICI_YOLU", str, 1, 200),
    ("calistirma", "tarayici_ek_bayraklar"): ("TARAYICI_EK_BAYRAKLAR", str, 1, 500),
    ("calistirma", "profil_klasoru"): ("TARAYICI_PROFIL_KLASORU", str, 1, 64),
    ("calistirma", "pencere_boyutu"): ("TARAYICI_PENCERE_BOYUTU", str, 3, 20),
    ("calistirma", "yeniden_baslat_s"): ("TARAYICI_YENIDEN_BASLAT_S", int, 0, 3600),
    ("calistirma", "web_klasoru"): ("WEB_KLASORU", str, 1, 64),
    ("calistirma", "web_sunucu_adresi"): ("WEB_SUNUCU_ADRESI", str, 3, 64),
    ("calistirma", "web_sunucu_portu"): ("WEB_SUNUCU_PORTU", int, 1024, 65535),
    ("calistirma", "web_veri_modu"): ("WEB_VERI_MODU", "secim", ("yerel", "https"), None),
    ("calistirma", "web_yenileme_ms"): ("WEB_YENILEME_MS", int, 5000, 3600000),
    # ---- nöbet değişikliğini anında yansıtma (tetikleyici) ----
    ("calistirma", "degisiklik_kontrol_ms"): ("DAMGA_KONTROL_MS", int, 5000, 3600000),
    ("calistirma", "degisiklik_bekleme_s"): ("DEGISIKLIK_BEKLEME_S", int, 0, 120),
    ("calistirma", "tetik_dosyasi"): ("TETIK_DOSYASI", str, 1, 64),
    # ---- uzaktan komut (S3 → cihaz) ----
    ("calistirma", "komut_imza_zorunlu"): ("KOMUT_IMZA_ZORUNLU", bool, None, None),
    ("calistirma", "komut_kuru_calistirma"): ("KOMUT_KURU_CALISTIRMA", bool, None, None),
    ("calistirma", "komut_zaman_asimi_s"): ("KOMUT_ZAMAN_ASIMI_S", int, 1, 3600),
    ("calistirma", "komut_yeniden_baslat"): ("KOMUT_YENIDEN_BASLAT", str, 0, 200),
    ("calistirma", "komut_uygulama_yeniden_baslat"): ("KOMUT_UYGULAMA_YENIDEN_BASLAT", str, 0, 200),
    ("calistirma", "komut_ekrani_yenile"): ("KOMUT_EKRANI_YENILE", str, 0, 200),
    # ---- önbellek (maliyet + performans) ----
    ("onbellek", "aktif"): ("ONBELLEK_AKTIF", bool, None, None),
    ("onbellek", "klasor"): ("ONBELLEK_KLASORU", str, 1, 64),
    ("onbellek", "maks_bayt"): ("ONBELLEK_MAKS_BAYT", int, 8 * 1024 * 1024, 64 * 1024 * 1024 * 1024),
    ("onbellek", "gorsel_saklama_gun"): ("ONBELLEK_GORSEL_SAKLAMA_GUN", int, 0, 365),
    ("onbellek", "veri_lastupdate_kullan"): ("ONBELLEK_VERI_LASTUPDATE_KULLAN", bool, None, None),
    ("onbellek", "gorsel_lastupdate_yeniler"): ("ONBELLEK_GORSEL_LASTUPDATE_YENILER", bool, None, None),
    # ---- gelişmiş (veri hacmi) ----
    ("gelismis", "max_json_bayt"): ("MAX_JSON_BAYT", int, 64 * 1024, 512 * 1024 * 1024),
    ("gelismis", "max_json_derinlik"): ("MAX_JSON_DERINLIK", int, 4, 256),
    ("gelismis", "max_json_dugum"): ("MAX_JSON_DUGUM", int, 1000, 50_000_000),
    ("gelismis", "max_gorsel_bayt"): ("MAX_GORSEL_BAYT", int, 64 * 1024, 128 * 1024 * 1024),
    ("gelismis", "max_gorsel_piksel"): ("MAX_GORSEL_PIKSEL", int, 16_384, 100_000_000),
    ("gelismis", "max_metin_uzunluk"): ("MAX_METIN_UZUNLUK", int, 20, 4096),
    ("gelismis", "max_gosterilen_kayit"): ("MAX_GOSTERILEN_ECZANE", int, 1, 5000),
    ("gelismis", "max_aktif_yayin"): ("MAX_AKTIF_YAYIN", int, 1, 1000),
    ("gelismis", "yayin_sure_en_az_s"): ("YAYIN_SURE_EN_AZ_S", int, 1, 3600),
    ("gelismis", "yayin_sure_en_cok_s"): ("YAYIN_SURE_EN_COK_S", int, 1, 3600),
}

#: Açıklamalar (panel ve raporlar için)
ACIKLAMALAR: dict[str, str] = {
    "ozellikler.nobet_listesi": "Nöbet listesi + detay ekranı gösterilsin mi",
    "ozellikler.yayinlar": "Yayın (görsel) moduna geçilsin mi",
    "ozellikler.kayan_yazi": "Yayın görünümünde alt kırmızı kuşak/kayan yazı gösterilsin mi",
    "ozellikler.saat_tarih": "Nöbet ekranındaki saat/tarih yazısı gösterilsin mi",
    "gorunum.sol_panel_satir": "Sol panelde satır yüksekliğinin hesaplandığı taban satır sayısı (az nöbetçide çerçeve büyümesin)",
    "gorunum.sol_panel_otomatik_kaydirma": "Sol panel vurgulanan nöbetçiyi otomatik takip etsin mi (satır alttan taşınca kaydırır)",
    "gorunum.sol_panel_kaydirma_sure_ms": "Sol panel kaydırma süresi (ms) — orta geçiş animasyonuyla aynı olması önerilir",
    "gorunum.kaydirma_cubugu_genislik": "Sol panel kaydırma çubuğu genişliği (px, 0 = gizli)",
    "gorunum.kaydirma_cubugu_renk": "Kaydırma çubuğu rayının rengi (#rrggbb)",
    "gorunum.kaydirma_tutamak_renk": "Kaydırma çubuğu tutamağının rengi (#rrggbb)",
    "calistirma.mod": "Gösterim modu: 'qt' (PyQt6 penceresi) veya 'tarayici' (Chromium kiosk)",
    "calistirma.tarayici_yolu": "Tarayıcı çalıştırılabilir dosyası (ör. chromium, chromium-browser, google-chrome)",
    "calistirma.tarayici_ek_bayraklar": "Chromium'a eklenecek ek bayraklar (boşlukla ayrılmış)",
    "calistirma.profil_klasoru": "Tarayıcı profili klasörü (kalıcı: görsel/HTTP önbelleği burada kalır)",
    "calistirma.pencere_boyutu": "Pencere boyutu (genişlik,yükseklik) — kiosk modunda yok sayılır",
    "calistirma.yeniden_baslat_s": "Tarayıcı kapanırsa kaç saniye sonra yeniden açılsın (0 = yeniden açma)",
    "calistirma.web_klasoru": "HTML/JS arayüzünün klasörü (proje kökü altında, ör. 'web')",
    "calistirma.web_sunucu_adresi": "Yerel sunucu adresi (varsayılan 127.0.0.1 — yalnızca cihazdan erişilir)",
    "calistirma.web_sunucu_portu": "Yerel sunucu portu",
    "calistirma.web_veri_modu": "Tarayıcı modunda veri kaynağı: 'yerel' (cihazdaki dosyalar) veya 'https' (DOSYA_ADRESI)",
    "calistirma.web_yenileme_ms": "Tarayıcının veriyi yeniden kontrol etme aralığı (ms)",
    "onbellek.aktif": "Cihaz önbelleği açık mı (veri + yayın görselleri diskte tutulur, internet tasarrufu)",
    "onbellek.klasor": "Önbellek klasörü (proje kökü altında; sürüm kontrolüne girmez)",
    "onbellek.maks_bayt": "Önbelleğin toplam boyut üst sınırı (bayt) — aşılırsa en eski kullanılanlar silinir",
    "onbellek.gorsel_saklama_gun": "Son gösterimden sonra görsellerin kaç gün daha tutulacağı (süresi geçen yayınlar silinir)",
    "onbellek.veri_lastupdate_kullan": "`lastupdate` değişmediyse büyük veri dosyalarını ağdan yeniden çekme (yalnızca https kaynağında)",
    "onbellek.gorsel_lastupdate_yeniler": "Veri değiştiğinde görselleri bir kez tazele (aynı adresteki içerik değişmiş olabilir)",
    "gelismis.max_json_bayt": "JSON gövdesi üst sınırı (bayt) — büyük veri için yükseltin",
    "gelismis.max_json_derinlik": "JSON iç içe geçme derinliği üst sınırı (GELİŞMİŞ)",
    "gelismis.max_json_dugum": "JSON düğüm (anahtar+değer) sayısı üst sınırı (GELİŞMİŞ)",
    "gelismis.max_gosterilen_kayit": "Tek ekranda gösterilecek en fazla kayıt",
    "gelismis.max_aktif_yayin": "Aynı anda işlenecek en fazla yayın",
}

_uygulanan_yollar: set[str] = set()


# --------------------------------------------------------------- yardımcılar
def yol(dosya: str | Path | None = None, kok: Path | None = None) -> Path:
    kok = Path(kok) if kok else Path(__file__).resolve().parent
    return (kok / dosya) if dosya else (kok / getattr(config, "AYARLAR_DOSYASI", AYARLAR_DOSYASI))


def ozellik(ad: str, varsayilan: bool = True) -> bool:
    """Özellik bayrağını config'ten okur (`OZELLIK_<AD>`)."""
    return bool(getattr(config, f"OZELLIK_{ad.upper()}", varsayilan))


def _deger_dogrula(tip, deger, alt, ust, anahtar: str):
    """Tek bir değeri doğrular; geçersizse (None, sebep) döner."""
    if tip is bool:
        if not isinstance(deger, bool):
            return None, f"{anahtar}: mantıksal değer (true/false) bekleniyordu"
        return deger, ""
    if tip is int:
        if isinstance(deger, bool) or not isinstance(deger, (int, float, str)):
            return None, f"{anahtar}: sayı bekleniyordu"
        try:
            sayi = int(float(deger))
        except (TypeError, ValueError):
            return None, f"{anahtar}: sayıya çevrilemedi"
        if alt is not None and sayi < alt:
            return None, f"{anahtar}: {sayi} alt sınırın altında (en az {alt})"
        if ust is not None and sayi > ust:
            return None, f"{anahtar}: {sayi} üst sınırın üstünde (en çok {ust})"
        return sayi, ""
    if tip is float:
        try:
            sayi = float(deger)
        except (TypeError, ValueError):
            return None, f"{anahtar}: ondalık sayı bekleniyordu"
        if alt is not None and sayi < alt:
            return None, f"{anahtar}: {sayi} alt sınırın altında (en az {alt})"
        if ust is not None and sayi > ust:
            return None, f"{anahtar}: {sayi} üst sınırın üstünde (en çok {ust})"
        return sayi, ""
    if tip is str:
        if not isinstance(deger, str):
            return None, f"{anahtar}: metin bekleniyordu"
        if ust is not None and len(deger) > ust:
            return None, f"{anahtar}: metin çok uzun (en çok {ust} karakter)"
        return deger.strip(), ""
    if tip == "secim":
        if not isinstance(deger, str) or deger not in alt:
            return None, f"{anahtar}: yalnızca {alt} değerlerinden biri olabilir"
        return deger, ""
    if tip == "liste":
        if not isinstance(deger, list) or not all(isinstance(x, str) and x.strip() for x in deger):
            return None, f"{anahtar}: metin listesi bekleniyordu"
        return tuple(x.strip() for x in deger), ""
    if tip == "sayi_listesi":
        if not isinstance(deger, list):
            return None, f"{anahtar}: sayı listesi bekleniyordu"
        sayilar = []
        for x in deger:
            try:
                sayi = int(x)
            except (TypeError, ValueError):
                return None, f"{anahtar}: listede sayı olmayan değer var"
            if alt is not None and not (alt <= sayi <= (ust or 65535)):
                return None, f"{anahtar}: {sayi} geçerli aralıkta değil"
            sayilar.append(sayi)
        return tuple(sayilar), ""
    return None, f"{anahtar}: bilinmeyen tip"


# ---------------------------------------------------------------- okuma/uygulama
def oku(dosya: str | Path | None = None, kok: Path | None = None) -> dict:
    """`ayarlar.json` içeriğini okur (yoksa boş sözlük). Güvenlik kapısından geçer."""
    hedef = yol(dosya, kok)
    if not hedef.is_file():
        return {}
    try:
        ham = hedef.read_bytes()
        belge = json_yukle(
            ham,
            etiket=hedef.name,
            en_buyuk_bayt=EN_BUYUK_AYAR_BAYT,
            en_buyuk_derinlik=16,
            en_buyuk_dugum=20_000,
        )
    except (OSError, VeriHatasi) as hata:
        log.error("ayar dosyası okunamadı (%s): %s", hedef, hata)
        return {}
    if not isinstance(belge, dict):
        log.error("ayar dosyası sözlük değil (%s); yok sayıldı", hedef)
        return {}
    return belge


def varsayilan_belge() -> dict:
    """Etkin (varsayılan ya da uygulanmış) değerlerden panel/örnek belge üretir."""
    belge: dict[str, dict] = {}
    for (grup, anahtar), (cfg_ad, _tip, _alt, _ust) in KURALLAR.items():
        deger = getattr(config, cfg_ad, None)
        if isinstance(deger, tuple):
            deger = list(deger)
        belge.setdefault(grup, {})[anahtar] = deger
        aciklama = ACIKLAMALAR.get(f"{grup}.{anahtar}")
        if aciklama:
            belge[grup][f"_{anahtar}_aciklama"] = aciklama
    return belge


def uygula(
    dosya: str | Path | None = None,
    kok: Path | None = None,
    *,
    zorla: bool = False,
) -> dict:
    """Ayar dosyasını `config`'e uygular; özet döner.

    `zorla=True` ise dosya zaten uygulanmış olsa da yeniden okunur (panel/test).
    """
    hedef = yol(dosya, kok)
    if str(hedef) in _uygulanan_yollar and not zorla:
        return {"uygulanan": [], "gecersiz": [], "yok_sayilan": [], "dosya": str(hedef), "atlandi": True}

    belge = oku(hedef)
    uygulanan: list[str] = []
    gecersiz: list[str] = []
    yok_sayilan: list[str] = []

    for (grup, anahtar), (cfg_ad, tip, alt, ust) in KURALLAR.items():
        grup_verisi = belge.get(grup)
        if not isinstance(grup_verisi, dict) or anahtar not in grup_verisi:
            yok_sayilan.append(f"{grup}.{anahtar}")
            continue
        deger, sebep = _deger_dogrula(tip, grup_verisi[anahtar], alt, ust, f"{grup}.{anahtar}")
        if deger is None:
            gecersiz.append(sebep)
            log.warning("ayar geçersiz, varsayılan kullanılacak — %s", sebep)
            continue
        setattr(config, cfg_ad, deger)
        uygulanan.append(f"{grup}.{anahtar}={deger}")

    # bilinmeyen gruplar/anahtarlar
    for grup, veri in belge.items():
        if grup.startswith("_"):
            continue
        if grup not in {g for g, _ in KURALLAR}:
            gecersiz.append(f"{grup}: bilinmeyen ayar grubu (yok sayıldı)")
            continue
        if not isinstance(veri, dict):
            continue
        for anahtar in veri:
            if anahtar.startswith("_"):
                continue
            if (grup, anahtar) not in KURALLAR:
                gecersiz.append(f"{grup}.{anahtar}: bilinmeyen anahtar (yok sayıldı)")

    tutarlilik = _tutarliligi_sagla()
    if uygulanan:
        log.info("ayarlar uygulandı (%d): %s", len(uygulanan), ", ".join(uygulanan))
    _uygulanan_yollar.add(str(hedef))
    return {
        "uygulanan": uygulanan,
        "gecersiz": gecersiz,
        "yok_sayilan": yok_sayilan,
        "tutarlilik": tutarlilik,
        "dosya": str(hedef),
    }


def _tutarliligi_sagla() -> list[str]:
    """Anlamsız kombinasyonları düzeltir (panelden yanlış girilmesin)."""
    uyarilar: list[str] = []
    nobet = ozellik("nobet_listesi")
    yayin = ozellik("yayinlar")
    kusak = ozellik("kayan_yazi")
    if not nobet and not yayin:
        config.OZELLIK_NOBET_LISTESI = True
        uyarilar.append(
            "nobet_listesi ve yayinlar ikisi de kapalı olamaz: nöbet listesi yeniden açıldı"
        )
    if not yayin and kusak:
        uyarilar.append("yayinlar kapalıyken kayan_yazi görünmez (kuşak yalnızca yayın görünümünde)")
    if getattr(config, "YAYIN_SURE_EN_AZ_S", 1) > getattr(config, "YAYIN_SURE_EN_COK_S", 60):
        config.YAYIN_SURE_EN_COK_S = config.YAYIN_SURE_EN_AZ_S
        uyarilar.append("yayın süresi alt sınırı üst sınırdan büyüktü: üst sınır = alt sınır")
    if getattr(config, "KUSAK_GIRIS_MS", 1) <= 0 or getattr(config, "KUSAK_CIKIS_MS", 1) <= 0:
        uyarilar.append("kuşak giriş/çıkış süresi sıfır olamaz (varsayılan kullanılır)")
    for uyari in uyarilar:
        log.warning("ayar tutarlılığı: %s", uyari)
    return uyarilar


def yaz(belge: dict | None = None, dosya: str | Path | None = None, kok: Path | None = None) -> Path:
    """Ayarları diske atomik yazar (yönetim panelinin kullanacağı yol)."""
    hedef = yol(dosya, kok)
    atomik_yaz(hedef, belge if belge is not None else varsayilan_belge(), mod=0o600)
    log.info("ayarlar yazıldı: %s", hedef)
    return hedef


# ============================================================================
#  KAPSAM AYARLARI (ilçe / bölge / cihaz bazında özellik yönetimi)
# ============================================================================
# Dosya (`kapsam-ayarlari.json`), yönetim panelinin yazdığı ikinci ayar dosyasıdır:
#
#   {
#     "varsayilan": { <ayarlar.json ile aynı gruplar> },
#     "ilceler":  { "<ilceId>":  { ... } },
#     "bolgeler": { "<bolgeId>": { ... } },
#     "cihazlar": { "<clientID>": { ... } }
#   }
#
# Çözümleme sırası (en özel kazanır): varsayilan → ilce → bolge → cihaz.
# Gruplar ve anahtarlar `KAPSAM_GRUPLARI` ile sınırlıdır; bilinmeyen anahtar yok sayılır.
KAPSAM_GRUPLARI = ("ozellikler", "kusak", "gorunum", "gelismis", "onbellek")


def kapsam_belgesi(
    kok: Path | None = None,
    *,
    ilce_id: str = "",
    bolge_id: str = "",
    client_id: str = "",
    dosya: str | Path | None = None,
) -> dict:
    """Kapsam dosyasını okur ve cihaz için **birleştirilmiş** ayar belgesini döner."""
    hedef = yol(dosya or getattr(config, "KAPSAM_AYARLARI_DOSYASI", "kapsam-ayarlari.json"), kok)
    ham = oku(hedef)
    if not ham:
        return {}

    belge: dict[str, dict] = {}
    kaynak: dict[str, str] = {}

    def _birlestir(veri: object, etiket: str) -> None:
        if not isinstance(veri, dict):
            return
        for grup, icerik in veri.items():
            if grup not in KAPSAM_GRUPLARI or not isinstance(icerik, dict):
                continue
            for anahtar, deger in icerik.items():
                if anahtar.startswith("_"):
                    continue
                belge.setdefault(grup, {})[anahtar] = deger
                kaynak[f"{grup}.{anahtar}"] = etiket

    _birlestir(ham.get("varsayilan"), "varsayilan")
    if ilce_id:
        _birlestir((ham.get("ilceler") or {}).get(ilce_id), f"ilce:{ilce_id}")
    if bolge_id:
        _birlestir((ham.get("bolgeler") or {}).get(bolge_id), f"bolge:{bolge_id}")
    if client_id:
        _birlestir((ham.get("cihazlar") or {}).get(client_id), f"cihaz:{client_id}")

    if belge:
        belge["_kaynak"] = kaynak  # hangi değerin hangi kapsamdan geldiği
    return belge


def kapsam_uygula(
    kok: Path | None = None,
    *,
    ilce_id: str = "",
    bolge_id: str = "",
    client_id: str = "",
    dosya: str | Path | None = None,
) -> dict:
    """Kapsam ayarlarını doğrulayıp `config`'e uygular; özet döner.

    Doğrulama `uygula()` ile **aynı** kuralları kullanır: aralık dışı/yanlış tip
    kabul edilmez, gerekçesi günlüğe yazılır ve varsayılan korunur.
    """
    belge = kapsam_belgesi(kok, ilce_id=ilce_id, bolge_id=bolge_id, client_id=client_id, dosya=dosya)
    if not belge:
        return {"uygulanan": [], "gecersiz": [], "kapsam": {}, "atlandi": True}

    kaynak = belge.pop("_kaynak", {})
    uygulanan: list[str] = []
    gecersiz: list[str] = []
    for (grup, anahtar), (cfg_ad, tip, alt, ust) in KURALLAR.items():
        if grup not in KAPSAM_GRUPLARI or anahtar not in belge.get(grup, {}):
            continue
        deger, sebep = _deger_dogrula(tip, belge[grup][anahtar], alt, ust, f"{grup}.{anahtar}")
        if deger is None:
            gecersiz.append(sebep)
            log.warning("kapsam ayarı geçersiz, yok sayıldı — %s", sebep)
            continue
        setattr(config, cfg_ad, deger)
        uygulanan.append(f"{grup}.{anahtar}={deger} ({kaynak.get(f'{grup}.{anahtar}', '?')})")

    tutarlilik = _tutarliligi_sagla()
    if uygulanan:
        log.info(
            "kapsam ayarları uygulandı (%d) · ilçe=%s bölge=%s cihaz=%s",
            len(uygulanan),
            ilce_id or "-",
            bolge_id or "-",
            client_id or "-",
        )
    return {"uygulanan": uygulanan, "gecersiz": gecersiz, "tutarlilik": tutarlilik, "kapsam": kaynak}


def kapsam_ozeti(
    kok: Path | None = None,
    *,
    ilce_id: str = "",
    bolge_id: str = "",
    client_id: str = "",
    dosya: str | Path | None = None,
) -> dict:
    """Panel/teşhis için: her anahtarın hangi kapsamdan geldiği + etkin değeri."""
    belge = kapsam_belgesi(kok, ilce_id=ilce_id, bolge_id=bolge_id, client_id=client_id, dosya=dosya)
    kaynak = belge.pop("_kaynak", {})
    satirlar: dict[str, dict] = {}
    for (grup, anahtar), (cfg_ad, _tip, _alt, _ust) in KURALLAR.items():
        if grup not in KAPSAM_GRUPLARI:
            continue
        satirlar[f"{grup}.{anahtar}"] = {
            "etkin": getattr(config, cfg_ad, None),
            "kapsam": kaynak.get(f"{grup}.{anahtar}", "config (varsayılan)"),
        }
    return satirlar


def ozet() -> dict:
    """Etkin özellik ve sınır özeti (rapor/panel için)."""
    return {
        "dosya": str(yol()),
        "ozellikler": {ad: ozellik(ad) for ad in ("nobet_listesi", "yayinlar", "kayan_yazi", "saat_tarih")},
        "sinirlar": {
            "max_json_bayt": config.MAX_JSON_BAYT,
            "max_json_derinlik": config.MAX_JSON_DERINLIK,
            "max_json_dugum": config.MAX_JSON_DUGUM,
            "max_gosterilen_kayit": config.MAX_GOSTERILEN_ECZANE,
            "max_aktif_yayin": config.MAX_AKTIF_YAYIN,
        },
    }
