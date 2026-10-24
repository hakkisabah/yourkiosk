"""TARAYICI ARAYÜZ PAKETİ BAYAT MI? — "değişiklik gelmiyor" sınıfına karşı kilit.

Gerçek olay: Qt kiosk değişikliği gösteriyordu, tarayıcı kiosk göstermiyordu. Neden:
`web/dist` (tarayıcının yüklediği derlenmiş paket) **12:31**'de üretilmişti, oysa `web/src`
çok daha sonra değişmişti. `git pull` derlenmiş paketi getirmez (`web/dist/` .gitignore'da) →
cihaz **eski JavaScript'i** çalıştırmaya devam etti. Sunucu tarafı doğru olsa bile ekranda
eski davranış görünür.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


@pytest.fixture()
def sahte_proje(tmp_path, monkeypatch):
    """Küçük bir proje ağacı: web/src + web/dist."""
    import core.tarayici as tarayici

    (tmp_path / "kiosk").mkdir()
    kaynak = tmp_path / "web" / "src"
    kaynak.mkdir(parents=True)
    (kaynak / "kiosk.ts").write_text("// arayüz", encoding="utf-8")
    dist = tmp_path / "web" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    # KOK = <proje>/kiosk ; web projesi komşu dizinde
    monkeypatch.setattr(tarayici, "KOK", tmp_path / "kiosk")
    (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
    return tarayici, tmp_path, kaynak, dist


def test_dist_yoksa_bayat(sahte_proje) -> None:
    tarayici, _kok, _kaynak, dist = sahte_proje
    import shutil

    shutil.rmtree(dist)
    durum = tarayici.dist_durumu()
    assert durum["var"] is False
    assert durum["bayat"] is True, "dist yokken 'bayat' demeli (kullanıcı derlemeyi unutmasın)"


def test_kaynak_dist_ten_yeni_ise_bayat(sahte_proje) -> None:
    tarayici, _kok, kaynak, _dist = sahte_proje
    # kaynağı dist'ten DAHA YENİ yap
    import os
    import time

    gelecek = time.time() + 60
    os.utime(kaynak / "kiosk.ts", (gelecek, gelecek))
    durum = tarayici.dist_durumu()
    assert durum["var"] is True
    assert durum["bayat"] is True
    assert "kiosk.ts" in str(durum.get("en_yeni_kaynak", "")), (
        "hangi dosyanın bayatlettiği görünmeli (kullanıcı neyi derleyeceğini bilsin)"
    )


def test_kaynak_eski_ise_taze(sahte_proje) -> None:
    tarayici, _kok, kaynak, dist = sahte_proje
    import os
    import time

    eski = time.time() - 600
    os.utime(kaynak / "kiosk.ts", (eski, eski))
    gelecek = time.time() + 60
    os.utime(dist / "index.html", (gelecek, gelecek))
    durum = tarayici.dist_durumu()
    assert durum["bayat"] is False


def test_tani_raporunda_gorunur(sahte_proje) -> None:
    """Bayatlık `--tani` raporunda AÇIKÇA yazmalı (kullanıcı oraya bakıyor)."""
    tarayici, _kok, kaynak, _dist = sahte_proje
    import os
    import time

    gelecek = time.time() + 60
    os.utime(kaynak / "kiosk.ts", (gelecek, gelecek))
    metin = "\n".join(tarayici.tani_raporu("98273648723468273"))
    assert "BAYAT" in metin.upper(), f"--tani bayat paketi söylemiyor:\n{metin[-400:]}"
