"""Veri kaynağı: sunucudaki (veya yerel) dört dosyanın okunması.

    lastupdate.json     -> nöbet verisi en son ne zaman güncellendi
    match.json          -> ilçe/bölge -> makine id'leri
    lastSystemData.json -> şablon doldurulmuş nöbet verisi
    makinebilgileri.json-> bu cihazın kimliği (clientID)

KAYNAK = "dosya" ise proje kökünden okunur; "https" ise `config.DOSYA_ADRESI`
altından indirilir (https + izin listesi + port + yönlendirme politikası).
Ağ hatasında son başarılı okuma bellekte tutulur ve o kullanılır.

GÜVENLİK: her okuma `security.veri_dogrulama` kapısından geçer — boyut sınırı,
JSON derinlik/düğüm sınırı; yerel dosyalarda sembolik bağ reddi ve proje kökü
dışına çıkmama denetimi.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import config
from core import onbellek
from security.network import AgAyarlari, AgHatasi, indir
from security.veri_dogrulama import VeriHatasi, dosya_oku_guvenli, json_yukle, temiz_metin

log = logging.getLogger("kiosk.kaynak")

KOK = Path(__file__).resolve().parent.parent

#: Son başarılı okumalar (ağ hatasında yedek)
_önbellek: dict[str, object] = {}

#: Bu veri turunun `lastupdate` damgası (None = henüz okunmadı)
_lastupdate_damgasi: str | None = None


def _yerel_yol(dosya: str) -> Path:
    return KOK / dosya


def _ag_ayarlari(butce: int) -> AgAyarlari:
    return AgAyarlari(
        zaman_asimi_s=config.HTTP_TIMEOUT_S,
        en_buyuk_bayt=butce,
        izinli_hostlar=tuple(config.ALLOWED_HOSTS),
        kullanici_ajani="yourkiosk/1.0",
        izinli_portlar=tuple(getattr(config, "AG_IZINLI_PORTLAR", (443,))),
        yonlendirme_izinli=bool(getattr(config, "AG_YONLENDIRME_IZINLI", False)),
        en_buyuk_url=getattr(config, "MAX_URL_UZUNLUK", 2048),
    )


def _oku(dosya: str) -> object | None:
    """Tek bir dosyayı okur (yerel ya da https). Başarısızsa önbelleği döner."""
    try:
        if (getattr(config, "KAYNAK", "dosya") or "dosya").lower() == "https":
            temel = getattr(config, "DOSYA_ADRESI", "")
            if not temel:
                raise AgHatasi("DOSYA_ADRESI tanımlı değil")
            url = temel.rstrip("/") + "/" + dosya
            # lastupdate dosyası KENDİSİ önbelleğe alınmaz: tazeliği o belirler.
            damga = "" if dosya == getattr(config, "LASTUPDATE_DOSYASI", "lastupdate.json") else _guncel_lastupdate()
            # 1) Disk önbelleği: damga değişmediyse ağa HİÇ çıkmadan kullan (maliyet + hız)
            if damga and bool(getattr(config, "ONBELLEK_VERI_LASTUPDATE_KULLAN", True)):
                disk = onbellek.veri_oku(dosya, damga)
                if disk is not None:
                    veri = json_yukle(
                        disk,
                        etiket=f"{dosya} (diskten)",
                        en_buyuk_bayt=config.MAX_JSON_BAYT,
                        en_buyuk_derinlik=config.MAX_JSON_DERINLIK,
                        en_buyuk_dugum=config.MAX_JSON_DUGUM,
                    )
                    _önbellek[dosya] = veri
                    log.info("'%s' disk önbelleğinden okundu (%d bayt) — ağ kullanılmadı", dosya, len(disk))
                    return veri
            govde, _tur = indir(url, _ag_ayarlari(config.MAX_JSON_BAYT), icerik_turu_denetle=False)
            if damga:
                onbellek.veri_yaz(dosya, govde, damga)
            veri = json_yukle(
                govde,
                etiket=url,
                en_buyuk_bayt=config.MAX_JSON_BAYT,
                en_buyuk_derinlik=config.MAX_JSON_DERINLIK,
                en_buyuk_dugum=config.MAX_JSON_DUGUM,
            )
        else:
            yol = _yerel_yol(dosya)
            if not yol.is_file():
                log.warning("dosya bulunamadı: %s", yol)
                return _önbellek.get(dosya)
            ham = dosya_oku_guvenli(yol, kok=KOK, etiket=dosya, en_buyuk_bayt=config.MAX_JSON_BAYT)
            veri = json_yukle(
                ham,
                etiket=dosya,
                en_buyuk_bayt=config.MAX_JSON_BAYT,
                en_buyuk_derinlik=config.MAX_JSON_DERINLIK,
                en_buyuk_dugum=config.MAX_JSON_DUGUM,
            )
        _önbellek[dosya] = veri
        return veri
    except (AgHatasi, VeriHatasi, OSError) as hata:
        log.error("'%s' okunamadı: %s", dosya, hata)
        return _önbellek.get(dosya)


# ------------------------------------------------------------------ dosyalar
def lastupdate_yukle() -> object | None:
    return _oku(config.LASTUPDATE_DOSYASI)


def lastupdate_taze() -> str:
    """Güncel `lastupdate` damgası — bu turun önbelleğini ATLAYARAK okur.

    `_guncel_lastupdate()` bir veri turunda bir kez okur (büyük dosyaların yeniden
    indirilmesini önlemek için). Hızlı değişiklik denetimi (`DAMGA_KONTROL_MS`) ise
    HER turda tazeyi görmek zorundadır; bu yüzden önbellek sıfırlanıp yeniden okunur
    (yalnızca küçük `lastupdate.json`; büyük veri dosyasına dokunulmaz).
    """
    global _lastupdate_damgasi
    _lastupdate_damgasi = None
    return _guncel_lastupdate()


def match_yukle() -> object | None:
    return _oku(config.MATCH_DOSYASI)


def sistem_verisi_yukle() -> object | None:
    veri = _oku(config.SISTEM_VERISI_DOSYASI)
    if veri is None:
        log.warning("yedek veri dosyasına düşülüyor: %s", config.VERI_DOSYASI_YEDEK)
        veri = _oku(config.VERI_DOSYASI_YEDEK)
    return veri


def _guncel_lastupdate() -> str:
    """Ağdaki güncel `lastupdate` damgası (önbelleğe BAKMAZ, döngü başına bir kez).

    Önbelleğin geçerli olup olmadığını anlamak için tek küçük dosya çekilir; büyük
    veri dosyaları yalnızca damga değiştiyse indirilir.
    """
    global _lastupdate_damgasi
    if _lastupdate_damgasi is not None:
        return _lastupdate_damgasi
    govde = lastupdate_yukle()
    if isinstance(govde, dict):
        for anahtar in ("lastUpdate", "lastupdate", "tarih", "zaman"):
            if govde.get(anahtar):
                _lastupdate_damgasi = str(govde[anahtar])
                return _lastupdate_damgasi
    if govde is None:
        # Ağ yok / çevrimdışı açılış: disk önbelleğinin geçerlilik anahtarı olarak SON BİLİNEN
        # damgayı kullan. Bu olmadan çevrimdışı yeniden başlatmada önbellek HİÇ kullanılmıyordu
        # (damga boş → `veri_oku` atlanıyor → veri yok).
        kayitli = onbellek.kayitli_damga()
        if kayitli:
            log.warning("lastupdate ağdan okunamadı; kayıtlı damga kullanılıyor: %s", kayitli)
            _lastupdate_damgasi = kayitli
            return kayitli
    _lastupdate_damgasi = json.dumps(govde, sort_keys=True) if govde is not None else ""
    return _lastupdate_damgasi


def onbellek_damgasi() -> str:
    """Dışarıya açık: bu veri turunun lastupdate damgası (günlük/teşhis için)."""
    return _guncel_lastupdate()


def makine_yukle() -> object | None:
    return _oku(config.MAKINE_DOSYASI)


def client_id() -> str:
    """Bu cihazın kimliği (makinebilgileri.json -> clientID), temizlenmiş hâlde."""
    govde = makine_yukle()
    if isinstance(govde, dict):
        for anahtar in ("clientID", "clientId", "client_id"):
            if anahtar in govde:
                deger = temiz_metin(govde.get(anahtar), en_buyuk=64, tek_satir=True)
                if deger:
                    return deger
    log.error("cihaz kimliği okunamadı (%s)", config.MAKINE_DOSYASI)
    return ""


def onbellegi_temizle() -> None:
    """Bellek önbelleğini ve döngü damgasını sıfırlar (testler/veri tazeleme)."""
    _önbellek.clear()
    global _lastupdate_damgasi
    _lastupdate_damgasi = None
