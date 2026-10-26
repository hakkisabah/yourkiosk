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
    # Yazma kuralı YOK = yazamıyor (acl_file varsayılanı reddet).
    assert not re.search(r"^topic\s+(write|readwrite)\b", blok, re.MULTILINE), (
        "paylaşılan `cihaz` hesabına yazma yetkisi verilmiş"
    )
    assert "topic read yourkiosk/yayin" in blok


def test_panel_izleme_salt_okur() -> None:
    """panel-izleme yalnız durum konusunu okur ve yazamaz."""
    blok = _acl_bloku(_metin(KUR), "panel-izleme")
    assert "topic read yourkiosk/durum/+" in blok
    assert not re.search(r"^topic\s+(write|readwrite)\b", blok, re.MULTILINE)
    assert "deny" not in blok, "`deny` okumayı da kapatır → panel-izleme izlemeyi kaybeder"


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

def test_acl_satirlari_gecerli_sozdizimi() -> None:
    """26 Ekim i5 bulgusu: `topic deny write <konu>` GEÇERSİZ sözdizimi.

    mosquitto erişim türünü TEK sözcük alır (`topic [read|write|readwrite|deny] <konu>`);
    `deny write x` yazınca konu "write x" olur ve hiçbir şey reddedilmez. `deny` ayrıca okumayı
    da kapatır (yön ayrımı yok) → panel-izleme için kullanılamaz. Doğru model: kural YAZMAMAK.
    """
    metin = _metin(KUR)
    izinli = {"read", "write", "readwrite", "deny"}
    for satir in metin.splitlines():
        s = satir.strip()
        if s.startswith("#") or not s.startswith("topic "):
            continue
        alanlar = s.split()
        assert len(alanlar) >= 3, f"eksik ACL satırı: {s}"
        assert alanlar[1] in izinli, f"geçersiz erişim türü: {s}"
        assert alanlar[1] != "deny", "`deny` okumayı da kapatır → yazma reddi için kural YAZILMAZ"
        assert alanlar[2].startswith("yourkiosk/"), f"beklenmeyen konu: {s}"


def test_kurulum_idempotent_cihaz_kimliklerini_silmez() -> None:
    """26 Ekim i5 bulgusu: tekrar koşan kur.sh parola dosyasını ve ACL'i SIFIRLIYORDU.

    `mosquitto_passwd -b -c` dosyayı sıfırdan yazar, `cat > acl` cihaz-<id> bloklarını ezer →
    600 cihazın kalp atışı sessizce düşer (betik başlığı "idempotent" diyordu).
    """
    metin = _metin(KUR)
    # `-c` (sıfırla) yalnız dosya YOKKEN çalışan dalda olmalı.
    assert "-b -c" in metin
    parola_blogu = metin.split("PWFILE=/etc/mosquitto/auth/passwd")[1].split("# mosquitto 2.x")[0]
    sifirla = [satir for satir in parola_blogu.splitlines() if "-b -c" in satir]
    assert sifirla, "ilk kurulum yolu (-b -c) kaybolmuş"
    assert any("[ -f \"$PWFILE\" ]" in satir for satir in metin.splitlines()), (
        "parola dosyası varlığı denetlenmiyor → tekrar koşuda cihaz kimlikleri silinir"
    )
    # ACL: yönetilen blok işaretli, cihaz blokları korunuyor, yazım atomik.
    assert "# >>> yourkiosk-managed" in metin and "# <<< yourkiosk-managed" in metin
    assert "cat > /etc/mosquitto/auth/acl" not in metin, "ACL hâlâ tümüyle eziliyor"
    assert 'install -m 640 -o mosquitto -g mosquitto "$ACL_GECICI" "$ACL_DOSYA"' in metin
    assert "ACL_KORUNAN" in metin and "cihaz-ekle.sh blokları" in metin


def test_dogrulama_degisken_adlari_kodla_uyusur() -> None:
    """26 Ekim i5 bulgusu: başlık `MQTT_PAROLA_CIHAZ` diyordu, 5. kontrol `MQTT_CIHAZ_PAROLA`."""
    metin = _metin(DOGRULA)
    baslik = metin.split("set -uo pipefail")[0]
    for ad in ("MQTT_PAROLA_PANEL", "MQTT_PAROLA_CIHAZ", "MQTT_PAROLA_IZLEME",
               "MQTT_CIHAZ_ID", "MQTT_CIHAZ_PAROLA"):
        assert ad in baslik, f"değişken belgede yok: {ad}"
    assert "MQTT_CIHAZ_KULLANICI" not in metin, "eski/yanlış değişken adı kalmış (5. kontrol atlanır)"
    # 5. kontrol kimlik verilmezse ATLAR (paylaşılan `cihaz` hesabı yazamaz → sahte ✓ üretmesin)
    assert '"${MQTT_CIHAZ_ID:-}" ]' in metin
