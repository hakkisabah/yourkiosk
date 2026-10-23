#!/usr/bin/env python3
"""Kiosk cihazında MQTT push ayarlarını yazar (elle JSON düzenlemeden).

NEDEN: `tetik.push_*` ayarları panelde (S3) duruyor; ancak cihaz **yerel veri** modunda
(`veri.kaynak = dosya`) çalışıyorsa uzak ayarlar hiç okunmaz → push kapalı kalır. Bu araç
ayarları cihazın KENDİ `ayarlar.json` dosyasına yazar (diğer anahtarlara dokunmaz).

Kullanım:
    .venv/bin/python tools/push_ayarla.py --broker yourkiosk.hakkisabah.com \
        --kullanici cihaz --parola 'PAROLA' --dene

    .venv/bin/python tools/push_ayarla.py --kaldir          # push'u kapat
    .venv/bin/python tools/push_ayarla.py --goster          # mevcut durumu yazdır
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

AYAR_DOSYASI = KOK / "ayarlar.json"

VARSAYILAN = {
    "aktif": True,
    "modlar": ["qt", "tarayici"],
    "kontrol_ms": 300000,
    "push_port": 8883,
    "push_konu": "yourkiosk/yayin",
}


def oku() -> dict:
    if not AYAR_DOSYASI.is_file():
        return {}
    try:
        veri = json.loads(AYAR_DOSYASI.read_text(encoding="utf-8"))
    except ValueError as hata:
        raise SystemExit(f"✗ {AYAR_DOSYASI} geçerli JSON değil: {hata}")
    if not isinstance(veri, dict):
        raise SystemExit(f"✗ {AYAR_DOSYASI} bir JSON nesnesi değil")
    return veri


def yaz(belge: dict) -> None:
    gecici = AYAR_DOSYASI.with_suffix(".tmp")
    gecici.write_text(json.dumps(belge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(gecici, 0o600)  # parola içerir
    gecici.replace(AYAR_DOSYASI)


def dene(broker: str, port: int, konu: str, kullanici: str, parola: str) -> bool:
    """Gerçek bağlantı denemesi (paho ile). Başarılıysa True."""
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("  ⚠ paho-mqtt yok → .venv/bin/python -m pip install paho-mqtt")
        return False
    sonuc = {"bagli": False, "hata": ""}

    def _baglandi(_c, _u, _f, rc, _p=None):
        sonuc["bagli"] = int(getattr(rc, "value", rc) or 0) == 0

    if hasattr(mqtt, "CallbackAPIVersion"):
        istemci = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"yourkiosk-tani-{int(time.time()) % 100000}")
    else:  # pragma: no cover
        istemci = mqtt.Client(client_id=f"yourkiosk-tani-{int(time.time()) % 100000}")
    istemci.on_connect = _baglandi
    if kullanici:
        istemci.username_pw_set(kullanici, parola)
    try:
        istemci.tls_set()
        istemci.connect(broker, port, keepalive=20)
        istemci.loop_start()
        for _ in range(20):
            time.sleep(0.25)
            if sonuc["bagli"]:
                istemci.disconnect()
                istemci.loop_stop()
                print(f"  ✓ broker bağlantısı kuruldu: {broker}:{port} · konu={konu}")
                return True
        istemci.loop_stop()
        print(f"  ✗ bağlanamadı: {broker}:{port} (sertifika/host/parola?)")
        return False
    except Exception as hata:  # noqa: BLE001
        print(f"  ✗ bağlantı hatası: {hata}")
        return False


def main() -> int:
    ayar = argparse.ArgumentParser(description="kiosk MQTT push ayarlarını yaz")
    ayar.add_argument("--broker", default="", help="MQTT broker adresi (ör. yourkiosk.hakkisabah.com)")
    ayar.add_argument("--port", type=int, default=VARSAYILAN["push_port"])
    ayar.add_argument("--konu", default=VARSAYILAN["push_konu"])
    ayar.add_argument("--kullanici", default="cihaz")
    ayar.add_argument("--parola", default="", help="broker parolası (ÖNERİLMEZ: kabuk geçmişine düşer)")
    ayar.add_argument("--parola-dosya", default="", help="parolayı bu dosyadan oku (0600; önerilen)")
    ayar.add_argument("--parola-sor", action="store_true", help="parolayı gizli olarak sor (geçmişe yazılmaz)")
    ayar.add_argument("--kontrol-ms", type=int, default=VARSAYILAN["kontrol_ms"])
    ayar.add_argument("--modlar", default="qt,tarayici", help="oto tetiklemenin geçerli olduğu modlar")
    ayar.add_argument("--dene", action="store_true", help="yazdıktan sonra gerçek bağlantı denemesi yap")
    ayar.add_argument("--veri-adresi", default="", help="veriyi bu adresten çek (ör. https://d2dnrvsx5eevod.cloudfront.net/)")
    ayar.add_argument("--yerel-veri", action="store_true", help="veri kaynağını yerel dosyalara geri al")
    ayar.add_argument("--kaldir", action="store_true", help="push'u kapat (diğer anahtarlar korunur)")
    ayar.add_argument("--goster", action="store_true", help="mevcut push ayarlarını yazdır")
    secim = ayar.parse_args()

    belge = oku()
    ham = belge.get("tetik")
    tetik: dict = dict(ham) if isinstance(ham, dict) else {}

    if secim.goster:
        print(f"ayar dosyası: {AYAR_DOSYASI} ({'var' if AYAR_DOSYASI.is_file() else 'yok'})")
        for k in ("aktif", "modlar", "kontrol_ms", "push_aktif", "push_broker", "push_port",
                  "push_konu", "push_kullanici", "push_parola", "push_ca", "push_sertifika", "push_anahtar"):
            if k in tetik:
                deger = "***" if "parola" in k else tetik[k]
                print(f"  tetik.{k:14s}= {deger}")
        return 0

    if secim.kaldir:
        tetik["push_aktif"] = False
        belge["tetik"] = tetik
        yaz(belge)
        print("✓ push kapatıldı (yoklama emniyet ağı kullanılacak)")
        print("  etkili olması için kiosk'u yeniden başlatın")
        return 0

    if not secim.broker:
        print("✗ --broker gerekli (ör. --broker yourkiosk.hakkisabah.com)", file=sys.stderr)
        return 2
    parola = secim.parola
    if not parola and secim.parola_dosya:
        try:
            parola = Path(secim.parola_dosya).read_text(encoding="utf-8").strip()
        except OSError as hata:
            print(f"✗ parola dosyası okunamadı: {hata}", file=sys.stderr)
            return 2
    if not parola and secim.parola_sor:
        import getpass

        parola = getpass.getpass("MQTT parolası (görünmez): ").strip()
    parola = parola or os.environ.get("MQTT_PAROLA") or str(tetik.get("push_parola", ""))
    if not parola:
        print("✗ parola gerekli (--parola ya da MQTT_PAROLA ortam değişkeni)", file=sys.stderr)
        return 2

    tetik.update({
        "aktif": True,
        "modlar": [m.strip() for m in secim.modlar.split(",") if m.strip()],
        "kontrol_ms": secim.kontrol_ms,
        "push_aktif": True,
        "push_broker": secim.broker,
        "push_port": secim.port,
        "push_konu": secim.konu,
        "push_kullanici": secim.kullanici,
        "push_parola": parola,
    })
    belge["tetik"] = tetik

    # Veri kaynağı: yerel modda cihaz PANELDEKİ değişiklikleri GÖRMEZ (panel S3'e yazar).
    if secim.yerel_veri:
        belge.setdefault("veri", {})["kaynak"] = "dosya"
        belge.setdefault("calistirma", {})["web_veri_modu"] = "yerel"
        print("✓ veri kaynağı YEREL dosyalara alındı (panel değişiklikleri görünmez)")
    elif secim.veri_adresi:
        from urllib.parse import urlparse

        adres = secim.veri_adresi.strip()
        if not adres.endswith("/"):
            adres += "/"
        konak = (urlparse(adres).hostname or "").strip()
        if not konak:
            print(f"✗ veri adresi geçersiz: {adres}", file=sys.stderr)
            return 2
        belge.setdefault("veri", {})["kaynak"] = "https"
        belge["veri"]["dosya_adresi"] = adres
        belge.setdefault("calistirma", {})["web_veri_modu"] = "https"

        # ZORUNLU: https kaynağı izin listesinde olmalı, yoksa TÜM okumalar reddedilir
        # ("adres izin listesinde değil" → beyaz ekran). Aracın bunu kendisi eklemesi gerekir.
        ag = belge.setdefault("ag", {})
        izinli = ag.get("izinli_hostlar")
        if not isinstance(izinli, list):
            izinli = []
        izinli = [str(x).strip() for x in izinli if str(x).strip()]
        # ÖNEMLİ: dosyadaki liste config varsayılanlarını EZER. Varsayılanları (veri kaynağı,
        # yayın görsellerinin alan adları) kaybetmemek için onları da ekle.
        try:
            import sys as _sys

            _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from config import ALLOWED_HOSTS as _VARSAYILAN

            for _h in _VARSAYILAN:
                if _h not in izinli:
                    izinli.append(_h)
        except Exception:  # noqa: BLE001
            pass
        if konak not in izinli:
            izinli.append(konak)
            print(f"✓ izin listesine eklendi: {konak}")
        ag["izinli_hostlar"] = izinli
        portlar = ag.get("izinli_portlar")
        if not isinstance(portlar, list):
            portlar = []
        portlar = [int(x) for x in portlar if str(x).strip().isdigit()]
        if 443 not in portlar:
            portlar.append(443)
        ag["izinli_portlar"] = portlar
        print(f"✓ veri kaynağı PANEL YAYINI: {adres} (kaynak=https · web_veri_modu=https)")
        print(f"  izinli hostlar: {izinli} · portlar: {portlar}")

    yaz(belge)
    print(f"✓ yazıldı: {AYAR_DOSYASI} (0600)")
    print(f"  broker={secim.broker}:{secim.port} · konu={secim.konu} · kullanıcı={secim.kullanici}")
    print(f"  modlar={tetik['modlar']} · kontrol_ms={secim.kontrol_ms}")

    if secim.dene:
        dene(secim.broker, secim.port, secim.konu, secim.kullanici, parola)
        if secim.veri_adresi or str(belge.get("veri", {}).get("kaynak", "")).lower() == "https":
            import urllib.request

            taban = str(belge.get("veri", {}).get("dosya_adresi", "") or "").rstrip("/")
            if taban:
                try:
                    with urllib.request.urlopen(f"{taban}/lastupdate.json", timeout=8) as yanit:
                        print(f"  ✓ veri adresi erişilebilir: {taban}/lastupdate.json (HTTP {yanit.status})")
                except Exception as hata:  # noqa: BLE001
                    print(f"  ✗ veri adresine erişilemedi: {taban} ({hata})")

    print("\nSıradaki: kiosk'u yeniden başlat → `tools/tarayici_kiosk.py --tani` çıktısında 'MQTT push … bağlı ✓'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
