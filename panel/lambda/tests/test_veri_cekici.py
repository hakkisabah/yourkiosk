"""veri_cekici: kaynak JSON -> lastSystemData/lastupdate (ağsız)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import veri_cekici


HAM = {
    "1": {
        "eczane": "Deneme", "ilce": "Çayırova", "bolge": "1.Bölge",
        "adres": "Adres", "tel": "0262", "baslangic": "2026-11-20 08:30:00",
        "bitis": "2026-11-21 08:30:00",
    }
}


class SahteS3:
    def __init__(self) -> None:
        self.yazilan: dict[str, bytes] = {}

    def get_object(self, **kw):  # noqa: ANN003
        raise KeyError(kw["Key"])

    def put_object(self, **kw):  # noqa: ANN003
        self.yazilan[kw["Key"]] = kw["Body"]


def test_sablona_cevir_gun_ilce_bolge() -> None:
    agac = veri_cekici.sablona_cevir(HAM)
    assert "T20261120" in agac
    ilce = next(iter(agac["T20261120"]))
    kayit = agac["T20261120"][ilce][0]
    bolge = next(iter(kayit.values()))[0]
    assert bolge["eczane"] == "Deneme"
    assert bolge["start"] == "20/11/2026 08:30"


def test_guncelle_iki_dosya_yazar() -> None:
    s3 = SahteS3()
    sonuc = veri_cekici.guncelle(s3, "kova", "kiosk/", ham=HAM)
    assert sonuc["degisti"] is True
    assert "kiosk/lastSystemData.json" in s3.yazilan
    assert "kiosk/lastupdate.json" in s3.yazilan
    belge = json.loads(s3.yazilan["kiosk/lastSystemData.json"])
    assert "Nobetler" in belge and belge["Yayinlar"] == {}
    assert belge["lastUpdate"] == sonuc["lastupdate"]


def test_ayni_veri_degisiklik_yazmaz() -> None:
    s3 = SahteS3()
    veri_cekici.guncelle(s3, "kova", "kiosk/", ham=HAM)
    # ikinci kez: mevcut belgeyi taklit et
    belge = json.loads(s3.yazilan["kiosk/lastSystemData.json"])
    class Mevcut(SahteS3):
        def get_object(self, **kw):  # noqa: ANN003
            return {"Body": type("B", (), {"read": lambda self: json.dumps(belge).encode()})()}
    s3b = Mevcut()
    sonuc = veri_cekici.guncelle(s3b, "kova", "kiosk/", ham=HAM)
    assert sonuc["degisti"] is False
    assert s3b.yazilan == {}
