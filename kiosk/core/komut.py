"""UZAKTAN KOMUT (S3 → cihaz) — yeniden başlat / uygulamayı yeniden başlat / ekranı yenile.

KULLANIM AKIŞI
--------------
1. Yönetici imzalı bir komut dosyası üretir (`tools/komut_gonder.py`) ve S3'e koyar;
   cihaz bunu `komut.json` olarak indirir (veri akışının bir parçası — `tetikle.json` gibi).
2. Cihaz, `DAMGA_KONTROL_MS` aralığıyla (ya da başlangıçta) `kontrol()` çağırır:
   okur → doğrular → uygular → uygulanan komutu işaretler.

GÜVENLİK (fail-closed — hiçbir koşulda "serbest komut" çalıştırılmaz)
--------------------------------------------------------------------
* **Beyaz liste:** yalnız `IZINLI_KOMUTLAR` içindeki adlar kabul edilir; ad, `config.KOMUT_*`
  ile sabit bir **argv**'ye eşlenir. Kabuk (`shell=True`) KULLANILMAZ, kullanıcı metni
  komut olarak çalıştırılmaz.
* **İmza zorunlu:** HMAC-SHA256 (`KOMUT_IMZA_ZORUNLU = True`). İmza `id|komut|cihazId|zaman`
  üzerinden hesaplanır; anahtar cihazda `komut.anahtar` (0600) dosyasındadır. Anahtar yoksa
  ya da imza tutmuyorsa komut **uygulanmaz** ve günlüğe "reddedildi" yazılır.
* **Hedef cihaz:** `cihazId` boş/"*" → tüm cihazlar; doluysa yalnız o cihaz.
* **Tek seferlik:** uygulanan komut kimliği (`id`) `komut-durum.json`'a yazılır; aynı komut
  ikinci kez uygulanmaz (S3'te dosya unutulsa bile cihaz tekrar yeniden başlamaz).
* **Kuru çalıştırma:** `KOMUT_KURU_CALISTIRMA` (ya da `--kuru`) açıkken komut yalnız günlüklenir.
* **Zaman aşımı:** komut çalıştırılırken `KOMUT_ZAMAN_ASIMI_S` sonra zorla sonlandırılır.

ÖNEMLİ: `ekrani-yenile` komutu için argv BOŞ olabilir; bu durumda hiçbir süreç çalıştırılmaz,
çağıran uygulama ekranı kendi içinde tazeler (`Sonuc.uygulama_ici = True`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import config

log = logging.getLogger("kiosk.komut")

#: Çalıştırılmasına izin verilen komut adları (başka HİÇBİR ad kabul edilmez)
IZINLI_KOMUTLAR = ("yeniden-baslat", "uygulamayi-yeniden-baslat", "ekrani-yenile")

PROJE_KOK = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ yollar
def dosya_yolu() -> Path:
    return PROJE_KOK / str(getattr(config, "KOMUT_DOSYASI", "komut.json"))


def durum_yolu() -> Path:
    return PROJE_KOK / str(getattr(config, "KOMUT_DURUM_DOSYASI", "komut-durum.json"))


def anahtar_yolu() -> Path:
    return PROJE_KOK / str(getattr(config, "KOMUT_ANAHTAR_DOSYASI", "komut.anahtar"))


# ------------------------------------------------------------------ karar/sonuç tipleri
@dataclass(frozen=True)
class Karar:
    """Doğrulama sonucu."""

    kabul: bool
    sebep: str


@dataclass
class Sonuc:
    """Uygulama sonucu (günlük ve CLI için)."""

    id: str
    komut: str
    argv: list[str] = field(default_factory=list)
    uygulama_ici: bool = False
    kuru: bool = False
    cikis_kodu: int | None = None
    cikti: str = ""
    hata: str = ""
    zaman: str = ""

    def ozet(self) -> str:
        if self.kuru:
            return f"KURU: {self.komut} → {' '.join(self.argv) or '(uygulama içi)'}"
        if self.uygulama_ici:
            return f"{self.komut} → uygulama içi tazeleme istendi"
        if self.hata:
            return f"{self.komut} → HATA: {self.hata}"
        return f"{self.komut} → çıkış={self.cikis_kodu}"


# ------------------------------------------------------------------ imza
def anahtar_oku(yol: Path | None = None) -> bytes | None:
    """HMAC anahtarını okur (yoksa/boşsa None). Dosya izni kısıtlı olmalı (0600)."""
    hedef = yol or anahtar_yolu()
    try:
        ham = hedef.read_bytes().strip()
    except OSError:
        return None
    return ham or None


def kanonik(belge: dict) -> str:
    """İmzalanan metin: `id|komut|cihazId|zaman` (sıra SABİT, uygulama ve araç aynı kural)."""
    return "|".join(
        str(belge.get(alan, "") or "") for alan in ("id", "komut", "cihazId", "zaman")
    )


def imzala(belge: dict, anahtar: bytes) -> str:
    return hmac.new(anahtar, kanonik(belge).encode("utf-8"), hashlib.sha256).hexdigest()


def imza_dogrula(belge: dict, anahtar: bytes | None, zorunlu: bool = True) -> Karar:
    gelen = str(belge.get("imza", "") or "").strip().lower()
    if not gelen:
        if zorunlu:
            return Karar(False, "imza yok (zorunlu)")
        return Karar(True, "imzasız kabul (zorunlu değil)")
    if not anahtar:
        return Karar(False, "imza var ama cihazda anahtar yok (komut.anahtar)")
    beklenen = imzala(belge, anahtar)
    return Karar(True, "imza geçerli") if hmac.compare_digest(beklenen, gelen) else Karar(False, "imza geçersiz")


# ------------------------------------------------------------------ okuma / durum
def oku() -> dict | None:
    """`komut.json`u okur; yok/bozuksa/`komut` alanı yoksa None."""
    yol = dosya_yolu()
    try:
        if not yol.is_file():
            return None
        veri = json.loads(yol.read_bytes()[-4096:].decode("utf-8-sig"))
    except (OSError, ValueError):
        log.warning("komut dosyası okunamadı: %s", yol, exc_info=True)
        return None
    if not isinstance(veri, dict) or not str(veri.get("komut") or "").strip():
        return None
    return veri


def getir() -> bool:
    """Panelin/S3'ün yazdığı `komut.json`u yerel kopyaya indirir (değiştiyse True).

    KOŞULLU indirme (ETag/Last-Modified → 304): değişmeyen komut dosyası için gövde inmez.
    İndirme tek başına bir şey ÇALIŞTIRMAZ; komut ancak `dogrula` + `uygula` ile (imza ve beyaz
    liste denetiminden geçerek) uygulanır.
    """
    from core import uzak

    return uzak.kosullu_indir_ve_yaz(str(getattr(config, "KOMUT_DOSYASI", "komut.json")), dosya_yolu())


def durum_oku() -> dict:
    yol = durum_yolu()
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"son_id": "", "son_zaman": "", "gecmis": []}
    if not isinstance(veri, dict):
        return {"son_id": "", "son_zaman": "", "gecmis": []}
    veri.setdefault("son_id", "")
    veri.setdefault("son_zaman", "")
    gecmis = veri.get("gecmis")
    veri["gecmis"] = gecmis if isinstance(gecmis, list) else []
    return veri


def durum_yaz(sonuc: Sonuc) -> None:
    """Uygulanan komutu işaretler (tekrar engeli) + son 20 kaydı tutar."""
    durum = durum_oku()
    durum["son_id"] = sonuc.id
    durum["son_zaman"] = sonuc.zaman or datetime.now().isoformat(timespec="seconds")
    durum["gecmis"] = ([*durum["gecmis"], {"id": sonuc.id, "komut": sonuc.komut, "zaman": durum["son_zaman"], "sonuc": sonuc.ozet()}] )[-20:]
    yol = durum_yolu()
    gecici = yol.with_suffix(".json.tmp")
    try:
        gecici.write_text(json.dumps(durum, ensure_ascii=False, indent=1), encoding="utf-8")
        gecici.replace(yol)
    except OSError:
        log.warning("komut durumu yazılamadı: %s", yol, exc_info=True)


# ------------------------------------------------------------------ doğrulama
def dogrula(
    belge: dict | None,
    *,
    cihaz_id: str = "",
    son_id: str = "",
    anahtar: bytes | None = None,
    imza_zorunlu: bool | None = None,
) -> Karar:
    """Komut uygulanmalı mı? (fail-closed: şüpheli her durum reddedilir)"""
    if not isinstance(belge, dict):
        return Karar(False, "komut yok")
    komut = str(belge.get("komut", "") or "").strip().lower()
    if komut not in IZINLI_KOMUTLAR:
        return Karar(False, f"izin listesinde olmayan komut: {komut or '(boş)'}")
    kimlik = str(belge.get("id", "") or "").strip()
    if not kimlik:
        return Karar(False, "komut kimliği (id) yok — tekrar engeli kurulamaz")
    if son_id and kimlik == son_id:
        return Karar(False, f"bu komut zaten uygulandı: {kimlik}")
    hedef = str(belge.get("cihazId", "") or "").strip()
    if hedef and hedef != "*" and cihaz_id and hedef != str(cihaz_id).strip():
        return Karar(False, f"komut başka cihaz için: {hedef}")
    zorunlu = bool(getattr(config, "KOMUT_IMZA_ZORUNLU", True)) if imza_zorunlu is None else imza_zorunlu
    imza = imza_dogrula(belge, anahtar, zorunlu)
    if not imza.kabul:
        return imza
    if not argv(komut):
        # argv boş → uygulama içi tazeleme (ekrani-yenile) ya da yapılandırma eksiği
        if komut != "ekrani-yenile":
            return Karar(False, f"'{komut}' için çalıştırılacak komut tanımlı değil (ayarlar)")
    return Karar(True, imza.sebep)


def argv(komut: str) -> list[str]:
    """Komut adının SABİT argv karşılığı (config'ten; kabuk kullanılmaz)."""
    esleme = {
        "yeniden-baslat": getattr(config, "KOMUT_YENIDEN_BASLAT", ""),
        "uygulamayi-yeniden-baslat": getattr(config, "KOMUT_UYGULAMA_YENIDEN_BASLAT", ""),
        "ekrani-yenile": getattr(config, "KOMUT_EKRANI_YENILE", ""),
    }
    ham = str(esleme.get(komut, "") or "").strip()
    return shlex.split(ham) if ham else []


# ------------------------------------------------------------------ uygulama
def uygula(
    belge: dict,
    *,
    kuru: bool | None = None,
    calistir=subprocess.run,
    bildirim_geri_cagri=None,
) -> Sonuc:
    """Doğrulanmış komutu çalıştırır. `kuru=True` ya da ayar açıkken yalnız günlüklenir.

    `bildirim_geri_cagri`: komut ÇALIŞMADAN ÖNCE çağrılır (`komut` metni ile). Qt burada
    "yeniden başlatılıyor" kaplamasını gösterip `processEvents()` çağırır; aksi hâlde
    `subprocess` ana iş parçacığını bloke ettiği için yazı hiç boyanmaz.
    """
    komut = str(belge.get("komut", "")).strip().lower()
    kimlik = str(belge.get("id", "")).strip()
    kuru = bool(getattr(config, "KOMUT_KURU_CALISTIRMA", False)) if kuru is None else kuru
    sonuc = Sonuc(
        id=kimlik,
        komut=komut,
        argv=argv(komut),
        kuru=kuru,
        zaman=datetime.now().isoformat(timespec="seconds"),
    )

    if not sonuc.argv:
        # argv yok → yalnız "ekrani-yenile": uygulama kendisi tazeler
        sonuc.uygulama_ici = True
        log.info("komut: %s → uygulama içi tazeleme istendi (%s)", komut, kimlik)
        _bildir(komut, bildirim_geri_cagri, sure_s=4.0)
        durum_yaz(sonuc)
        return sonuc

    if kuru:
        log.info("komut (KURU): %s → %s", komut, " ".join(sonuc.argv))
        durum_yaz(sonuc)
        return sonuc

    zaman_asimi = int(getattr(config, "KOMUT_ZAMAN_ASIMI_S", 60) or 60)
    log.warning("komut ÇALIŞTIRILIYOR: %s → %s (%s)", komut, " ".join(sonuc.argv), kimlik)
    # EKRANDA KISA BİLGİ (kullanıcı isteği): komut çalışırken ekran kararıyor gibi görünmesin.
    _bildir(komut, bildirim_geri_cagri)
    try:
        tamam = calistir(sonuc.argv, capture_output=True, text=True, timeout=zaman_asimi, check=False)
        sonuc.cikis_kodu = int(getattr(tamam, "returncode", 0) or 0)
        cikti = f"{getattr(tamam, 'stdout', '') or ''}{getattr(tamam, 'stderr', '') or ''}".strip()
        sonuc.cikti = cikti[:2000]
    except Exception as hata:  # noqa: BLE001 - komut hatası uygulamayı düşürmemeli
        sonuc.hata = f"{type(hata).__name__}: {hata}"
        log.error("komut çalıştırılamadı: %s → %s", komut, sonuc.hata)

    # Bildirim SÜRELİDİR (auto-expire). BAŞARILI komutta burada temizlenmez: tarayıcı modunda
    # arayüz `/komut-bildirim` ucunu 1 sn'de bir sorar, `systemctl reboot/restart` ise ~10-50 ms'de
    # döner — anında temizlik yazının hiç görünmemesine yol açıyordu (i5 bulgusu). Metin en çok
    # `bildirim.VARSAYILAN_SURE_S` (8 sn) görünür; süreç ölürse kayıt zaten bellekle birlikte gider.
    # Komut BAŞARISIZ olduysa yanıltıcı olmasın diye hemen kaldırılır (ekranda "yeniden başlatılıyor"
    # yazıp hiçbir şeyin olmaması daha kötüdür).
    if sonuc.hata or sonuc.cikis_kodu != 0:
        _bildir_temizle()
    durum_yaz(sonuc)
    log.info("komut sonucu: %s", sonuc.ozet())
    return sonuc


def _bildir(komut: str, geri_cagri=None, sure_s: float | None = None) -> None:
    """Ekran bildirimini başlatır (hata gösterimi ASLA engellemez)."""
    try:
        from core import bildirim as bildirim_modulu

        bildirim_modulu.goster(komut, sure_s)
    except Exception:  # noqa: BLE001 - bildirim uygulamayı düşürmemeli
        log.debug("komut bildirimi gösterilemedi", exc_info=True)
    if geri_cagri is None:
        return
    try:
        geri_cagri(komut)
    except Exception:  # noqa: BLE001
        log.debug("komut bildirimi geri çağrısı başarısız", exc_info=True)


def _bildir_temizle() -> None:
    try:
        from core import bildirim as bildirim_modulu

        bildirim_modulu.temizle()
    except Exception:  # noqa: BLE001
        log.debug("komut bildirimi temizlenemedi", exc_info=True)


def kontrol(
    *,
    cihaz_id: str = "",
    kuru: bool | None = None,
    calistir=subprocess.run,
    bildirim_geri_cagri=None,
) -> tuple[Karar, Sonuc | None]:
    """Tam akış: oku → doğrula → uygula. Uygulanacak komut yoksa `(Karar, None)`.

    Çağıran taraf (Qt uygulaması ya da tarayıcı başlatıcı) bu fonksiyonu kısa aralıklarla çağırır.
    """
    belge = oku()
    if not belge:
        return Karar(False, "komut yok"), None
    durum = durum_oku()
    karar = dogrula(belge, cihaz_id=cihaz_id, son_id=str(durum.get("son_id", "")), anahtar=anahtar_oku())
    if not karar.kabul:
        # aynı komutun tekrarını her turda günlüğe yazmayalım: yalnız farklı bir kimlikse uyar
        if str(belge.get("id", "")) != str(durum.get("son_id", "")):
            log.warning("komut REDDEDİLDİ (%s): %s", belge.get("komut"), karar.sebep)
        return karar, None
    return karar, uygula(belge, kuru=kuru, calistir=calistir, bildirim_geri_cagri=bildirim_geri_cagri)


def sonuc_metni(sonuc: Sonuc) -> str:
    """Teşhis/günlük için okunabilir tek satır."""
    return f"{sonuc.zaman} {sonuc.ozet()}"
