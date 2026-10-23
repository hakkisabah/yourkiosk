"""SUNUCUDAN KÜÇÜK DOSYA ÇEKME — `tetikle.json` (nöbet değişikliği) ve `komut.json` (uzaktan komut).

Panel bu dosyaları S3'e yazar; cihazın **yerel kopyasını** güncel tutması gerekir. Tarayıcı modunda
cihaz bu dosyaları yerel sunucudan okuduğu (ve sunucu imzası mtime'a baktığı) için yerel kopya
güncellendiği AN arayüz de haberdar olur.

GÜVENLİK: `security.network` ile AYNI politika — yalnız izinli alan adları, yalnız HTTPS, boyut
sınırı, yönlendirme kapalı. Bu dosyalar **komut değil, veri**dir: içeriği ancak doğrulamadan
(imza/beyaz liste) geçerse uygulanır (`core/komut.py`).
"""

from __future__ import annotations

import logging
from pathlib import Path

import config

log = logging.getLogger("kiosk.uzak")

#: Küçük kontrol dosyaları için bayt sınırı (tetikleyici/komut asla bunu aşmamalı)
EN_BUYUK_KUCUK_BAYT = 64 * 1024


def taban_adres() -> str:
    """Küçük dosyaların çekileceği taban adres (boşsa uzak senkron YAPILMAZ)."""
    adres = str(getattr(config, "DOSYA_ADRESI", "") or "").strip()
    if not adres:
        return ""
    return adres.rstrip("/")


def getir(ad: str, *, taban: str | None = None, en_buyuk_bayt: int = EN_BUYUK_KUCUK_BAYT) -> bytes | None:
    """`<taban>/<ad>` içeriğini indirir (politika ihlali/bağlantı hatası → None)."""
    kok = taban if taban is not None else taban_adres()
    if not kok:
        return None
    from security.network import AgAyarlari, AgHatasi, indir

    ayarlar = AgAyarlari(
        zaman_asimi_s=float(getattr(config, "HTTP_TIMEOUT_S", 10.0)),
        en_buyuk_bayt=en_buyuk_bayt,
        izinli_hostlar=tuple(getattr(config, "ALLOWED_HOSTS", ()) or ()),
        kullanici_ajani="yourkiosk/1.0",
        izinli_portlar=tuple(getattr(config, "AG_IZINLI_PORTLAR", (443,))),
        yonlendirme_izinli=bool(getattr(config, "AG_YONLENDIRME_IZINLI", False)),
        en_buyuk_url=int(getattr(config, "MAX_URL_UZUNLUK", 2048)),
    )
    # NOT: `indir()` varsayılan olarak GÖRSEL içerik türü beyaz listesini uygular (png/jpeg/webp).
    # tetikle.json / komut.json `application/json` gelir → bu yüzden denetim KAPATILIR; JSON
    # geçerliliği çağıran tarafta (core/tetik.py, core/komut.py) ayrıştırılarak doğrulanır.
    try:
        govde, tur = indir(f"{kok}/{ad}", ayarlar, icerik_turu_denetle=False)
        if tur and not (tur.startswith("application/json") or tur.startswith("text/plain")
                        or tur in ("", "application/octet-stream")):
            log.warning("küçük dosya beklenmeyen içerik türü (%s/%s): %s", kok, ad, tur)
            return None
    except AgHatasi as hata:
        # 403/404 = dosya yok (henüz yazılmamış) → gürültü yapma; gerçek politika/ağ hatası uyarı
        metin = str(hata)
        if "HTTP 403" in metin or "HTTP 404" in metin:
            log.debug("küçük dosya yok (%s/%s): %s", kok, ad, metin)
        else:
            log.warning("küçük dosya alınamadı (%s/%s): %s", kok, ad, hata)
        return None
    except Exception:  # noqa: BLE001 - ağ hatası gösterimi durdurmamalı
        log.warning("küçük dosya alınamadı (%s/%s)", kok, ad, exc_info=True)
        return None
    return govde


def yerel_guncelle(yol: Path, govde: bytes) -> bool:
    """İçerik FARKLIYSA yerel dosyayı atomik yazar; değiştiyse True.

    İçerik aynıysa dokunulmaz → gereksiz mtime değişimi (ve gereksiz arayüz bildirimi) olmaz.
    """
    try:
        if yol.is_file() and yol.read_bytes() == govde:
            return False
        gecici = yol.with_suffix(yol.suffix + ".tmp")
        gecici.write_bytes(govde)
        gecici.replace(yol)
        return True
    except OSError:
        log.warning("yerel dosya yazılamadı: %s", yol, exc_info=True)
        return False


def senkron(hedefler: dict[str, Path]) -> list[str]:
    """Verilen `{ad: yerel yol}` çiftlerini sunucudan tazeler; DEĞİŞENLERİN adlarını döner.

    Taban adres tanımlı değilse hiçbir şey yapmaz (cihaz dosyaları elle/yedekleme yoluyla gelir).
    """
    if not taban_adres():
        return []
    degisenler: list[str] = []
    for ad, yol in hedefler.items():
        govde = getir(ad)
        if govde and yerel_guncelle(yol, govde):
            degisenler.append(ad)
    if degisenler:
        log.info("uzak senkron: güncellenen dosyalar → %s", ", ".join(degisenler))
    return degisenler
