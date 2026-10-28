"""28 Ekim i5 DEPLOY bulgularının kilitleri (kuru koşu sözü, IAM en-az-yetki).

Her test ÖLÇÜLEN kusuru yeniden üretir; kusur geri gelirse KIRMIZI olur.

BULGU 1 (DÜŞÜK): `deploy/guncelle.sh` içindeki `find … -delete` KURU denetiminin DIŞINDAYDI.
`--kuru` "hiçbir şeyi değiştirmez" dese de her koşuda 14 günden eski günlükleri siliyordu
(geri alınamaz veri kaybı + operatöre yanlış güvence).

BULGU 2 (DÜŞÜK): `kiosk/tools/gorsel_webp.py` karışık durumda (bazı adresler cihaz kapısından
geçmez) GEÇEN adresleri yazıp veri dosyasını değiştiriyor, sonra "DEĞİŞTİRİLMEDİ" diyordu.
Karışık durum testi `test_gorsel_optimize.py` içindedir (atomik karar).

BULGU 3 (DÜŞÜK): `deploy/cloudwatch/iam-politikasi.json` hiçbir betikte çağrılmayan izinler
taşıyordu (`sns:SetTopicAttributes`, `sns:GetTopicAttributes` + aynı sınıftan
`cloudwatch:ListTagsForResource`, `sns:ListTopics`).

BULGU 4 (DÜŞÜK): `deploy/yedek/iam-politikasi.json` içinde `s3:PutObject` TÜM `kiosk/*`
üzerindeydi; betik yalnız iki nesneyi geri yazdığı hâlde yedek anahtarı panel paketini,
yayın görsellerini ve ayar dosyalarını ezebiliyordu.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

DEPO = Path(__file__).resolve().parents[2]
DEPLOY = DEPO / "deploy"
GUNCELLE = DEPLOY / "guncelle.sh"
ALARMLAR = DEPLOY / "cloudwatch" / "alarmlar.sh"
ALARM_POLITIKA = DEPLOY / "cloudwatch" / "iam-politikasi.json"
ALARM_README = DEPLOY / "cloudwatch" / "README.md"
YEDEK_BETIK = DEPLOY / "yedek" / "geri_donme.sh"
YEDEK_POLITIKA = DEPLOY / "yedek" / "iam-politikasi.json"
YEDEK_README = DEPLOY / "yedek" / "README.md"


def _metin(yol: Path) -> str:
    return yol.read_text(encoding="utf-8")


def _politika(yol: Path) -> dict:
    return json.loads(_metin(yol))


def _eylemler(pol: dict) -> set[str]:
    return {eylem for ifade in pol["Statement"] for eylem in ifade["Action"]}


def _kaynaklar(pol: dict) -> list[str]:
    kaynak: list[str] = []
    for ifade in pol["Statement"]:
        deger = ifade["Resource"]
        kaynak.extend([deger] if isinstance(deger, str) else deger)
    return kaynak


# aws CLI alt komutu → gerektirdiği IAM eylemleri. Betiklerdeki çağrı biçimi (satır sonu
# devamı, `bolge_arg` sarmalayıcısı, değişkene atama) değişebildiği için metinde
# `<servis> <komut>` çifti aranır; `aws` önekinin nerede olduğu ÖNEMLİ DEĞİLDİR.
KOMUT_EYLEM: dict[tuple[str, str], set[str]] = {
    ("sns", "create-topic"): {"sns:CreateTopic"},
    ("sns", "subscribe"): {"sns:Subscribe"},
    ("sns", "delete-topic"): {"sns:DeleteTopic"},
    ("cloudwatch", "put-metric-alarm"): {"cloudwatch:PutMetricAlarm"},
    ("cloudwatch", "delete-alarms"): {"cloudwatch:DeleteAlarms"},
    ("cloudwatch", "describe-alarms"): {"cloudwatch:DescribeAlarms"},
    ("s3api", "list-object-versions"): {"s3:ListBucketVersions"},
    ("s3api", "get-bucket-versioning"): {"s3:GetBucketVersioning"},
    # head-object: geçerli nesne → GetObject, --version-id verilirse GetObjectVersion
    ("s3api", "head-object"): {"s3:GetObject", "s3:GetObjectVersion"},
    # copy-object: kaynağı okur (sürüm kimliğiyle), hedefe yazar
    ("s3api", "copy-object"): {"s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"},
}


def _betikteki_eylemler(metin: str) -> set[str]:
    gerekli: set[str] = set()
    for (servis, komut), eylemler in KOMUT_EYLEM.items():
        if re.search(rf"\b{re.escape(servis)}\s+{re.escape(komut)}\b", metin):
            gerekli |= eylemler
    return gerekli


#: Operatörün BU anahtarla yapması BELGELENMİŞ işler (betik çağırmaz). Her giriş gerekçeli
#: olmalı — "belki gerekir" gerekçe değildir.
BELGELI_OPERATOR_IZINLERI: dict[str, str] = {
    "cloudwatch:GetMetricStatistics": "README §2: fatura metriğini bu anahtarla okuma",
    "cloudwatch:ListMetrics": "README §2: fatura metriğini bu anahtarla okuma (metrik listesi)",
}


# ------------------------------------------------------- BULGU 1: kuru koşu sözü
def _guncelle_env(tmp_path: Path) -> dict[str, str]:
    depo = tmp_path / "depo"
    depo.mkdir()
    log_dizin = tmp_path / "log"
    log_dizin.mkdir()
    return {
        **os.environ,
        "KIOSK_KOK": str(depo),
        "KIOSK_LOG_DIZIN": str(log_dizin),
        "KIOSK_HOME": str(tmp_path / "kiosk-home"),
        "KIOSK_KULLANICI": os.environ.get("USER") or "kiosk",
    }


def _eski_gunluk(tmp_path: Path) -> Path:
    """14 günden eski bir günlük bırakır (silinmeye aday)."""
    yol = tmp_path / "log" / "canli-20200101-000000.log"
    yol.write_text("eski günlük", encoding="utf-8")
    yirmi_gun_once = time.time() - 20 * 86400
    os.utime(yol, (yirmi_gun_once, yirmi_gun_once))
    return yol


def test_kuru_kosu_eski_gunlukleri_silmez(tmp_path: Path) -> None:
    """Bulgu 1: `--kuru` hiçbir şeyi değiştirmemeli — 14 günden eski günlük yerinde kalmalı."""
    env = _guncelle_env(tmp_path)
    eski = _eski_gunluk(tmp_path)

    subprocess.run(
        ["bash", str(GUNCELLE), "--kuru"],
        env=env, capture_output=True, text=True, timeout=120, check=False,
    )

    assert eski.is_file(), "--kuru eski günlüğü sildi (kuru koşu hiçbir şeyi değiştirmez sözü bozuk)"


def test_gercek_kosu_eski_gunlukleri_temizler(tmp_path: Path) -> None:
    """Karşı yön: KURU değilken temizlik YAPILMALI (kapı, işlevi tamamen kapatmamalı)."""
    env = _guncelle_env(tmp_path)
    eski = _eski_gunluk(tmp_path)

    subprocess.run(
        ["bash", str(GUNCELLE)],
        env=env, capture_output=True, text=True, timeout=120, check=False,
    )

    assert not eski.exists(), "gerçek koşuda eski günlük temizlenmedi (kapı işlevi kapatmış)"


# ------------------------------------------- BULGU 3: kullanılmayan IAM izni yok
def test_alarm_politikasinda_kullanilmayan_izin_yok() -> None:
    """Bulgu 3: her izin ya betikte çağrılıyor ya da gerekçeli allow-list'te."""
    pol = _politika(ALARM_POLITIKA)
    gerekli = _betikteki_eylemler(_metin(ALARMLAR))

    artik = _eylemler(pol) - gerekli - set(BELGELI_OPERATOR_IZINLERI)
    assert not artik, f"hiçbir betikte çağrılmayan izin(ler): {sorted(artik)}"


def test_alarm_betiginin_ihtiyaci_politikada_karsilanmis() -> None:
    """Ters yön: betiğin çağırdığı her eylem politikada olmalı (sessiz AccessDenied olmasın)."""
    pol = _politika(ALARM_POLITIKA)
    eksik = _betikteki_eylemler(_metin(ALARMLAR)) - _eylemler(pol)

    assert not eksik, f"betik bu eylemleri çağırıyor ama politika izin vermiyor: {sorted(eksik)}"


def test_alarm_politikasinda_sns_publish_yok() -> None:
    """Alarmlar SNS'e AWS servisi olarak yazar; anahtarın yayın yapması gerekmez."""
    assert "sns:Publish" not in _eylemler(_politika(ALARM_POLITIKA))


# --------------------------------------- BULGU 4: yedek anahtarı dar olmalı
YEDEK_IZINLI_NESNELER = {
    "arn:aws:s3:::yourkiosk-veri/kiosk/lastSystemData.json",
    "arn:aws:s3:::yourkiosk-veri/kiosk/lastupdate.json",
}


def test_yedek_politikasi_yalniz_iki_nesneye_yazar() -> None:
    """Bulgu 4: `s3:PutObject` kiosk/* üzerinde olamaz — yalnız geri dönme iki nesnesi."""
    pol = _politika(YEDEK_POLITIKA)
    yazma = {
        ifade["Sid"]: ifade for ifade in pol["Statement"] if "s3:PutObject" in ifade["Action"]
    }
    assert yazma, "s3:PutObject izni hiç yok — geri dönme yazamaz"
    for sid, ifade in yazma.items():
        kaynak = ifade["Resource"]
        kaynak = [kaynak] if isinstance(kaynak, str) else kaynak
        assert set(kaynak) == YEDEK_IZINLI_NESNELER, f"{sid}: beklenen iki nesne, gelen {kaynak}"


def test_yedek_politikasinda_wildcard_nesne_yok() -> None:
    for kaynak in _kaynaklar(_politika(YEDEK_POLITIKA)):
        assert not kaynak.endswith("/*"), f"nesne düzeyinde wildcard geri gelmiş: {kaynak}"


def test_yedek_politikasinda_kullanilmayan_izin_yok() -> None:
    pol = _politika(YEDEK_POLITIKA)
    artik = _eylemler(pol) - _betikteki_eylemler(_metin(YEDEK_BETIK))
    assert not artik, f"geri_donme.sh çağırmıyor ama izin verilmiş: {sorted(artik)}"


def test_yedek_betiginin_ihtiyaci_politikada_karsilanmis() -> None:
    pol = _politika(YEDEK_POLITIKA)
    eksik = _betikteki_eylemler(_metin(YEDEK_BETIK)) - _eylemler(pol)
    assert not eksik, f"betik bu eylemleri çağırıyor ama politika izin vermiyor: {sorted(eksik)}"


def test_yedek_politikasi_silme_yetkisi_icermez() -> None:
    """Geri dönme silmez, yeni sürüm yazar (yanlış sürüm seçimi geri alınabilir kalsın)."""
    assert "s3:DeleteObject" not in _eylemler(_politika(YEDEK_POLITIKA))
    assert "s3:DeleteObjectVersion" not in _eylemler(_politika(YEDEK_POLITIKA))


# ------------------------------------- BELGE ↔ POLİTİKA: özet satırı gerçeği söylemeli
def _ozet_bloku(metin: str) -> str:
    """'İçerik özeti' ile başlayan paragraf (ilk boş satıra kadar)."""
    for parca in metin.split("\n\n"):
        if parca.lstrip().startswith("İçerik özeti"):
            return parca
    raise AssertionError("README'de 'İçerik özeti' paragrafı yok")


def _ozetteki_eylemler(metin: str, onek: str) -> set[str]:
    """Özet paragrafındaki `<önek>:Eylem|Eylem2` biçimindeki listeleri çözer."""
    bulunan: set[str] = set()
    blok = _ozet_bloku(metin)
    for grup in re.findall(rf"{onek}:[A-Za-z]+(?:\|[A-Za-z]+)*", blok):
        for ad in grup.split(":", 1)[1].split("|"):
            bulunan.add(f"{onek}:{ad}")
    return bulunan


#: Özette adı geçen ama politikada BİLEREK olmayan eylemler + belgedeki gerekçe cümlesi.
#: Test, gerekçenin belgede durduğunu da doğrular: cümle silinirse kırmızıya döner.
BELGEDE_ANILAN_ISTISNALAR: dict[str, str] = {
    "sns:Publish": "bilerek yok",
}


def test_alarm_readme_ozeti_politikayla_ayni() -> None:
    metin = _metin(ALARM_README)
    pol = _eylemler(_politika(ALARM_POLITIKA))
    for onek in ("sns", "cloudwatch"):
        belge = _ozetteki_eylemler(metin, onek)
        gercek = {e for e in pol if e.startswith(f"{onek}:")}
        fazla = belge - gercek
        for eylem in sorted(fazla):
            gerekce = BELGEDE_ANILAN_ISTISNALAR.get(eylem)
            assert gerekce and gerekce in metin, (
                f"belge özetinde politikada olmayan izin var: {eylem} (gerekçe yok)"
            )
        assert gercek <= belge, (
            f"{onek} özeti eksik — politikadaki izinler belgede yazmıyor: {sorted(gercek - belge)}"
        )


def test_yedek_readme_ozeti_politikayla_ayni() -> None:
    pol = _eylemler(_politika(YEDEK_POLITIKA))
    belge = _ozetteki_eylemler(_metin(YEDEK_README), "s3")
    assert belge == pol, f"belge özeti politikayla uyuşmuyor: belge {sorted(belge)} · politika {sorted(pol)}"

