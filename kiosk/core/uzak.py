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
import os
import tempfile
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


def _ayarlar(en_buyuk_bayt: int = EN_BUYUK_KUCUK_BAYT):
    """Ağ politikası ayarları (indirme ve koşullu indirme AYNI politikayı kullanır)."""
    from security.network import AgAyarlari

    return AgAyarlari(
        zaman_asimi_s=float(getattr(config, "HTTP_TIMEOUT_S", 10.0)),
        en_buyuk_bayt=en_buyuk_bayt,
        izinli_hostlar=tuple(getattr(config, "ALLOWED_HOSTS", ()) or ()),
        kullanici_ajani="yourkiosk/1.0",
        izinli_portlar=tuple(getattr(config, "AG_IZINLI_PORTLAR", (443,))),
        yonlendirme_izinli=bool(getattr(config, "AG_YONLENDIRME_IZINLI", False)),
        en_buyuk_url=int(getattr(config, "MAX_URL_UZUNLUK", 2048)),
    )


def getir(ad: str, *, taban: str | None = None, en_buyuk_bayt: int = EN_BUYUK_KUCUK_BAYT) -> bytes | None:
    """`<taban>/<ad>` içeriğini indirir (politika ihlali/bağlantı hatası → None)."""
    kok = taban if taban is not None else taban_adres()
    if not kok:
        return None
    from security.network import AgHatasi, indir

    ayarlar = _ayarlar(en_buyuk_bayt)
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


#: Dosya adı → (ETag, Last-Modified). 304 yanıtı gövde indirmez; hatırlanan değerler gönderilir.
#: ANAHTAR TAM URL'dir (taban adres + dosya adı): farklı kaynaklardan aynı ad istenirse
#: doğrulayıcı sızmasın (i5 bulgusu — başka kaynağa `If-None-Match` gönderiliyordu).
_ETAG: dict[str, tuple[str, str]] = {}


def _anahtar(ad: str, taban: str | None = None) -> str:
    kok = taban if taban is not None else taban_adres()
    return f"{kok.rstrip('/')}/{ad}"


def kosullu_getir(
    ad: str,
    *,
    taban: str | None = None,
    en_buyuk_bayt: int = EN_BUYUK_KUCUK_BAYT,
) -> tuple[bytes | None, bool, tuple[str, str]]:
    """`<taban>/<ad>`u KOŞULLU indirir.

    Dönüş: `(gövde|None, degismedi_mi, (etag, son_degisiklik))`.
    `degismedi_mi=True` → 304: içerik değişmedi, GÖVDE İNMEDİ (çağıran bellekteki kopyayı kullanır).
    `gövde is None` + `degismedi_mi=False` → dosya yok (403/404) ya da ağ/politika hatası.

    Doğrulayıcı BURADA hatırlanmaz: çağıran, yerel kopyayı gerçekten güncellediğini doğruladıktan
    sonra `dogrulayici_kaydet()` çağırır. Aksi hâlde tek seferlik yazma hatası sonraki tüm turları
    304'e düşürür ve dosya bir daha hiç inmez (i5 bulgusu — "sessizce ölü" hatasının yeni yolu).

    NEDEN: `tetikle.json`/`komut.json`/`durum.json` her yoklama turunda (Qt 20 sn, tarayıcı uzun
    yoklama ~3 sn) tam gövde olarak indiriliyordu; dosya çoğu turda hiç değişmiyor. ETag ile 304
    alınınca yanıt gövdesiz (birkaç yüz bayt) olur — 600 cihazda trafik/maliyet düşer.

    Sunucu ETag/Last-Modified vermiyorsa davranış eskisiyle aynıdır (gövde her turda iner).
    """
    kok = taban if taban is not None else taban_adres()
    if not kok:
        return None, False, ("", "")
    from security.network import AgHatasi, kosullu_indir

    etag, tarih = _ETAG.get(_anahtar(ad, taban), ("", ""))
    ayarlar = _ayarlar(en_buyuk_bayt)
    try:
        govde, tur, yeni_etag, yeni_tarih = kosullu_indir(
            f"{kok.rstrip('/')}/{ad}", ayarlar, etag=etag, son_degisiklik=tarih,
            icerik_turu_denetle=False,
        )
    except AgHatasi as hata:
        metin = str(hata)
        if "HTTP 403" in metin or "HTTP 404" in metin:
            log.debug("küçük dosya yok (%s/%s): %s", kok, ad, metin)
        else:
            log.warning("küçük dosya alınamadı (%s/%s): %s", kok, ad, hata)
        return None, False, ("", "")
    except Exception:  # noqa: BLE001 - ağ hatası gösterimi durdurmamalı
        log.warning("küçük dosya alınamadı (%s/%s)", kok, ad, exc_info=True)
        return None, False, ("", "")
    dogrulayici = (yeni_etag or etag, yeni_tarih or tarih)
    if govde is None:
        return None, True, dogrulayici  # 304: içerik değişmedi, gövde inmedi
    if tur and not (tur.startswith("application/json") or tur.startswith("text/plain")
                    or tur in ("", "application/octet-stream")):
        log.warning("küçük dosya beklenmeyen içerik türü (%s/%s): %s", kok, ad, tur)
        return None, False, ("", "")
    return govde, False, dogrulayici


def dogrulayici_kaydet(ad: str, dogrulayici: tuple[str, str], *, taban: str | None = None) -> None:
    """ETag/Last-Modified'i ANCAK yerel kopya doğrulandıktan sonra hatırla.

    Kural: doğrulayıcı sunucudan gelen içerikLE yerel kopya EŞLEŞTİĞİNDE (ya da hiç yoksa)
    saklanmalı; aksi hâlde yazma hatası kalıcı 304'e dönüşür ve dosya bir daha inmez.
    """
    etag, tarih = dogrulayici
    if not (etag or tarih):
        return
    _ETAG[_anahtar(ad, taban)] = (etag, tarih)


def kosullu_indir_ve_yaz(ad: str, yol: Path, *, taban: str | None = None) -> bool:
    """Koşullu indir + yerel dosyaya atomik yaz (değiştiyse True).

    Doğrulayıcı YALNIZ içerik yerelde doğrulandıktan sonra hatırlanır:
    - içerik aynı → dosyaya dokunulmaz, doğrulayıcı saklanır (sonraki tur 304 alır),
    - içerik farklı → yazılır; **yazma başarısızsa doğrulayıcı SAKLANMAZ** → sonraki turda gövde
      yeniden iner (yanlış 304 yüzünden dosyanın sonsuza dek eski kalması engellenir).
    """
    govde, _degismedi, dogrulayici = kosullu_getir(ad, taban=taban)
    if govde is None:
        return False
    try:
        ayni = yol.is_file() and yol.read_bytes() == govde
    except OSError:
        ayni = False
    if ayni:
        dogrulayici_kaydet(ad, dogrulayici, taban=taban)
        return False
    if not yerel_guncelle(yol, govde):
        log.warning("yerel kopya yazılamadı, doğrulayıcı hatırlanmadı (sonraki turda yeniden denenecek): %s", yol)
        return False
    dogrulayici_kaydet(ad, dogrulayici, taban=taban)
    return True


def yerel_guncelle(yol: Path, govde: bytes) -> bool:
    """İçerik FARKLIYSA yerel dosyayı atomik yazar; değiştiyse True.

    İçerik aynıysa dokunulmaz → gereksiz mtime değişimi (ve gereksiz arayüz bildirimi) olmaz.

    GÜVENLİK: geçici dosya `mkstemp` ile TAHMİN EDİLEMEZ adla ve `O_EXCL` olarak açılır. Önceden
    `<ad>.tmp` sabit adına yazılıyordu; uygulama dizinine yazabilen daha az yetkili bir yerel
    kullanıcı o ada sembolik bağ kurup içeriği başka yere yönlendirebilirdi (i5 bulgusu).
    `os.replace` hedefte sembolik bağ olsa bile BAĞI değiştirir, hedefini izlemez.
    """
    try:
        if yol.is_file() and yol.read_bytes() == govde:
            return False
    except OSError:
        pass
    gecici = ""
    try:
        tanitici, gecici = tempfile.mkstemp(prefix=f".{yol.name}.", suffix=".tmp", dir=str(yol.parent))
        with os.fdopen(tanitici, "wb") as dosya:
            dosya.write(govde)
            dosya.flush()
            os.fsync(dosya.fileno())
        os.chmod(gecici, 0o644)  # eski davranış: diğer süreçler okuyabilsin (içerik zaten herkese açık)
        os.replace(gecici, yol)
        return True
    except OSError:
        log.warning("yerel dosya yazılamadı: %s", yol, exc_info=True)
        if gecici:
            try:
                os.unlink(gecici)
            except OSError:
                pass
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
