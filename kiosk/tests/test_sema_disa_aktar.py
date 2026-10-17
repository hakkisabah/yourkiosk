"""Panel ile kiosk'un ayar şeması ayrışmasın: dışa aktarılan şema güncel olmalı.

`tools/sema_disa_aktar.py` `ayarlar.KURALLAR`'ı `panel/src/domain/sema.generated.json`
dosyasına yazar; panel bu dosyayı doğrulama için kullanır. Şemaya anahtar eklenip
dosya yenilenmezse bu test kırılır ve yapılacak işi söyler.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "tools"))

import sema_disa_aktar  # noqa: E402

HEDEF = sema_disa_aktar.HEDEF


def test_sema_dosyasi_guncel() -> None:
    if not HEDEF.parent.is_dir():
        pytest.skip("yönetim paneli bu kopyada yok (panel/src/domain/)")
    assert HEDEF.is_file(), "şema dosyası yok — çalıştır: python3 tools/sema_disa_aktar.py"
    assert HEDEF.read_text(encoding="utf-8") == sema_disa_aktar.metin(), (
        "şema güncel değil — çalıştır: python3 tools/sema_disa_aktar.py"
    )


def test_sema_tum_anahtarlari_kapsar() -> None:
    sema = sema_disa_aktar.sema()
    anahtarlar = {a["tam"] for g in sema["gruplar"] for a in g["anahtarlar"]}
    beklenen = {f"{g}.{a}" for (g, a) in sema_disa_aktar.ayarlar.KURALLAR}
    assert anahtarlar == beklenen


def test_sema_araliklari_python_ile_ayni() -> None:
    """Panelin gördüğü aralıklar `ayarlar.KURALLAR` ile birebir aynı olmalı."""
    sema = sema_disa_aktar.sema()
    for g in sema["gruplar"]:
        for a in g["anahtarlar"]:
            cfg_ad, tip, alt, ust = sema_disa_aktar.ayarlar.KURALLAR[(g["ad"], a["ad"])]
            if a["izinli"] is None and isinstance(alt, (int, float)) and not isinstance(alt, bool):
                assert a["alt"] == alt, a["tam"]
            if isinstance(ust, (int, float)) and not isinstance(ust, bool):
                assert a["ust"] == ust, a["tam"]
            assert a["varsayilan"] == getattr(sema_disa_aktar.config, cfg_ad, None)
