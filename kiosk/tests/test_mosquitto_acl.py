"""MQTT ACL ve doğrulama betikleri — metin kilidi (i5 bulguları).

NEDEN METİN TESTİ: bu bulgular kabuk betiklerinde (broker ACL'i, doğrulama testleri) ve
sahada koşulmadan görülemeyecek davranışlarda. Betik metnini kilitlemek, düzeltmenin sessizce
geri alınmasını engeller:

  1. Paylaşılan `cihaz` hesabı `yourkiosk/durum/+` konusuna YAZAMAMALI (cihaz taklidi).
     600 cihaz aynı parolayı taşıdığı için yazabilseydi tek bir ele geçirilmiş kiosk başka
     cihazın çevrimiçi durumunu taklit edebilirdi.
  2. ACL testi kendi kendini çürütmemeli: sabit/retained bir test konusu `-C 1` abonesine hemen
     ulaşırsa test her koşulda '✓' yazar. Test konuları benzersiz olmalı.
  3. Sabit /tmp yolu olmamalı: root olarak `>` ile sabit dosyaya yazmak, /tmp'de sembolik bağ
     kuran yerel kullanıcıya root'un rastgele bir dosyayı kesmesine izin verir.
  4. doğrulama bölüm numaralandırması kesintisiz olmalı (5) → 7) atlaması operatörü yanıltır).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
MOSQUITTO = KOK / "deploy" / "mosquitto"
KUR = MOSQUITTO / "kur.sh"
DOGRULA = MOSQUITTO / "dogrula.sh"


def _metin(yol: Path) -> str:
    assert yol.is_file(), f"beklenen dosya yok: {yol}"
    return yol.read_text(encoding="utf-8")


def _acl_bloku(metin: str, kullanici: str) -> str:
    """ACL heredoc'undan bir `user <ad>` bloğunu çıkarır (sonraki user/EOF'a kadar)."""
    desen = re.compile(
        r"^user " + re.escape(kullanici) + r"\s*$(.*?)(?=^user |^EOF)",
        re.MULTILINE | re.DOTALL,
    )
    eslesme = desen.search(metin)
    assert eslesme, f"ACL'de '{kullanici}' bloğu bulunamadı"
    return eslesme.group(1)


@pytest.mark.parametrize("betik", [KUR, DOGRULA])
def test_betikler_sozdizimi_bozuk_degil(betik: Path) -> None:
    """`bash -n` ile sözdizimi (mosquitto-clients kurulu olmasa da çalışır)."""
    import subprocess

    sonuc = subprocess.run(["bash", "-n", str(betik)], capture_output=True, text=True)
    assert sonuc.returncode == 0, sonuc.stderr


def test_paylasilan_cihaz_hesabi_durum_konusuna_yazamaz() -> None:
    """Bulgu 1: paylaşılan hesap `durum/+` yazamaz; yazma yetkisi cihaz-<id> kullanıcısında."""
    metin = _metin(KUR)
    blok = _acl_bloku(metin, "cihaz")
    assert "topic write yourkiosk/durum/+" not in blok, (
        "paylaşılan `cihaz` hesabına joker durum yazma yetkisi geri gelmiş (cihaz taklidi)"
    )
    assert "topic deny write yourkiosk/durum/#" in blok, "paylaşılan hesap için deny kuralı yok"
    assert "topic read yourkiosk/yayin" in blok


def test_panel_izleme_salt_okur() -> None:
    """panel-izleme yalnız durum konusunu okur ve yazamaz."""
    blok = _acl_bloku(_metin(KUR), "panel-izleme")
    assert "topic read yourkiosk/durum/+" in blok
    assert "topic write" not in blok.replace("topic deny write", "")


def test_acl_testi_kendini_curutmez() -> None:
    """Bulgu 2: test konuları benzersiz olmalı ve retained mesaj bırakılmamalı.

    `-C 1` abonesi, önceki adımdan kalan retained mesajı hemen alıp çıkarsa sızıntı testi
    hiçbir zaman gerçek yayını görmez → her koşulda '✓'.
    """
    metin = _metin(KUR)
    assert not re.search(r"-t\s+yourkiosk/durum/kurulum-testi", metin), (
        "sabit retained test konusu geri gelmiş (açıklama yorumu serbest, gerçek kullanım değil)"
    )
    for konu in re.findall(r'KONU_[A-Z]+="([^"]+)"', metin):
        # Benzersizlik: doğrudan PID ($$) ya da PID içeren bir değişken (TEST_CIHAZ="…$$").
        assert "$$" in konu or "$TEST_CIHAZ" in konu, f"test konusu benzersiz değil: {konu}"
    # Sızıntı/taklit testleri retained YAYINLAMAMALI (yalnız -r -n ile silme serbest).
    for satir in metin.splitlines():
        if "KONU_TAKLIT" in satir or "KONU_SIZINTI" in satir:
            assert " -r " not in satir or " -r -n " in satir, f"retained test yayını: {satir.strip()}"


@pytest.mark.parametrize("betik", [KUR, DOGRULA])
def test_sabit_tmp_yolu_yok(betik: Path) -> None:
    """Bulgu 3: sabit /tmp yolu yerine mktemp kullanılmalı."""
    metin = _metin(betik)
    sabitler = re.findall(r">\s*/tmp/[A-Za-z0-9_.-]+", metin)
    assert not sabitler, f"sabit /tmp yolu (sembolik bağ riski): {sabitler}"
    assert "mktemp" in metin, "geçici dosya mktemp ile üretilmiyor"


def test_dogrulama_numaralandirmasi_kesintisiz() -> None:
    """Bulgu 4: 1..8 arası bölüm numaraları eksiksiz ve sıralı olmalı."""
    numaralar = [int(n) for n in re.findall(r'^echo "=== (\d+)\)', _metin(DOGRULA), re.MULTILINE)]
    assert numaralar == list(range(1, len(numaralar) + 1)), f"numaralandırma bozuk: {numaralar}"


def test_cihaz_ekle_betigi_cihaz_basina_yetki_verir() -> None:
    """Kalp atışının üretimde çalışması cihaz başına kullanıcıya bağlı — belge ve betik uyumlu."""
    metin = _metin(MOSQUITTO / "cihaz-ekle.sh")
    assert 'local kullanici="cihaz-$kimlik"' in metin
    assert "topic write $KONU_TABANI/durum/$kimlik" in metin
