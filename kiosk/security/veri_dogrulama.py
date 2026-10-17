"""Güvenilmeyen veriyi sınırlandırma + temizleme (Qt bağımlılığı YOK).

NEDEN
-----
Kiosk ekranı verisini **dışarıdan** alır (sunucu dosyaları ya da yerel JSON).
Bozuk ya da kötü niyetli bir dosya:

  * belleği şişirebilir (yüz megabaytlık JSON, milyonlarca düğüm, aşırı derinlik),
  * ekranı ele geçirebilir (on binlerce kayıt → kayan yazı/sıralama donar),
  * görüntüyü yanıltabilir (denetim karakterleri, satır sonları, çift yönlü
    yazı kontrolleri: U+202E ile metni ters çevirme, sahte telefon numarası),
  * zamanlayıcıyı kilitleyebilir (`duration: 99999999` → ekran yayında donar).

Bu modül tek kapıdır: JSON okuma, metin temizleme ve sınırlama burada yapılır.
"""

from __future__ import annotations

import json
import logging
import os
import unicodedata
from pathlib import Path

log = logging.getLogger("kiosk.veri_guvenlik")


class VeriHatasi(RuntimeError):
    """Veri politikaya uymadı (boyut/derinlik/şema)."""


# ----------------------------------------------------------------- boyut/derinlik
def _derinlik_ve_dugum_say(deger: object, *, en_buyuk_derinlik: int, en_buyuk_dugum: int) -> int:
    """Yinelemesiz (yığın tabanlı) derinlik/düğüm denetimi; aşımda VeriHatasi."""
    dugum = 0
    yigin: list[tuple[object, int]] = [(deger, 1)]
    while yigin:
        nesne, derinlik = yigin.pop()
        dugum += 1
        if dugum > en_buyuk_dugum:
            raise VeriHatasi(f"JSON düğüm sayısı sınırı aştı (> {en_buyuk_dugum})")
        if derinlik > en_buyuk_derinlik:
            raise VeriHatasi(f"JSON derinliği sınırı aştı (> {en_buyuk_derinlik})")
        if isinstance(nesne, dict):
            yigin.extend((k, derinlik + 1) for k in nesne.keys())
            yigin.extend((v, derinlik + 1) for v in nesne.values())
        elif isinstance(nesne, (list, tuple)):
            yigin.extend((o, derinlik + 1) for o in nesne)
    return dugum


def json_yukle(
    ham: bytes | str,
    *,
    etiket: str = "veri",
    en_buyuk_bayt: int = 4 * 1024 * 1024,
    en_buyuk_derinlik: int = 32,
    en_buyuk_dugum: int = 200_000,
) -> object:
    """Boyut + derinlik + düğüm denetimli JSON okuma."""
    if isinstance(ham, str):
        ham = ham.encode("utf-8")
    if len(ham) > en_buyuk_bayt:
        raise VeriHatasi(f"{etiket}: gövde çok büyük ({len(ham)} > {en_buyuk_bayt} bayt)")
    if not ham.strip():
        raise VeriHatasi(f"{etiket}: boş gövde")
    try:
        veri = json.loads(ham.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as hata:
        raise VeriHatasi(f"{etiket}: JSON çözülemedi ({type(hata).__name__})") from hata
    dugum = _derinlik_ve_dugum_say(veri, en_buyuk_derinlik=en_buyuk_derinlik, en_buyuk_dugum=en_buyuk_dugum)
    log.debug("%s: JSON okundu (%d düğüm)", etiket, dugum)
    return veri


# ------------------------------------------------------------------- dosya okuma
def dosya_oku_guvenli(yol: Path, *, kok: Path, etiket: str = "dosya", en_buyuk_bayt: int = 4 * 1024 * 1024) -> bytes:
    """Yerel veri dosyasını denetimli okur.

    * sembolik bağ (symlink) kabul edilmez — beklenmeyen bir yere işaret edemez,
    * dosya proje kökünün **içinde** olmalı (path traversal engeli),
    * yalnızca normal dosya (aygıt/FIFO değil) ve boyut sınırı içinde.
    """
    kok = Path(kok).resolve()
    yol = Path(yol)
    if yol.is_symlink():
        raise VeriHatasi(f"{etiket}: sembolik bağ kabul edilmiyor ({yol})")
    try:
        gercek = yol.resolve(strict=True)
    except (OSError, RuntimeError) as hata:
        raise VeriHatasi(f"{etiket}: dosya açılamadı ({hata})") from hata
    if kok not in gercek.parents and gercek != kok:
        raise VeriHatasi(f"{etiket}: dosya proje dizininin dışında ({gercek})")
    if not gercek.is_file():
        raise VeriHatasi(f"{etiket}: normal dosya değil ({gercek})")
    boyut = gercek.stat().st_size
    if boyut > en_buyuk_bayt:
        raise VeriHatasi(f"{etiket}: dosya çok büyük ({boyut} > {en_buyuk_bayt} bayt)")
    return gercek.read_bytes()


def atomik_yaz(yol: Path, icerik: str | bytes | dict | list, *, mod: int = 0o600) -> None:
    """Aynı dizine geçici dosya + `os.replace` ile atomik yazma (kısmi dosya kalmaz).

    `icerik` sözlük/liste ise JSON olarak yazılır.
    """
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(f".{yol.name}.tmp")
    if isinstance(icerik, (dict, list)):
        icerik = json.dumps(icerik, ensure_ascii=False, indent=2)
    veri = icerik.encode("utf-8") if isinstance(icerik, str) else icerik
    tanim = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mod)
    try:
        with os.fdopen(tanim, "wb") as dosya:
            dosya.write(veri)
            dosya.flush()
            os.fsync(dosya.fileno())
    except BaseException:
        gecici.unlink(missing_ok=True)
        raise
    os.replace(gecici, yol)


def dosya_izni_uyari(yol: Path, *, etiket: str = "veri") -> str | None:
    """Dosya gruba/dünyaya yazılabilirse uyarı metni döner (tamper denetimi)."""
    try:
        mod = Path(yol).stat().st_mode
    except OSError:
        return None
    if mod & 0o022:
        return f"{etiket}: {Path(yol).name} gruba/dünyaya yazılabilir (mod {oct(mod & 0o777)}) — kurcalanmaya açık"
    return None


# ------------------------------------------------------------------- metin temizleme
#: Çift yönlü yazı kontrolleri (görüntüyü yanıltmak için kullanılabilir)
BIDI_KONTROLLERI = dict.fromkeys(
    [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069, 0x200E, 0x200F]
)


def temiz_metin(deger: object, *, en_buyuk: int = 160, tek_satir: bool = False) -> str:
    """Gösterilecek metni güvenli hâle getirir.

    * denetim karakterleri (C0/C1) ve çift yönlü yazı kontrolleri atılır,
    * `tek_satir` ise satır sonları boşluğa çevrilir (yerleşimi bozamasın),
    * fazla boşluklar sadeleştirilir, baş/son boşluk atılır,
    * uzunluk `en_buyuk` ile sınırlanır (uzunluk aşımı `…` ile işaretlenir).
    """
    if deger is None:
        return ""
    if not isinstance(deger, str):
        deger = str(deger)
    deger = unicodedata.normalize("NFC", deger).translate(BIDI_KONTROLLERI)
    parcalar: list[str] = []
    for karakter in deger:
        kod = ord(karakter)
        if karakter in "\r\n\t":
            parcalar.append(" " if tek_satir else ("\n" if karakter == "\n" else " "))
            continue
        if kod < 0x20 or 0x7F <= kod <= 0x9F:
            continue  # denetim karakteri
        parcalar.append(karakter)
    metin = "".join(parcalar)
    if tek_satir:
        metin = " ".join(metin.split())
    else:
        satirlar = [" ".join(s.split()) for s in metin.split("\n")]
        metin = "\n".join(s for s in satirlar if s)
    metin = metin.strip()
    if en_buyuk > 0 and len(metin) > en_buyuk:
        metin = metin[: max(0, en_buyuk - 1)].rstrip() + "…"
        log.warning("metin kısaltıldı (%d karakter sınırı)", en_buyuk)
    return metin


def sayi_sinirla(deger: object, *, alt: int, ust: int, varsayilan: int) -> int:
    """Sayısal alanı güvenli aralığa çeker (bozuk değer ekranı kilitlemesin)."""
    try:
        sayi = int(float(deger))  # araya "10.0" ya da "10" gelirse
    except (TypeError, ValueError):
        log.warning("sayısal alan okunamadı (%r), varsayılan %d", deger, varsayilan)
        return varsayilan
    if sayi < alt or sayi > ust:
        log.warning("sayısal alan sınır dışı (%d), %d..%d aralığına çekildi", sayi, alt, ust)
        return max(alt, min(ust, sayi))
    return sayi


def liste_sinirla(liste: object, *, en_buyuk: int, etiket: str = "liste") -> list:
    """Listeyi üst sınırla keser (aşımda uyarır)."""
    if not isinstance(liste, list):
        return []
    if len(liste) > en_buyuk:
        log.warning("%s: %d kayıt var, ilk %d tanesi gösterilecek", etiket, len(liste), en_buyuk)
        return liste[:en_buyuk]
    return liste


def kimlik_ozeti(kimlik: str) -> str:
    """Günlüğe ham kimlik yazmamak için kısa özet (ilk 6 karakter + uzunluk)."""
    import hashlib

    metin = kimlik or ""
    if not metin:
        return "-"
    ozet = hashlib.sha256(metin.encode("utf-8")).hexdigest()[:10]
    return f"{metin[:4]}…({len(metin)}h, sha256:{ozet})"
