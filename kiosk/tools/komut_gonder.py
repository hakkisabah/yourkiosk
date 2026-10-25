#!/usr/bin/env python3
"""UZAKTAN KOMUT GÖNDER (yönetici tarafı) — imzalar, S3'e konacak dosyayı üretir.

NEDEN AYRI BİR ARAÇ: cihaz yalnız **imzalı** komut çalıştırır (fail-closed). İmza anahtarı
panel tarayıcısına konulamayacağı için (istemci paketine sızardı) imzalama, anahtarın güvenli
olduğu yerlerde yapılır: yöneticinin makinesi (bu araç) ya da sunucu tarafı (Lambda ortam
değişkeni). Aynı anahtar cihazda `komut.anahtar` (0600) dosyasında durur.

KULLANIM
--------
    # 1) Anahtarı bir kez üret (cihaza ve panel/Lambda'ya aynı değeri koy)
    python3 tools/komut_gonder.py --anahtar-olustur

    # 2) Komutu imzala ve S3'e kopyalanacak dosyayı üret
    python3 tools/komut_gonder.py --komut uygulamayi-yeniden-baslat --cihaz 98273648723468273
    python3 tools/komut_gonder.py --komut ekrani-yenile            # tüm cihazlar

    # 3) Üretilen dosyayı S3'e koy (araç komutu ekrana yazar).
    #    Cihaz komutu 10 yoklama turunda bir çapraz kontrolde alır: en çok 20 dk (push bağlı),
    #    5 dk (push kopuk). Ayrıntı: KOMUTLAR.md §3.

    # Yardımcılar
    python3 tools/komut_gonder.py --durum                # bu cihazdaki son komut durumu
    python3 tools/komut_gonder.py --dogrula komut.json   # bir komut dosyasının imzası geçerli mi

İzinli komutlar: `yeniden-baslat`, `uygulamayi-yeniden-baslat`, `ekrani-yenile`.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from core import komut as komut_modulu  # noqa: E402


def _anahtar_olustur(yol: Path, *, zorla: bool = False) -> int:
    if yol.is_file() and not zorla:
        print(f"anahtar zaten var: {yol}\n(yeniden üretmek için --zorla)")
        return 1
    anahtar = secrets.token_hex(32)  # 64 karakter (32 bayt)
    yol.write_text(anahtar + "\n", encoding="utf-8")
    yol.chmod(0o600)
    print(f"anahtar üretildi: {yol} (izin 0600)")
    print(f"  değer: {anahtar}")
    print()
    print("Aynı değeri şu yerlere de koyun:")
    print("  · diğer cihazlar: `kiosk/komut.anahtar` (0600)")
    print("  · Lambda/sunucu tarafı: ortam değişkeni (ör. KOMUT_ANAHTARI) — panel istemcisine KOYMAYIN")
    return 0


def _imzala(komut_adi: str, cihaz: str, aciklama: str, yol: Path, anahtar_yolu: Path, s3_yol: str) -> int:
    anahtar = komut_modulu.anahtar_oku(anahtar_yolu)
    if not anahtar:
        print(f"anahtar yok: {anahtar_yolu}\nönce: python3 tools/komut_gonder.py --anahtar-olustur")
        return 1
    if komut_adi not in komut_modulu.IZINLI_KOMUTLAR:
        print(f"izinli komut değil: {komut_adi}\nizinli: {', '.join(komut_modulu.IZINLI_KOMUTLAR)}")
        return 1

    belge = {
        "id": f"cmd-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}",
        "komut": komut_adi,
        "cihazId": cihaz or "",
        "zaman": datetime.now().replace(microsecond=0).isoformat(),
        "olusturan": "tools/komut_gonder.py",
        "aciklama": aciklama or "",
    }
    belge["imza"] = komut_modulu.imzala(belge, anahtar)

    # kendi kendini denetle: cihazın yapacağı doğrulamanın aynısı
    karar = komut_modulu.dogrula(belge, cihaz_id=cihaz or "", anahtar=anahtar)
    if not karar.kabul:
        print(f"üretilen komut doğrulamadan geçmedi: {karar.sebep}")
        return 1

    yol.write_text(json.dumps(belge, ensure_ascii=False, indent=1), encoding="utf-8")
    print("komut hazır:", yol)
    print(json.dumps(belge, ensure_ascii=False, indent=1))
    print()
    print("S3'e koyun (cihaz `DAMGA_KONTROL_MS` içinde alır):")
    print(f"  aws s3 cp {yol} {s3_yol}")
    print("  # ya da paneldeki S3 tarayıcısından aynı anahtara yükleyin")
    print()
    print("Doğrulama (cihazda): python3 tools/komut_gonder.py --durum")
    return 0


def _durum() -> int:
    durum = komut_modulu.durum_oku()
    print(f"komut dosyası : {komut_modulu.dosya_yolu()}")
    print(f"durum dosyası : {komut_modulu.durum_yolu()}")
    print(f"anahtar       : {komut_modulu.anahtar_yolu()} {'(var)' if komut_modulu.anahtar_oku() else '(YOK — imzalı komut çalışmaz)'}")
    bekleyen = komut_modulu.oku()
    if bekleyen:
        karar, _ = komut_modulu.kontrol(kuru=True)
        print(f"bekleyen      : {bekleyen.get('id')} · {bekleyen.get('komut')} · cihaz={bekleyen.get('cihazId') or 'tümü'}")
        print(f"bekleyen karar: {'UYGULANIR' if karar.kabul else 'REDDEDİLİR'} — {karar.sebep}")
    else:
        print("bekleyen      : yok")
    print(f"son uygulanan : {durum.get('son_id') or '-'} · {durum.get('son_zaman') or '-'}")
    for kayit in durum.get("gecmis", [])[-5:]:
        print(f"  · {kayit.get('zaman')} {kayit.get('komut')} → {kayit.get('sonuc')}")
    return 0


def _dogrula(yol: Path, anahtar_yolu: Path) -> int:
    try:
        belge = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as hata:
        print(f"okunamadı: {hata}")
        return 1
    anahtar = komut_modulu.anahtar_oku(anahtar_yolu)
    karar = komut_modulu.dogrula(belge, cihaz_id=str(belge.get("cihazId", "")), anahtar=anahtar)
    print(f"{yol}: {'GEÇERLİ' if karar.kabul else 'REDDEDİLİR'} — {karar.sebep}")
    print(f"argv: {' '.join(komut_modulu.argv(str(belge.get('komut', '')))) or '(uygulama içi)'}")
    return 0 if karar.kabul else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="Uzaktan komut imzala/gönder (S3)")
    ap.add_argument("--komut", default="", choices=["", *komut_modulu.IZINLI_KOMUTLAR], help="gönderilecek komut")
    ap.add_argument("--cihaz", default="", help="hedef cihaz kimliği (boş: tüm cihazlar)")
    ap.add_argument("--aciklama", default="", help="kısa not (günlükte görünür)")
    ap.add_argument("--cikti", default="komut-gonderilecek.json", help="üretilecek dosya adı")
    ap.add_argument("--anahtar", default="", help="anahtar dosyası (varsayılan: kiosk/komut.anahtar)")
    ap.add_argument("--s3-yol", default="s3://KOVA/kiosk/komut.json", help="yazdırılacak aws s3 cp hedefi")
    ap.add_argument("--anahtar-olustur", action="store_true", help="yeni HMAC anahtarı üret")
    ap.add_argument("--zorla", action="store_true", help="var olan anahtarın üzerine yaz")
    ap.add_argument("--durum", action="store_true", help="cihazdaki komut durumunu göster")
    ap.add_argument("--dogrula", default="", help="verilen komut dosyasının imzasını denetle")
    a = ap.parse_args()

    anahtar_yolu = Path(a.anahtar).expanduser() if a.anahtar else komut_modulu.anahtar_yolu()

    if a.anahtar_olustur:
        return _anahtar_olustur(anahtar_yolu, zorla=a.zorla)
    if a.durum:
        return _durum()
    if a.dogrula:
        return _dogrula(Path(a.dogrula), anahtar_yolu)
    if not a.komut:
        ap.error("--komut verin (ya da --durum/--dogrula/--anahtar-olustur)")
    return _imzala(a.komut, a.cihaz, a.aciklama, Path(a.cikti), anahtar_yolu, a.s3_yol)


if __name__ == "__main__":
    raise SystemExit(main())
