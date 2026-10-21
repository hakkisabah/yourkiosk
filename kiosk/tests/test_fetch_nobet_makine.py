"""`tools/fetch_nobet.py` — cihaz kimliği davranışı (temiz klon senaryosu).

Neden: i5/i3 makinelerinde `fetch_nobet.py` çalıştırıldığında ham `FileNotFoundError`
traceback'i çıkıyordu ("makinebilgileri.json yok") ve kullanıcı ne yapacağını bilmiyordu.
Bu testler davranışı sabitler: anlaşılır mesaj + çıkış kodu + `--cihaz-id` ile oluşturma.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
MODUL_YOLU = KOK / "tools" / "fetch_nobet.py"


def _modul():
    spec = importlib.util.spec_from_file_location("fetch_nobet_test", MODUL_YOLU)
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


def test_kimlik_yoksa_traceback_degil_cozum_yazar(tmp_path, capsys) -> None:
    modul = _modul()
    with pytest.raises(SystemExit) as hata:
        modul.makine_bilgisi(None, kok=tmp_path)
    assert hata.value.code == 3
    mesaj = capsys.readouterr().err
    assert "makinebilgileri.json yok" in mesaj
    assert "--cihaz-id" in mesaj
    assert "i5/i3" in mesaj  # ajan makinelerinde gerekmediği de yazılı


def test_cihaz_id_verilince_dosya_olusturulur(tmp_path) -> None:
    modul = _modul()
    veri = modul.makine_bilgisi("TEST-123", kok=tmp_path)
    assert veri == {"clientID": "TEST-123"}
    yazilan = json.loads((tmp_path / "makinebilgileri.json").read_text(encoding="utf-8"))
    assert yazilan["clientID"] == "TEST-123"


def test_var_olan_dosya_okunur(tmp_path) -> None:
    modul = _modul()
    (tmp_path / "makinebilgileri.json").write_text('{"clientID": "VAR-1"}', encoding="utf-8")
    assert modul.makine_bilgisi("YOK-SAYILMALI", kok=tmp_path)["clientID"] == "VAR-1"


def test_bozuk_dosya_anlasilir_hata(tmp_path, capsys) -> None:
    modul = _modul()
    (tmp_path / "makinebilgileri.json").write_text("{bozuk json", encoding="utf-8")
    with pytest.raises(SystemExit) as hata:
        modul.makine_bilgisi(None, kok=tmp_path)
    assert hata.value.code == 3
    assert "okunamadı" in capsys.readouterr().err


def test_clientid_bossa_hata(tmp_path, capsys) -> None:
    modul = _modul()
    (tmp_path / "makinebilgileri.json").write_text('{"clientID": "  "}', encoding="utf-8")
    with pytest.raises(SystemExit) as hata:
        modul.makine_bilgisi(None, kok=tmp_path)
    assert hata.value.code == 3
    assert "clientID" in capsys.readouterr().err
