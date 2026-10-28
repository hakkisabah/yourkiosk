"""olcek_test — hedef beyaz listesi ve üst sınırlar (26 Ekim i5 bulgusu).

Araç 64 iş parçacığıyla saniyede yüzlerce istek atar. `--adres` herhangi bir URL'yi kabul
ediyorsa, yanlışlıkla üçüncü taraf bir adrese koşulduğunda dışarıdan gelen bir yük testi gibi
görünür. Bu dosya iki kilidi tutar:

1. Hedef yalnız yerel adresler + `config.ALLOWED_HOSTS` + AWS dağıtımları (CloudFront/S3).
2. `--sure`/`--cihaz`/`--isci` üst sınırları: araç farkında olmadan yük testine dönüşmesin.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KIOSK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIOSK / "tools"))
sys.path.insert(0, str(KIOSK))

import olcek_test  # noqa: E402


def test_yerel_adresler_kabul():
    for adres in ("http://127.0.0.1:8000/durum.json", "https://localhost/x", "http://[::1]:9/a"):
        assert olcek_test._hedef_guvenli_mi(adres)[0], adres


def test_izinli_alan_adlari_kabul():
    for adres in ("https://kocaelieo.org.tr/durum.json",
                  "https://d2dnrvsx5eevod.cloudfront.net/kiosk/durum.json",
                  "https://yourkiosk-veri.s3.eu-central-1.amazonaws.com/durum.json"):
        assert olcek_test._hedef_guvenli_mi(adres)[0], adres


def test_yabanci_adres_reddedilir():
    """Üçüncü taraf adres → reddedilir (dış yük testi görüntüsü/başkasının kotası)."""
    for adres in ("https://kotu.example/durum.json", "https://example.com",
                  "https://kocaelieo.org.tr.kotu.example/x"):
        guvenli, neden = olcek_test._hedef_guvenli_mi(adres)
        assert not guvenli, adres
        assert "izin listesinde değil" in neden or "host" in neden


def test_sema_ve_host_zorunlu():
    assert not olcek_test._hedef_guvenli_mi("ftp://kocaelieo.org.tr/x")[0]
    assert not olcek_test._hedef_guvenli_mi("kocaelieo.org.tr/x")[0]


def test_sure_ve_cihaz_ust_siniri():
    assert olcek_test.main(["--sure", "301", "--adres", "http://127.0.0.1:1/x"]) == 2
    assert olcek_test.main(["--cihaz", "5000", "--adres", "http://127.0.0.1:1/x"]) == 2
    assert olcek_test.main(["--isci", "999", "--adres", "http://127.0.0.1:1/x"]) == 2


def test_yabanci_adresle_kosum_reddedilir(capsys):
    kod = olcek_test.main(["--adres", "https://kotu.example/durum.json", "--sure", "1",
                           "--cihaz", "1", "--aralik", "1"])
    assert kod == 2
    assert "izin listesinde değil" in capsys.readouterr().err
