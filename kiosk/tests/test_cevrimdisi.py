"""Çevrimdışı açılış: ağ yoksa disk önbelleği kullanılmalı.

Önceki davranış: `lastupdate` ağdan okunamayınca damga boş kalıyor, `veri_oku(dosya, damga)` hiç
çağrılmıyor ve cihaz yeniden başladıktan sonra internetsiz **veri göstermiyordu**
(bellek önbelleği yalnız aynı çalışma oturumunda yardımcı oluyordu).
"""

from __future__ import annotations

import json

import config


def test_ag_yokken_kayitli_damga_ve_disk_onbellegi_kullanilir(monkeypatch) -> None:
    from core import onbellek, veri_kaynagi

    monkeypatch.setattr(config, "KAYNAK", "https", raising=False)
    monkeypatch.setattr(config, "DOSYA_ADRESI", "https://ornek/", raising=False)
    monkeypatch.setattr(config, "ONBELLEK_AKTIF", True, raising=False)

    # ağ yok: lastupdate okunamıyor
    monkeypatch.setattr(veri_kaynagi, "lastupdate_yukle", lambda: None)
    # diske yazılmış son damga
    monkeypatch.setattr(onbellek, "kayitli_damga", lambda: "D-2026")
    # diskteki veri
    govde = json.dumps({"ilce": "Çayırova"}).encode("utf-8")
    monkeypatch.setattr(onbellek, "veri_oku", lambda ad, damga="": govde if damga == "D-2026" else None)

    def ag_yok(*_a, **_k):
        raise AssertionError("önbellek varken ağa çıkılmamalı")

    monkeypatch.setattr(veri_kaynagi, "indir", ag_yok)
    veri_kaynagi._lastupdate_damgasi = None

    assert veri_kaynagi._oku("match.json") == {"ilce": "Çayırova"}


def test_damga_ne_agdan_ne_diskten_gelmiyorsa_none(monkeypatch) -> None:
    from core import onbellek, veri_kaynagi

    monkeypatch.setattr(config, "KAYNAK", "https", raising=False)
    monkeypatch.setattr(config, "DOSYA_ADRESI", "https://ornek/", raising=False)
    monkeypatch.setattr(veri_kaynagi, "lastupdate_yukle", lambda: None)
    monkeypatch.setattr(onbellek, "kayitli_damga", lambda: "")
    monkeypatch.setattr(onbellek, "veri_oku", lambda ad, damga="": None)

    def hata(*_a, **_k):
        from security.network import AgHatasi

        raise AgHatasi("ağ yok")

    monkeypatch.setattr(veri_kaynagi, "indir", hata)
    veri_kaynagi._lastupdate_damgasi = None
    veri_kaynagi._önbellek.clear()  # aynı oturumda önceki testten kalan bellek yedeği olmasın
    assert veri_kaynagi._oku("match.json") is None
