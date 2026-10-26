"""CANLIYA GEÇİŞ belgelerindeki araç komutları GERÇEKTEN çalışmalı (i5 bulgusu 4).

ÖLÇÜLEN (26 Ekim): `deploy/CANLIYA-GECIS.md` cihaz kurulumunda
`tools/fetch_nobet.py --cihaz-id <ID> --taban https://<dağıtım>/` yazıyordu; araçta `--taban`
seçeneği YOK (`error: unrecognized arguments: --taban`) → canlıya geçiş listesi olduğu gibi
uygulanamıyordu.

Bu test belgedeki her `tools/<araç>.py` satırındaki seçenekleri aracın GERÇEK `--help` çıktısıyla
karşılaştırır. Yeni bir yanlış seçenek yazılırsa (ya da araçtan seçenek kaldırılırsa) kırmızı olur.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DEPO = Path(__file__).resolve().parents[2]
KIOSK = DEPO / "kiosk"
BELGELER = (
    DEPO / "deploy" / "CANLIYA-GECIS.md",
    DEPO / "deploy" / "README.md",
)

ARAC = re.compile(r"tools/([A-Za-z0-9_-]+)\.py")
SECENEK = re.compile(r"(?<![\w-])(--[A-Za-z0-9][A-Za-z0-9-]*)")


def _komut_satirlari(metin: str) -> list[str]:
    """Kod bloklarındaki, `\\` ile süren satırları BİRLEŞTİRİP döner (yorumlar hariç)."""
    bloklar = re.findall(r"```(?:bash|sh)?\n(.*?)```", metin, re.S)
    komutlar: list[str] = []
    for blok in bloklar:
        birikim = ""
        for ham in blok.splitlines():
            satir = ham.rstrip()
            if satir.lstrip().startswith("#"):
                continue
            if satir.endswith("\\"):
                birikim += satir[:-1] + " "
                continue
            birikim += satir
            if birikim.strip():
                komutlar.append(birikim.strip())
            birikim = ""
        if birikim.strip():
            komutlar.append(birikim.strip())
    return komutlar


def _yardim(arac: str) -> str:
    sonuc = subprocess.run(
        [sys.executable, f"tools/{arac}.py", "--help"],
        cwd=str(KIOSK), capture_output=True, text=True, timeout=120,
    )
    assert sonuc.returncode == 0, f"{arac} --help başarısız: {sonuc.stderr[:400]}"
    return sonuc.stdout


def test_belgelerdeki_arac_secenekleri_gercek():
    yardimlar: dict[str, str] = {}
    hatalar: list[str] = []
    for belge in BELGELER:
        assert belge.is_file(), f"belge yok: {belge}"
        for komut in _komut_satirlari(belge.read_text(encoding="utf-8")):
            for arac in set(ARAC.findall(komut)):
                yardim = yardimlar.setdefault(arac, _yardim(arac))
                for secenek in SECENEK.findall(komut):
                    # `--flag=değer` biçimini de kabul et
                    if secenek not in yardim:
                        hatalar.append(f"{belge.name}: {arac}.py {secenek} (araçta yok)")
    assert not hatalar, "belgede araca ait OLMAYAN seçenekler:\n  " + "\n  ".join(sorted(set(hatalar)))


def test_fetch_nobet_taban_secenegi_yok_belge_de_kullanmaz():
    """Regresyon kilidi: `--taban` araca eklenmediyse belgede KOMUT olarak da geçmemeli."""
    yardim = _yardim("fetch_nobet")
    belge = (DEPO / "deploy" / "CANLIYA-GECIS.md").read_text(encoding="utf-8")
    komutlar = [k for k in _komut_satirlari(belge) if "fetch_nobet.py" in k]
    if "--taban" not in yardim:
        kacak = [k for k in komutlar if "--taban" in k]
        assert not kacak, f"fetch_nobet.py'de olmayan --taban belgede komut olarak var: {kacak}"
