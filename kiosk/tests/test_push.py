"""MQTT push: mesaj → yerel tetikleyici (mevcut yenileme zincirini besler)."""

from __future__ import annotations

import json

import config


def test_mesaj_tetikleyici_yazar(monkeypatch, tmp_path) -> None:
    from core import push, tetik

    monkeypatch.setattr(config, "TETIK_AKTIF", True, raising=False)
    monkeypatch.setattr(config, "TETIK_MODLAR", ("qt", "tarayici"), raising=False)
    monkeypatch.setattr(config, "CALISTIRMA_MODU", "tarayici", raising=False)

    hedef = tmp_path / "tetikle.json"
    monkeypatch.setattr(tetik, "dosya_yolu", lambda: hedef)

    assert push.mesaj_isle(b'{"kaynak":"panel"}') is True
    belge = json.loads(hedef.read_text(encoding="utf-8"))
    assert belge["zaman"]
    assert belge["ilceId"] == ""  # tüm cihazlar
    assert belge["aciklama"].startswith("push:")


def test_otomatik_tetikleme_kapaliysa_mesaj_yok_sayilir(monkeypatch, tmp_path) -> None:
    from core import push, tetik

    monkeypatch.setattr(config, "TETIK_AKTIF", False, raising=False)
    hedef = tmp_path / "tetikle.json"
    monkeypatch.setattr(tetik, "dosya_yolu", lambda: hedef)

    assert push.mesaj_isle("yenile") is False
    assert not hedef.exists()


def test_mod_listede_degilse_mesaj_yok_sayilir(monkeypatch, tmp_path) -> None:
    from core import push, tetik

    monkeypatch.setattr(config, "TETIK_AKTIF", True, raising=False)
    monkeypatch.setattr(config, "TETIK_MODLAR", ("tarayici",), raising=False)
    monkeypatch.setattr(config, "CALISTIRMA_MODU", "qt", raising=False)
    hedef = tmp_path / "tetikle.json"
    monkeypatch.setattr(tetik, "dosya_yolu", lambda: hedef)

    assert push.mesaj_isle("yenile") is False
    assert not hedef.exists()


def test_bos_mesaj_da_yenileme_tetikler(monkeypatch, tmp_path) -> None:
    """Mesaj gövdesi önemsiz: yalnız 'yenile' anlamı taşır."""
    from core import push, tetik

    monkeypatch.setattr(config, "TETIK_AKTIF", True, raising=False)
    monkeypatch.setattr(config, "TETIK_MODLAR", ("qt", "tarayici"), raising=False)
    monkeypatch.setattr(config, "CALISTIRMA_MODU", "qt", raising=False)
    hedef = tmp_path / "tetikle.json"
    monkeypatch.setattr(tetik, "dosya_yolu", lambda: hedef)

    assert push.mesaj_isle(b"") is True
    assert hedef.exists()


def test_push_acikken_uzun_yoklama_uzak_yoklama_yapmaz(monkeypatch) -> None:
    """Push varken tetikleyiciyi mesaj getirir; yoklama maliyeti oluşmamalı."""
    from core import push as push_modulu
    from core import tarayici
    from core import tetik as tetik_modulu

    monkeypatch.setattr(config, "TETIK_AKTIF", True, raising=False)
    monkeypatch.setattr(config, "TETIK_MODLAR", ("qt", "tarayici"), raising=False)
    monkeypatch.setattr(push_modulu, "acik", lambda: True)
    monkeypatch.setattr(config, "WEB_VERI_MODU", "https", raising=False)

    assert tarayici.uzak_yoklama_gerekli() is False

    monkeypatch.setattr(push_modulu, "acik", lambda: False)
    assert tarayici.uzak_yoklama_gerekli() is True

    monkeypatch.setattr(config, "WEB_VERI_MODU", "yerel", raising=False)
    monkeypatch.setattr(config, "KAYNAK", "dosya", raising=False)
    assert tarayici.uzak_yoklama_gerekli() is False


# ---------------------------------------------------------------- cihaz izleme (kalp atışı)
def test_durum_konusu_yayin_konusundan_turetilir(monkeypatch) -> None:
    """600 cihazın çevrimiçi durumu: `<taban>/durum/<cihazId>` (panel aynı kuralı kullanır)."""
    from core import push

    monkeypatch.setattr(config, "TETIK_PUSH_KONU", "yourkiosk/yayin", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_AKTIF", True, raising=False)
    assert push.durum_konusu("C1") == "yourkiosk/durum/C1"
    monkeypatch.setattr(config, "TETIK_PUSH_KONU", "kurum/alt/yayin", raising=False)
    assert push.durum_konusu("C2") == "kurum/alt/durum/C2"


def test_durum_konusu_joker_ve_slash_temizler(monkeypatch) -> None:
    """Kimlikte `+`/`#`/`/` olursa MQTT konusu bozulur → temizlenir (panel eşleşmesi şaşmasın)."""
    from core import push

    monkeypatch.setattr(config, "TETIK_PUSH_KONU", "yourkiosk/yayin", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_AKTIF", True, raising=False)
    assert push.durum_konusu("A/B+C#D") == "yourkiosk/durum/A-B-C-D"
    # cihaz kimliği okunamıyorsa konu yine geçerli kalır (panel bu cihazı "bilinmeyen" görür)
    monkeypatch.setattr(push, "cihaz_kimligi", lambda: "")
    assert push.durum_konusu() == "yourkiosk/durum/bilinmeyen"


def test_kalp_atisi_belgesi_alanlari(monkeypatch) -> None:
    from datetime import datetime, timezone

    from core import push

    monkeypatch.setattr(config, "CALISTIRMA_MODU", "tarayici", raising=False)
    belge = push.kalp_atisi_belgesi(True, datetime(2026, 10, 25, 9, 30, tzinfo=timezone.utc))
    assert belge["cevrimici"] is True
    assert belge["zaman"] == "2026-10-25T09:30:00Z"
    assert belge["mod"] == "tarayici"
    assert push.kalp_atisi_belgesi(False)["cevrimici"] is False
