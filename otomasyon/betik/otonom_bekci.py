#!/usr/bin/env python3
"""otonom_bekci — otonom koordinatörün bekçisi.

otonom-tik.service bir oneshot tik'tir; timer onu aralıklı çalıştırır. Bu bekçi
ayrı bir timer ile çalışır ve şunları denetler:
  - otonom-tik.timer aktif mi (ölmüş/başarısız ise reset-failed + start),
  - otonom-tik.service takılı mı (aktifse dokunma),
  - durum.json'daki son tik kalp atışı bayat mı (SESSIZ_DK),
  - birim dosyaları kurulu mu (değilse onarmaya kalkışma).
Onarımı ONARIM_ARALIGI_DK'dan sık yapmaz; böylece kırık bir kurulumda döngü
üretmez, yalnız günlüğe yazar.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
EV = Path(os.environ.get("OTONOM_EV", str(Path.home() / ".local" / "state" / "yourkiosk-otonom")))
DURUM = EV / "durum.json"
BEKCI_DURUM = EV / "bekci-durum.json"
GUNLUK = EV / "bekci.log"
TIK_TIMER = "otonom-tik.timer"
TIK_SERVIS = "otonom-tik.service"
SESSIZ_DK = int(os.environ.get("OTONOM_AZAMI_SESSIZ_DK", "90"))
ONARIM_ARALIGI_DK = int(os.environ.get("OTONOM_ONARIM_ARALIGI_DK", "15"))


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def damga(an: datetime) -> str:
    return an.strftime("%Y-%m-%dT%H:%M:%SZ")


def gunluk(mesaj: str) -> None:
    try:
        EV.mkdir(parents=True, exist_ok=True)
        with GUNLUK.open("a", encoding="utf-8") as dosya:
            dosya.write(f"[{damga(simdi())}] {mesaj}" + chr(10))
    except OSError:
        pass
    print(mesaj)


def systemctl(*arg: str) -> int:
    try:
        return subprocess.run(["systemctl", "--user", *arg],
                              capture_output=True, text=True, timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return 127


def json_oku(yol: Path) -> dict:
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
        return veri if isinstance(veri, dict) else {}
    except (OSError, ValueError):
        return {}


def durum_yaz(veri: dict) -> None:
    try:
        EV.mkdir(parents=True, exist_ok=True)
        gecici = BEKCI_DURUM.with_suffix(".tmp")
        gecici.write_text(json.dumps(veri, ensure_ascii=False, sort_keys=True) + chr(10),
                          encoding="utf-8")
        os.chmod(gecici, 0o600)
        os.replace(gecici, BEKCI_DURUM)
    except OSError:
        pass


def son_tik_zamani(veri: dict) -> datetime | None:
    ham = str(veri.get("son_tik") or "")
    if not ham:
        return None
    try:
        return datetime.fromisoformat(ham.replace("Z", "+00:00"))
    except ValueError:
        return None


def karar_ver(aktif_timer: bool, aktif_servis: bool, son_tik: datetime | None,
              an: datetime) -> dict:
    if aktif_servis:
        return {"eylem": "bekle", "neden": "tik sürüyor"}
    if not aktif_timer:
        return {"eylem": "onar", "neden": "zamanlayici aktif değil"}
    if son_tik is None:
        return {"eylem": "onar", "neden": "kalp atışı yok"}
    yas = (an - son_tik).total_seconds() / 60
    if yas > SESSIZ_DK:
        return {"eylem": "onar", "neden": f"son tik {yas:.0f} dk önce (eşik {SESSIZ_DK})"}
    return {"eylem": "bekle", "neden": f"sağlıklı (son tik {yas:.0f} dk önce)"}


def onar() -> bool:
    systemctl("reset-failed", TIK_SERVIS)
    systemctl("reset-failed", TIK_TIMER)
    return systemctl("start", TIK_TIMER) == 0


def tik(kuru: bool = False) -> int:
    birim = Path.home() / ".config" / "systemd" / "user" / TIK_TIMER
    if not birim.is_file():
        gunluk(f"ENGE: {birim} kurulu değil — onarım yapılmaz (otonom-kur.sh çalıştırın)")
        return 2
    aktif_timer = systemctl("is-active", "--quiet", TIK_TIMER) == 0
    aktif_servis = systemctl("is-active", "--quiet", TIK_SERVIS) == 0
    karar = karar_ver(aktif_timer, aktif_servis, son_tik_zamani(json_oku(DURUM)), simdi())
    if kuru:
        print(json.dumps(karar, ensure_ascii=False))
        return 0
    if karar["eylem"] == "bekle":
        gunluk("sağlıklı: " + karar["neden"])
        return 0

    onceki = json_oku(BEKCI_DURUM)
    try:
        son_onar = datetime.fromisoformat(str(onceki.get("son_onar") or "").replace("Z", "+00:00"))
    except ValueError:
        son_onar = None
    if son_onar is not None:
        yas = (simdi() - son_onar).total_seconds() / 60
        if yas < ONARIM_ARALIGI_DK:
            gunluk(f"onarım ertelendi ({yas:.0f} dk önce onarıldı): {karar['neden']}")
            return 0

    basarili = onar()
    durum_yaz({"son_onar": damga(simdi()), "neden": karar["neden"], "basarili": basarili})
    gunluk(("onarıldı: " if basarili else "onarılamadı: ") + karar["neden"])
    return 0 if basarili else 1


def durum_bas() -> int:
    print(json.dumps({"durum": json_oku(DURUM), "bekci": json_oku(BEKCI_DURUM)},
                     ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ayar = argparse.ArgumentParser(description="otonom koordinatör bekçisi")
    ayar.add_argument("--kuru", action="store_true", help="kararı göster, onarma")
    ayar.add_argument("--durum", action="store_true", help="yerel durum")
    secim = ayar.parse_args()
    if secim.durum:
        return durum_bas()
    return tik(kuru=secim.kuru)


if __name__ == "__main__":
    raise SystemExit(main())
