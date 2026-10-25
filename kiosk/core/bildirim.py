"""KOMUT BİLDİRİMİ — komut uygulanırken ekranda kısa bir "yeniden başlatılıyor" bilgisi.

NEDEN
-----
Yeniden başlatma komutu geldiğinde ekran birkaç saniye içinde kararır/kapanır; kullanıcı bunu
"ekran bozuldu" diye yorumluyordu. Qt ve tarayıcı modunda aynı metin gösterilsin diye bildirim
TEK yerde (`core/bildirim.py`) tutulur:

* **Qt** aynı süreçte olduğu için `aktif()` çağırır (yoklama turunda) ve kaplamayı gösterir.
* **Tarayıcı** modunda süpervizör ayrı süreç gibi çalışır ama web sunucusu da aynı süreçtedir;
  arayüz `/komut-bildirim` ucundan okur (`core/tarayici.py`).

TASARIM
-------
* Bildirim **sürelidir** (`sure_s`, varsayılan 8 sn): uygulama çökse/komut takılsa bile ekranda
  kalıcı bir yazı kalmaz (auto-expire).
* Metin SABİTTİR ve komut adı beyaz listeden gelir; komut gövdesinden metin taşınmaz (XSS/uydurma
  metin riski yok).
* Durum yalnız bellekte tutulur — diske yazılmaz, cihaz yeniden başlayınca kaybolur (istenen).
"""

from __future__ import annotations

import threading
import time

#: (komut, metin) — beyaz listedeki adlar (`core/komut.py::IZINLI_KOMUTLAR`)
METINLER: dict[str, str] = {
    "yeniden-baslat": "Cihaz yeniden başlatılıyor…",
    "uygulamayi-yeniden-baslat": "Ekran uygulaması yeniden başlatılıyor…",
    "ekrani-yenile": "Ekran yenileniyor…",
}

VARSAYILAN_METIN = "Komut uygulanıyor…"
VARSAYILAN_SURE_S = 8.0

#: `ekrani-yenile` kısa sürer: tarayıcı süreci yeniden başlatılır, sayfa hemen tazelenir.
EKRANI_YENILE_SURE_S = 4.0

#: Tarayıcı arayüzünün `/komut-bildirim` yoklama aralığı (sn) — `web/src/App.vue` ile AYNI olmalı.
ARAYUZ_YOKLAMA_S = 1.0

#: Sayfa yenilenmeden ÖNCE beklenecek süre: bir yoklama turu + pay. Arayüz yazıyı bir kez
#: okusun diye; sabit `1.2` yazmak yerine yoklama aralığından türetilir (i5 bulgusu).
YENILEME_ONCESI_BEKLEME_S = ARAYUZ_YOKLAMA_S * 1.2


def sure_uret(komut: str) -> float:
    """Komutun bildirim süresi (sn) — TEK KAYNAK.

    Qt kaplaması, tarayıcı beklemesi ve `goster()` aynı değeri kullanır; sabit sayı
    tekrarlanmadığı için biri değişince diğeri yanlış süre göstermez (i5 bulgusu).
    """
    return EKRANI_YENILE_SURE_S if str(komut or "").strip().lower() == "ekrani-yenile" else VARSAYILAN_SURE_S

_kilit = threading.Lock()
_durum: dict | None = None


def metin_uret(komut: str) -> str:
    """Komut adına karşılık gelen sabit metin (bilinmeyen ad → genel metin)."""
    return METINLER.get(str(komut or "").strip().lower(), VARSAYILAN_METIN)


def goster(komut: str, sure_s: float | None = None, *, simdi: float | None = None) -> dict:
    """Bildirimi başlatır; görünen durumu döner."""
    global _durum
    sure = sure_uret(komut) if sure_s is None else max(0.0, float(sure_s))
    an = time.monotonic() if simdi is None else float(simdi)
    durum = {
        "komut": str(komut or "").strip().lower(),
        "metin": metin_uret(komut),
        "baslangic": an,
        "bitis": an + sure,
    }
    with _kilit:
        _durum = durum
    return dict(durum)


def aktif(*, simdi: float | None = None) -> dict | None:
    """Süresi dolmamış bildirim (yoksa None). Süresi geçen kayıt temizlenir."""
    global _durum
    an = time.monotonic() if simdi is None else float(simdi)
    with _kilit:
        if _durum is None:
            return None
        if an >= float(_durum.get("bitis", 0)):
            _durum = None
            return None
        return dict(_durum)


def temizle() -> None:
    """Bildirimi hemen kaldırır (komut bittiğinde)."""
    global _durum
    with _kilit:
        _durum = None


def sifirla() -> None:
    """Testler için: bellekteki durumu tamamen temizler."""
    temizle()
