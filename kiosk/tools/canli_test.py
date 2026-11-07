#!/usr/bin/env python3
"""CANLI TEST — "değişiklik neden ekrana gelmiyor?" sorusunu 20 saniyede yanıtlar.

Kiosk ÇALIŞIRKEN ayrı bir terminalde çalıştırın:

    .venv/bin/python tools/canli_test.py

Zincirin her halkasını AYRI ölçer ve nerede koptuğunu yazar:

  1. PANEL/VERİ  : uzak `durum.json` + `lastupdate.json` damgası (panel yazdı mı?)
  2. DİSK        : cihazın disk önbelleğindeki damga (veri indi mi?)
  3. MQTT        : broker bağlantısı, konuya abonelik ve 15 sn içinde mesaj geliyor mu?
  4. YEREL TETİK : `tetikle.json` mtime (push yerel dosyaya yazdı mı?)
  5. ARAYÜZ      : yerel sunucudan `index.html` + ana JS varlığı (beyaz ekran kapısı)

Çıkış kodu 0 = zincir sağlam, 1 = kopukluk var (hangi halka yazılır).
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import config  # noqa: E402

# ayarlar.json DEĞERLERİ: DOSYA_ADRESI / TETIK_PUSH_* config'e buradan gelir (yoksa araç
# "broker boş" der — yanıltıcı). Uygulama ÇAĞRI ANINDA yapılır, modül düzeyinde DEĞİL:
# 6 Kasım bulgusu — modül düzeyindeki `ayarlar.uygula()` import sırasında `config.KAYNAK` ve
# `config.DOSYA_ADRESI`ni kalıcı olarak değiştiriyordu. Bu aracı import eden test modülü
# (`tests/test_canli_test_guncelleme.py`) yüzünden tam pakette `ayarlar.uygula()` çağıran
# testler uzak `ayarlar.json`u çekmeye çalışıp test SIRASINA BAĞLI kırmızı üretiyordu.
import ayarlar  # noqa: E402


def ayarlari_uygula() -> None:
    """`ayarlar.json`ı config'e uygular — YALNIZ CLI (`main`) çağırır."""
    ayarlar.uygula()


def _bas(h: str) -> None:
    print(f"\n── {h} " + "─" * max(0, 58 - len(h)))


def _uzak(ad: str) -> dict:
    taban = str(getattr(config, "DOSYA_ADRESI", "") or "").rstrip("/")
    if not taban:
        return {}
    istek = urllib.request.Request(f"{taban}/{ad}", headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(istek, timeout=12) as y:
        return json.loads(y.read())


def _yerel_damga() -> str:
    from core import onbellek

    kayit = onbellek.veri_kayit("lastSystemData.json") or {}
    return str(kayit.get("lastupdate", "") or "")


def _tetik_mtime() -> str:
    yol = KOK / str(getattr(config, "TETIK_DOSYASI", "tetikle.json"))
    if not yol.is_file():
        return "(dosya yok)"
    return datetime.fromtimestamp(yol.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def mqtt_test(sure: float = 15.0) -> tuple[str, str]:
    """Broker'a bağlan, konuya abone ol, mesaj bekleyen bir cihaz gibi davran.

    Dönüş: `("ok" | "atlandi" | "hata", metin)`.

    NEDEN ÜÇ DURUM (i5 bulgusu, PR #84): push yapılandırılmamış cihazda (varsayılan:
    `push_aktif=False`, broker/konu boş) MQTT halkası "hata" sayılıyordu → `guncelle.sh`
    sağlık kapısı HER ZAMAN düşüyor, cihaz her gece güncellemeyi geri alıyordu. Kapalı bir
    halka "arıza" değildir; atlanır ve çıkış kodunu etkilemez.
    """
    try:
        import paho.mqtt.client as mqtt  # type: ignore
    except ImportError:
        return "hata", "paho-mqtt yok (venv: .venv/bin/python)"

    broker = str(getattr(config, "TETIK_PUSH_BROKER", "") or "")
    port = int(getattr(config, "TETIK_PUSH_PORT", 8883))
    konu = str(getattr(config, "TETIK_PUSH_KONU", "") or "")
    if not broker or not konu:
        return "atlandi", "push kapalı (ayarlarda broker/konu boş) — MQTT halkası atlandı"

    sonuc = {"bagli": False, "mesaj": 0, "hata": ""}

    def baglandi(c, u, f, rc, p=None):
        sonuc["bagli"] = int(getattr(rc, "value", rc) or 0) == 0
        if sonuc["bagli"]:
            c.subscribe(konu, qos=1)

    def mesaj(c, u, m):
        sonuc["mesaj"] += 1

    if hasattr(mqtt, "CallbackAPIVersion"):
        istemci = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"canli-test-{os.getpid()}")
    else:  # pragma: no cover
        istemci = mqtt.Client(client_id=f"canli-test-{os.getpid()}")
    kullanici = str(getattr(config, "TETIK_PUSH_KULLANICI", "") or "")
    if kullanici:
        istemci.username_pw_set(kullanici, str(getattr(config, "TETIK_PUSH_PAROLA", "") or ""))
    istemci.on_connect = baglandi
    istemci.on_message = mesaj
    try:
        if port == 8883:
            istemci.tls_set()
        istemci.connect(broker, port, keepalive=30)
        istemci.loop_start()
    except Exception as hata:  # noqa: BLE001
        return "hata", f"bağlanamadı: {hata}"

    bitis = time.monotonic() + sure
    while time.monotonic() < bitis and sonuc["mesaj"] == 0:
        time.sleep(0.3)
    try:
        istemci.loop_stop()
        istemci.disconnect()
    except Exception:  # noqa: BLE001
        pass

    if not sonuc["bagli"]:
        return "hata", "broker bağlantısı KURULAMADI (kullanıcı/parola/TLS)"
    if sonuc["mesaj"] == 0:
        return "ok", f"abonelik tamam, {int(sure)} sn içinde mesaj gelmedi (panelden 'Bildir' deneyin)"
    return "ok", f"mesaj ALINDI ({sonuc['mesaj']}) — push halkası sağlam"


def surec_denetimi() -> tuple[bool, str]:
    """Kiosk süreci GERÇEKTEN çalışıyor mu, hangi kodla, ne zaman başladı?

    NEDEN: disk damgası hiç ilerlemiyorsa ilk şüphe "kod hatası" değil, "süreç ölü/eski kod".
    Bu kontrol süreç yoksa ya da süreç, düzeltme commit'inden ÖNCE başladıysa bunu söyler.
    """
    import subprocess
    from datetime import datetime as _dt

    bulunan = []
    for kok_dizin in Path("/proc").iterdir():
        if not kok_dizin.name.isdigit():
            continue
        try:
            cmdline = (kok_dizin / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
        except OSError:
            continue
        if ("main.py" not in cmdline and "tarayici_kiosk.py" not in cmdline) or "canli_test" in cmdline:
            continue
        try:
            cwd = str((kok_dizin / "cwd").resolve())
            baslama = float((kok_dizin / "stat").read_text().rsplit(")", 1)[1].split()[19]) / 100  # starttime (s, boot)
            # gerçek başlama anı: /proc/uptime ile
            with open("/proc/uptime") as u:
                calisma = float(u.read().split()[0])
            baslama_ts = time.time() - (calisma - baslama)
        except (OSError, ValueError, IndexError):
            cwd, baslama_ts = "?", 0.0
        bulunan.append((kok_dizin.name, cmdline.strip(), cwd, baslama_ts))

    if not bulunan:
        return False, "kiosk süreci ÇALIŞMIYOR (main.py / tarayici_kiosk.py bulunamadı)"

    satirlar = []
    for pid, cmd, cwd, ts in bulunan:
        ne_zaman = _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "?"
        # süreç, çalıştığı dizindeki kodun SON commit'inden önce mi başlamış?
        eski = ""
        try:
            mtime = (Path(cwd) / "pharmacy_app.py").stat().st_mtime
            if ts and mtime > ts:
                eski = " ← ESKİ KOD (dosyalar süreç başladıktan SONRA değişti: YENİDEN BAŞLAT)"
        except OSError:
            pass
        satirlar.append(f"pid {pid} · başlama {ne_zaman} · dizin {cwd}{eski}")
    return True, " | ".join(satirlar)


def arayuz_test(port: int | None = None) -> tuple[bool, str]:
    """Yerel HTTP sunucusundan ARAYÜZ PAKETİNİ doğrular (index.html + ana JS varlığı).

    NEDEN (6 Kasım i5 bulgusu, orta): sağlık kapısı yalnız süreç/veri/disk/MQTT/tetik
    halkalarına bakıyordu; `vite` derlemesi yarıda kalsa dist boşalır, cihaz BEYAZ EKRANLA
    açılır ve kapı bunu "sağlıklı" sayardı. Bu halka tam olarak o arızayı ölçer:
    `index.html` 200 + text/html olmalı ve işaret ettiği ana JS varlığı 200 + JS içerik
    tipiyle gelmeli (boş/yarım paket yakalanır).
    """
    import re

    port = port or int(getattr(config, "WEB_SUNUCU_PORTU", 8090))
    taban = f"http://127.0.0.1:{port}"

    def get(yol: str) -> tuple[int, str, bytes]:
        with urllib.request.urlopen(f"{taban}{yol}", timeout=5) as r:  # noqa: S310 — sabit yerel taban
            return r.status, r.headers.get("Content-Type", ""), r.read()

    try:
        kod, tur, govde = get("/index.html")
    except Exception as hata:  # noqa: BLE001
        return False, f"yerel sunucuya ulaşılamadı ({taban}/index.html): {hata}"

    if kod != 200:
        return False, f"index.html HTTP {kod} (200 bekleniyordu)"
    if "text/html" not in tur.lower():
        return False, f"index.html içerik tipi '{tur}' (text/html bekleniyordu)"
    metin = govde.decode("utf-8", errors="replace")
    if "yourkiosk" not in metin.lower():
        return False, "index.html kiosk işaretini taşımıyor (yanlış/boş paket)"

    # Ana JS varlığı: <script type="module" src="/assets/index-xxxx.js">
    m = re.search(r'<script[^>]+src="([^"]+\.js)"', metin) or re.search(r'src="([^"]+\.js)"', metin)
    if not m:
        return False, "index.html hiçbir JS varlığına işaret etmiyor (derleme yarım kalmış)"
    varlik = m.group(1)
    yol = varlik if varlik.startswith("/") else "/" + varlik.lstrip("./")
    try:
        k_v, t_v, b_v = get(yol)
    except Exception as hata:  # noqa: BLE001
        return False, f"ana JS varlığı indirilemedi ({yol}): {hata}"
    if k_v != 200:
        return False, f"ana JS varlığı {yol} HTTP {k_v} (200 bekleniyordu)"
    if "javascript" not in t_v.lower() and "ecmascript" not in t_v.lower():
        return False, f"ana JS varlığı içerik tipi '{t_v}' (javascript bekleniyordu)"
    if len(b_v) < 100:
        return False, f"ana JS varlığı {yol} yalnız {len(b_v)} bayt (boş paket)"
    return True, f"index.html + ana JS varlığı ({yol}, {len(b_v) // 1024} KB) sunuluyor"


def main(sure: float = 15.0) -> int:
    ayarlari_uygula()  # import sırasında DEĞİL: yalnız gerçek koşuda
    print("=" * 62)
    print("CANLI ZİNCİR TESTİ — kiosk çalışırken çalıştırın")
    print("=" * 62)

    sorun = 0
    l_damga = ""

    _bas("0) ÇALIŞAN KIOSK SÜRECİ")
    var, metin = surec_denetimi()
    print(("✓ " if var else "✗ ") + metin)
    if not var:
        sorun += 1

    _bas("1) PANEL / UZAK VERİ")
    try:
        durum = _uzak("durum.json")
        last = _uzak("lastupdate.json")
        d_damga = str(durum.get("lastupdate", "") or "")
        l_damga = str(last.get("lastupdate", "") or "")
        print(f"durum.json     : {d_damga or '(yok)'}")
        print(f"lastupdate.json: {l_damga or '(yok)'}")
        if d_damga and l_damga and d_damga != l_damga:
            print("✗ İKİSİ FARKLI — panel yarım yazmış (Bildir/Kaydet sırasında tekrar deneyin)")
            sorun += 1
        elif not l_damga:
            print("✗ uzak damga okunamadı")
            sorun += 1
        else:
            print("✓ panel verisi okunabiliyor")
    except Exception as hata:  # noqa: BLE001
        print(f"✗ uzak dosyalar okunamadı: {hata}")
        sorun += 1

    _bas("2) CİHAZ DİSKİ")
    try:
        disk = _yerel_damga()
        print(f"disk damgası   : {disk or '(yok)'}")
        if disk and l_damga and disk != l_damga:
            print("→ disk ESKİ: yoklama turunda yenilenecek (bu normal, bekleme süresi kadar)")
        elif disk == l_damga:
            print("✓ disk güncel")
    except Exception as hata:  # noqa: BLE001
        print(f"! disk okunamadı: {hata}")

    _bas("3) MQTT / PUSH")
    mqtt_durum, metin = mqtt_test(sure)
    if mqtt_durum == "atlandi":
        print(f"- {metin}")
    else:
        print(("✓ " if mqtt_durum == "ok" else "✗ ") + metin)
        if mqtt_durum != "ok":
            sorun += 1

    _bas("4) YEREL TETİK DOSYASI")
    print(f"tetikle.json   : son yazım {_tetik_mtime()}")

    _bas("5) ARAYÜZ PAKETİ (beyaz ekran kapısı)")
    arayuz_var, metin = arayuz_test()
    print(("✓ " if arayuz_var else "✗ ") + metin)
    if not arayuz_var:
        sorun += 1

    _bas("SONUÇ")
    if sorun == 0:
        print("✓ zincir sağlam. Panelde değişiklik yapıp 'Bildir' deyin; 2 sn içinde gelmeli.")
        print("  Gelmezse: bu betiği Bildir'e bastıktan hemen SONRA tekrar çalıştırın")
        print("  (3. adım 'mesaj ALINDI' demeli; demiyorsa panel tarayıcısı yayın yapamıyor).")
    else:
        print(f"✗ {sorun} halkada sorun var — yukarıdaki ✗ satırlarına bakın.")
    return 0 if sorun == 0 else 1


if __name__ == "__main__":
    import argparse

    _ayristirici = argparse.ArgumentParser(description="Canlı zincir testi (kiosk çalışırken).")
    _ayristirici.add_argument(
        "--sure", type=float, default=15.0,
        help="MQTT mesaj bekleme süresi, saniye (varsayılan 15; guncelle.sh 15 verir)",
    )
    _arg = _ayristirici.parse_args()
    raise SystemExit(main(_arg.sure))
