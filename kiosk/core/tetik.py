"""NÖBET DEĞİŞİKLİĞİ TETİKLEYİCİSİ (panel → cihaz) — TEK KURAL KAYNAĞI.

SORUN: veri saatte bir kontrol edilir (`LASTUPDATE_KONTROL_MS`). Bir nöbet değişikliği
yapıldığında cihazın bir saate kadar beklemesi istenmez.

ÇÖZÜM: yönetici paneli değişikliği uygularken **tetikleyici** yazar (`tetikle.json`):

    {"zaman": "2026-10-17T09:12:00", "ilceId": "30607352906750376", "bolgeId": "", "aciklama": ""}

Cihaz bu dosyayı (ve `lastupdate.json` damgasını) kısa aralıklarla — `DAMGA_KONTROL_MS`,
**push bağlı 120 sn / kopuk 30 sn** — **yalnızca üst veri** olarak okur (büyük veri dosyasına
dokunmaz) ve kendisini ilgilendiren tetikleyiciyi görürse **hemen** yenilenir:

  · `ilceId` boş/"*"      → TÜM cihazlar,
  · `ilceId` kendi ilçesi → bu cihaz,
  · `bolgeId` kendi bölgesi → bu cihaz,
  · başka ilçe/bölge      → hemen yenilenmez (yoklama push bağlı 120 sn / kopuk 30 sn, saatlik kontrol yeter).

Tarayıcı (Chromium kiosk) modunda buna ek olarak yerel sunucudaki `/degisiklik` ucu ile
**uzun yoklama** yapılır: dosya değiştiği AN bildirilir (tipik <1 sn).

Bu modül hem Qt uygulaması hem yerel web sunucusu hem de `tools/nobet_tetikle.py` tarafından
kullanılır; kural tek yerde durur.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import config
from core import zaman

log = logging.getLogger("kiosk.tetik")

#: Tetikleyici dosyası proje kökünde (cihazın kendi dosyası; panel S3'e aynı adla yazar)
PROJE_KOK = Path(__file__).resolve().parent.parent


def dosya_yolu() -> Path:
    return PROJE_KOK / str(getattr(config, "TETIK_DOSYASI", "tetikle.json"))


#: Geçerli mod adları (ayar doğrulaması ve panel için tek kaynak)
MODLAR = ("qt", "tarayici")


def otomatik_acik(mod: str) -> bool:
    """Bu modda oto tetikleme açık mı?

    `tetik.aktif = false` → hiçbir modda (cihaz normal aralıkta yenilenir).
    `tetik.modlar` → yalnızca listede olan modlar (ör. yalnız `qt`).
    """
    if not bool(getattr(config, "TETIK_AKTIF", True)):
        return False
    modlar = {str(x).strip().lower() for x in (getattr(config, "TETIK_MODLAR", MODLAR) or ())}
    return mod.lower() in modlar


def oku() -> dict | None:
    """Tetikleyiciyi okur; dosya yok/bozuksa ya da `zaman` alanı yoksa None."""
    yol = dosya_yolu()
    try:
        if not yol.is_file():
            return None
        veri = json.loads(yol.read_bytes()[-4096:].decode("utf-8-sig"))
    except (OSError, ValueError):
        log.warning("tetikleyici okunamadı: %s", yol, exc_info=True)
        return None
    if not isinstance(veri, dict) or not str(veri.get("zaman") or "").strip():
        return None
    return {
        "zaman": str(veri.get("zaman") or "").strip(),
        "ilceId": str(veri.get("ilceId") or "").strip(),
        "bolgeId": str(veri.get("bolgeId") or "").strip(),
        "aciklama": str(veri.get("aciklama") or "").strip(),
    }


def yaz(ilce_id: str = "", bolge_id: str = "", aciklama: str = "", zaman: str | None = None) -> dict:
    """Tetikleyiciyi ATOMİK yazar (arayüz yarım dosya okumasın)."""
    belge = {
        "zaman": zaman or datetime.now().replace(microsecond=0).isoformat(),
        "ilceId": str(ilce_id or "").strip(),
        "bolgeId": str(bolge_id or "").strip(),
        "aciklama": str(aciklama or "").strip(),
    }
    yol = dosya_yolu()
    # GÜVENLİK: sabit `<ad>.json.tmp` adı yerine mkstemp (sembolik bağ saldırısı — i5/i3 bulgusu).
    from core import uzak

    if not uzak.atomik_yaz(yol, json.dumps(belge, ensure_ascii=False, indent=1).encode("utf-8")):
        log.warning("tetikleyici yazılamadı: %s", yol)
    log.info("tetikleyici yazıldı: %s (kapsam=%s)", yol, belge["ilceId"] or "tüm cihazlar")
    return belge


def sil() -> bool:
    """Tetikleyiciyi kaldırır (uygulandıktan sonra panel/kurulum isterse)."""
    yol = dosya_yolu()
    try:
        yol.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        log.warning("tetikleyici silinemedi: %s", yol, exc_info=True)
        return False


def getir() -> bool:
    """Panelin S3'e yazdığı `tetikle.json`u yerel kopyaya indirir (değiştiyse True).

    KOŞULLU indirme: sunucu ETag/Last-Modified veriyorsa değişmeyen dosya için 304 alınır ve
    gövde HİÇ inmez. Önceden her yoklama turunda (tarayıcı uzun yoklamasında ~3 sn'de bir) tam
    gövde indirilip bayt karşılaştırması yapılıyordu — dosya çoğu turda değişmiyordu.

    Tarayıcı modunda yerel sunucu imzası bu dosyanın mtime'ına baktığı için, indirme anında
    arayüz de uzun yoklama ile haberdar olur.
    """
    from core import uzak

    return uzak.kosullu_indir_ve_yaz(str(getattr(config, "TETIK_DOSYASI", "tetikle.json")), dosya_yolu())


def imza() -> str:
    """Hızlı değişiklik imzası: dosyanın mtime+boyut+zamanı (yalnız üst veri okunur)."""
    yol = dosya_yolu()
    try:
        durum = yol.stat()
        mtime_boyut = f"{int(durum.st_mtime_ns)}:{durum.st_size}"
    except OSError:
        mtime_boyut = "-"
    mevcut = oku()
    return f"{mtime_boyut}:{(mevcut or {}).get('zaman', '')}"


def uygulanmali(
    tetik: dict | None,
    ilce_id: str | None,
    bolge_id: str | None,
    son_uygulanan: str = "",
) -> bool:
    """Tetikleyici BU cihazda hemen uygulanmalı mı? (tarayıcı tarafındaki kuralın aynısı)

    · boş/"*" ilçe → tüm cihazlar,
    · kendi ilçesi/bölgesi → bu cihaz,
    · aynı/eski tetikleyici → tekrar uygulanmaz (zaman damgası karşılaştırılır).
    """
    if not isinstance(tetik, dict):
        return False
    zaman_metni = str(tetik.get("zaman") or "").strip()
    if not zaman_metni:
        return False
    # SAAT DİLİMİ (i5 bulgusu): `_son_tetik` uygulanan tetiğin damgasını taşır ve bu damga iki
    # biçimde gelebilir — panel/`durum.json` UTC (`...Z`), MQTT/yerel `tetik.yaz` yerel saat
    # (uzantısız). Sözlüksel karşılaştırma UTC+3 cihazda yerel damgayı 3 saat ileri gösterip
    # panelin YENİ tetiğini "eski" sayıyordu → "Bildir" sessizce yutuluyordu (farklı kapıdan
    # aynı belirti). `zaman.yeni_mi` anları karşılaştırır, çözemezse sözlüksel davranışa düşer.
    if son_uygulanan and not zaman.yeni_mi(zaman_metni, son_uygulanan):
        return False
    ilce = str(tetik.get("ilceId") or "").strip()
    bolge = str(tetik.get("bolgeId") or "").strip()
    if not ilce or ilce == "*":
        return True
    if ilce_id and ilce == str(ilce_id).strip():
        return True
    if bolge and bolge_id and bolge == str(bolge_id).strip():
        return True
    return False
