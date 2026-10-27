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


def test_durum_konusu_acl_ve_panel_sozlesmesine_uyar(monkeypatch) -> None:
    """26 Ekim i5 bulgusu: yayıncı kimliği yalnız `/ + #` temizliyordu.

    ACL aracı (`cihaz-ekle.sh`) `^[A-Za-z0-9_-]{1,40}$`, panel `^[A-Za-z0-9_-]+$` ve ≤64 istiyor.
    Türkçe karakter/boşluk/nokta içeren kimlik ACL'e yazılamıyor → cihaz panelde sonsuza kadar
    "bilinmiyor" kalıyordu. Tek normalizasyon kuralı: ASCII dışı ve joker → `-`, en çok 40.
    """
    import re

    from core import push

    monkeypatch.setattr(config, "TETIK_PUSH_KONU", "yourkiosk/yayin", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_AKTIF", True, raising=False)
    for ham in ("İZMİR 01", "C.1", "C 1", "a" * 70, "C/1", "C+1", "C#1"):
        konu = push.durum_konusu(ham)
        kimlik = konu.split("/")[-1]
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,40}", kimlik), f"{ham!r} → {kimlik!r} ACL'e uymuyor"
        assert konu == f"yourkiosk/durum/{kimlik}"


def test_durum_konusu_taban_egik_cizgiyle_kaymaz(monkeypatch) -> None:
    """26 Ekim i5 bulgusu: `yourkiosk/yayin/` → taban `yourkiosk/yayin` olup konu kayıyordu."""
    from core import push

    monkeypatch.setattr(config, "TETIK_PUSH_AKTIF", True, raising=False)
    for konu, beklenen in (("yourkiosk/yayin/", "yourkiosk/durum/C1"),
                           ("yourkiosk/yayin//", "yourkiosk/durum/C1")):
        monkeypatch.setattr(config, "TETIK_PUSH_KONU", konu, raising=False)
        assert push.durum_konusu("C1") == beklenen


def test_kalp_atisi_belgesi_alanlari(monkeypatch) -> None:
    from datetime import datetime, timezone

    from core import push

    monkeypatch.setattr(config, "CALISTIRMA_MODU", "tarayici", raising=False)
    belge = push.kalp_atisi_belgesi(True, datetime(2026, 10, 25, 9, 30, tzinfo=timezone.utc))
    assert belge["cevrimici"] is True
    assert belge["zaman"] == "2026-10-25T09:30:00Z"
    assert belge["mod"] == "tarayici"
    assert push.kalp_atisi_belgesi(False)["cevrimici"] is False


def test_tls_porttan_bagimsiz_acik(monkeypatch) -> None:
    """26 Ekim i5 bulgusu: TLS yalnız `port == 8883` iken kuruluyordu.

    `TETIK_PUSH_PORT` başka bir değere (1883/8884/443/ters vekil) ayarlanınca kullanıcı/parola
    ve kalp atışı ŞİFRESİZ gidiyordu. Kural: TLS varsayılan AÇIK, porttan bağımsız.
    """
    from core import push

    monkeypatch.setattr(config, "TETIK_PUSH_TLS", True, raising=False)
    for port in (8883, 1883, 8884, 443):
        monkeypatch.setattr(config, "TETIK_PUSH_PORT", port, raising=False)
        assert push.tls_gerekli() is True, f"port {port} için TLS kapalı kaldı"
    monkeypatch.setattr(config, "TETIK_PUSH_TLS", False, raising=False)
    assert push.tls_gerekli() is False, "açık kapatma (TETIK_PUSH_TLS=false) yok sayıldı"


def test_tls_kur_ca_ve_istemci_sertifikasi(monkeypatch) -> None:
    """`tls_kur` CA'yı ve varsa istemci sertifikasını (AWS IoT Core) bağlar."""
    from core import push

    class Sahte:
        def __init__(self) -> None:
            self.cagrilar: list[dict] = []

        def tls_set(self, **kw) -> None:  # noqa: ANN003
            self.cagrilar.append(kw)

    monkeypatch.setattr(config, "TETIK_PUSH_CA", "", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_SERTIFIKA", "", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_ANAHTAR", "", raising=False)
    sade = Sahte()
    push.tls_kur(sade)
    assert sade.cagrilar == [{"ca_certs": None}]

    monkeypatch.setattr(config, "TETIK_PUSH_CA", "/tmp/kok.pem", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_SERTIFIKA", "/tmp/cihaz.pem", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_ANAHTAR", "/tmp/cihaz.key", raising=False)
    x509 = Sahte()
    push.tls_kur(x509)
    assert x509.cagrilar == [{"ca_certs": "/tmp/kok.pem", "certfile": "/tmp/cihaz.pem",
                             "keyfile": "/tmp/cihaz.key"}]


def test_taban_konu_bos_yayin_konusunda_cokmez(monkeypatch) -> None:
    """Yayın konusu boş/tek parçasız kalırsa taban BOŞ olmamalı.

    Boş taban `"/durum/<id>"` konusu üretiyordu; panel `yourkiosk/durum/+` dinlediği için cihaz
    sonsuza kadar "bilinmiyor" kalırdı. Taban `yourkiosk`a düşer.
    """
    from core import push

    for konu, beklenen in (("", "yourkiosk"), ("/", "yourkiosk"), ("yourkiosk", "yourkiosk"),
                           ("yourkiosk/yayin", "yourkiosk"), ("a/b/c", "a/b")):
        monkeypatch.setattr(config, "TETIK_PUSH_KONU", konu, raising=False)
        assert push.taban_konu() == beklenen, f"{konu!r} → {push.taban_konu()!r}"
        assert push.durum_konusu("C1") == f"{beklenen}/durum/C1"


def test_taban_konu_panel_ile_ayni_kurali_uygular() -> None:
    """Panel (`cihazIzleme.ts`) ve cihaz aynı tabanı hesaplamalı — yoksa panel cihazı hiç görmez."""
    from pathlib import Path

    panel = (Path(__file__).resolve().parents[2] / "panel" / "src" / "domain"
             / "cihazIzleme.ts").read_text(encoding="utf-8")
    assert "lastIndexOf('/')" in panel or "rsplit" in panel or "split('/')" in panel, (
        "panel taban hesabı değişmiş — cihazla parite testi güncellenmeli"
    )
    assert "/durum/" in panel, "panel durum konusu kalıbı değişmiş"


def test_bozuk_push_portu_is_parcacigini_oldurmez(monkeypatch) -> None:
    """27 Ekim i5 bulgusu: geçersiz `push_port` iş parçacığını SESSİZCE öldürüyordu.

    Ölçüt: `_adres_ve_port()` istisna yükseltmez, 8883'e düşer ve nedeni `durum()`ta görünür
    (kullanıcı `--tani` çıktısında görebilir). Adres de bozuksa boş adres döner → çağıran push'u
    kapatır, cihaz yoklama ağıyla çalışmaya devam eder.
    """
    from core import push

    monkeypatch.setattr(config, "TETIK_PUSH_BROKER", "broker.test", raising=False)
    for bozuk in ("", "tls://8883", "8883.5", None):
        monkeypatch.setattr(config, "TETIK_PUSH_PORT", bozuk, raising=False)
        adres, port = push._adres_ve_port()
        assert (adres, port) == ("broker.test", 8883), f"port={bozuk!r}"


def test_push_adresi_yoksa_bos_adres_doner(monkeypatch) -> None:
    from core import push

    monkeypatch.setattr(config, "TETIK_PUSH_BROKER", "", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_PORT", 8883, raising=False)
    adres, _port = push._adres_ve_port()
    assert adres == ""


def test_gecerli_port_aynen_kullanilir(monkeypatch) -> None:
    from core import push

    monkeypatch.setattr(config, "TETIK_PUSH_BROKER", "broker.test", raising=False)
    monkeypatch.setattr(config, "TETIK_PUSH_PORT", "1884", raising=False)
    assert push._adres_ve_port() == ("broker.test", 1884)
