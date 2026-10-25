"""`durum.json` — cihazın TEK istekle tüm küçük kontrol bilgilerini alması.

NEDEN: her yoklama turunda 3 ayrı dosya çekiliyordu (`lastupdate.json`, `tetikle.json`,
`komut.json`). 600 cihaz × 300 sn'lik turda bu **~15,5 M istek/ay** (~$18). Tek dosya:
- 1 istek/tur (3× azalma),
- aynı yanıt hem damgayı hem tetikleyiciyi hem komut işaretini taşır.

PANEL YAZAR (`durum.json`):
    {
      "zaman": "2026-10-24T09:12:00Z",          # bu belgenin üretim anı
      "lastupdate": "2026-10-24 09:11:58",       # veri damgası
      "tetik": {"zaman": "...", "ilceId": "", "bolgeId": "", "aciklama": "panel: sistem"},
      "komut": {"zaman": "...", "id": "..."}     # yalnız işaret; gövde ayrı dosyada (nadir)
    }

GERİYE UYUM: `durum.json` yoksa (404) eski üç dosyalı yol aynen çalışır.
"""

from __future__ import annotations

import json
import logging

from core import uzak, zaman
from security.veri_dogrulama import VeriHatasi, json_yukle

log = logging.getLogger("kiosk.durum")

AD = "durum.json"

#: `durum.json` küçük bir özettir; sınırlar sabittir (yayın belgesi değil, cihaz özeti).
EN_BUYUK_BELGE_BAYT = 64 * 1024
EN_BUYUK_DERINLIK = 16
EN_BUYUK_DUGUM = 2_000

#: Son BAŞARILI belge (304'te gövde inmez → bellek kopyası kullanılır). 404'te temizlenir.
_son_belge: dict | None = None


def getir() -> dict | None:
    """`durum.json` içeriği (yoksa/bozuksa None → çağıran eski yola düşer).

    KOŞULLU okuma: sunucu ETag/Last-Modified veriyorsa değişmeyen dosya için 304 alınır ve
    ~1 tam gövde indirilmez; son başarılı belge bellekten döner (i5 bulgusu — maliyet hedefi).
    Doğrulayıcı YALNIZ JSON başarıyla ayrıştırıldıktan sonra hatırlanır (bozuk içerik kalıcı
    304'e dönüşmesin).
    """
    global _son_belge

    govde, degismedi, dogrulayici = uzak.kosullu_getir(AD)
    if degismedi:
        return _son_belge  # 304: içerik değişmedi, gövde inmedi
    if not govde:
        _son_belge = None  # 404/boş/hata → eski üç dosyalı yola düşülür
        # Doğrulayıcıyı da unut: dosya aynı içerikle yeniden yaratılırsa 304 alıp bir daha
        # inmeme riski kalmasın (i5 bulgusu).
        uzak.dogrulayici_unut(AD)
        return None
    try:
        belge = json_yukle(
            govde,
            etiket=AD,
            en_buyuk_bayt=EN_BUYUK_BELGE_BAYT,
            en_buyuk_derinlik=EN_BUYUK_DERINLIK,
            en_buyuk_dugum=EN_BUYUK_DUGUM,
        )
    except (VeriHatasi, RecursionError):
        # RecursionError: 64 KB sınırı içinde DERİN iç içe gövde ayrıştırmayı patlatır; yakalanmazsa
        # istisna yoklama turunu düşürür (i5 bulgusu). `json_yukle` bunu artık VeriHatasi'ya çevirir;
        # yine de savunmalı olarak burada da yakalanır.
        log.warning("durum.json bozuk/çok derin JSON — yok sayıldı")
        _son_belge = None
        return None
    if not isinstance(belge, dict):
        _son_belge = None
        return None
    _son_belge = belge
    uzak.dogrulayici_kaydet(AD, dogrulayici)  # yalnız başarılı ayrıştırmadan sonra
    return belge


def damga(belge: dict | None) -> str:
    return str((belge or {}).get("lastupdate") or "").strip()


def tetik(belge: dict | None) -> dict | None:
    deger = (belge or {}).get("tetik")
    return deger if isinstance(deger, dict) and deger else None


def secili_tetik(belge: dict | None, yerel_oku) -> dict | None:
    """Tetikleyici seçimi: UZAK (panel → `durum.json`) önce, yoksa YEREL (MQTT → `tetikle.json`).

    NEDEN: MQTT push yerel dosyaya yazar. `durum.json` yoluna geçildiğinde bu dosya okunmazsa
    "Bildir" anlık çalışmaz (yaşandı). `yerel_oku` enjekte edilir → test edilebilir.
    """
    uzak_tetik = tetik(belge)
    try:
        yerel = yerel_oku()
    except Exception:  # noqa: BLE001 - yerel okuma hatası gösterimi durdurmamalı
        yerel = None
    if not isinstance(yerel, dict) or not yerel:
        return uzak_tetik

    # İKİSİ DE VARSA **DAHA YENİ** olanı seç. Sabit öncelik yanlıştı: `durum.json` her panel
    # kaydında yazıldığı için uzak tetik hep dolu; MQTT'nin daha yeni tetiği hiç uygulanmıyordu
    # (değişiklik ancak uygulama yeniden başlatılınca görünüyordu).
    if not uzak_tetik:
        return yerel
    uzak_zaman = str(uzak_tetik.get("zaman", "") or "")
    yerel_zaman = str(yerel.get("zaman", "") or "")
    # SAAT DİLİMİ: panel UTC (`...Z`), yerel tetikleyici yerel saat (`...` uzantısız) yazar.
    # Sözlüksel karşılaştırma UTC+3 cihazda yerel damgayı hep 3 saat ileri gösterip panelin YENİ
    # tetiğini "eski" sayıyordu (panel "Bildir" sessizce yutuluyordu — i5 bulgusu).
    # `zaman.yeni_mi` anları karşılaştırır; çözemezse sözlüksel davranışa düşer.
    return yerel if zaman.yeni_mi(yerel_zaman, uzak_zaman) else uzak_tetik


def komut_isareti(belge: dict | None) -> str:
    """Komut dosyası için kısa işaret (zaman + id). Değişmediyse komut dosyası çekilmez."""
    deger = (belge or {}).get("komut")
    if not isinstance(deger, dict):
        return ""
    return f"{deger.get('zaman', '')}|{deger.get('id', '')}".strip("|")
