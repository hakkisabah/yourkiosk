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



# --- 28 Ekim i5 bulguları (2. tur): deploy/README tablosu politikalarla ayrışmıştı ---
#
# BULGU 5 (DÜŞÜK): `deploy/README.md` §2 tablosundaki izin satırları politikaların
# GERÇEĞİNİ yazmıyordu: yayın satırı `s3:ListBucket`'ı NESNE ARN'i (`kiosk/*`) ile
# veriyordu (kova düzeyi eylem nesne ARN'inde hiçbir şey yapmaz; ayrıca kapsam yanlış:
# yayın `panel/*`, `kiosk/*` değil), yedek satırı politikada OLMAYAN
# `GetObjectTagging|PutObjectTagging` izinlerini sayıp `GetObjectVersion|
# GetBucketVersioning`'i atlıyordu, alarm satırı `sns:ListTopics` diyor (politikada yok)
# ve `sns:DeleteTopic`'ı (alarmlar.sh --sil için ZORUNLU) yazmıyordu.
#
# BULGU 6 (DÜŞÜK): `deploy/yedek/README.md` ve `deploy/cloudwatch/README.md` var OLMAYAN
# bir dosyayı kanıt gösteriyordu (`kiosk/tests/test_deploy_iam_dar.py`). Operatör kanıtı
# açar, bulamaz; "makineyle kilitli" güvencesi boşa çıkar.

DEPO_README = DEPLOY / "README.md"
YAYIN_POLITIKA = DEPO / "panel" / "infra" / "yayin-politikasi.json"

#: Tablo satırında geçen ama AWS eylemi OLMAYAN geri-tırnaklı sözcükler.
EYLEM_DEGIL = {"EVR6YMP2UVX8A"}


def _tablo_satiri(metin: str, is_adi: str) -> str:
    """Verilen iş adını taşıyan markdown tablo satırını döndürür."""
    for satir in metin.splitlines():
        if satir.startswith("|") and is_adi in satir.split("|")[1]:
            return satir
    raise AssertionError(f"deploy/README.md tablosunda '{is_adi}' satırı yok")


def _satirdaki_eylemler(satir: str) -> set[str]:
    """Tablo satırındaki `<önek>:Eylem` ve ardından gelen kısa `Eylem` biçimlerini çözer.

    `cloudwatch:PutMetricAlarm`, `DescribeAlarms`, `DeleteAlarms` → üçü de cloudwatch:.
    """
    bulunan: set[str] = set()
    onek = ""
    for parca in re.findall(r"`([^`]+)`", satir):
        parca = parca.strip()
        eslesme = re.fullmatch(r"(s3|sns|cloudwatch|cloudfront):([A-Za-z]+)", parca)
        if eslesme:
            onek = eslesme.group(1)
            bulunan.add(f"{onek}:{eslesme.group(2)}")
        elif re.fullmatch(r"[A-Z][A-Za-z]+", parca) and onek and parca not in EYLEM_DEGIL:
            bulunan.add(f"{onek}:{parca}")
    return bulunan


def _satir_eylemleri_esit(metin: str, is_adi: str, politika: Path) -> None:
    satir = _tablo_satiri(metin, is_adi)
    belge = _satirdaki_eylemler(satir)
    gercek = _eylemler(_politika(politika))
    assert belge == gercek, (
        f"'{is_adi}' satırı {politika.name} ile ayrışmış\n"
        f"  belgede fazla : {sorted(belge - gercek)}\n"
        f"  belgede eksik : {sorted(gercek - belge)}"
    )


def test_deploy_readme_yayin_satiri_politikayla_ayni() -> None:
    _satir_eylemleri_esit(_metin(DEPO_README), "Günlük yayın", YAYIN_POLITIKA)


def test_deploy_readme_yedek_satiri_politikayla_ayni() -> None:
    _satir_eylemleri_esit(_metin(DEPO_README), "Yedek tatbikatı", YEDEK_POLITIKA)


def test_deploy_readme_alarm_satiri_politikayla_ayni() -> None:
    _satir_eylemleri_esit(_metin(DEPO_README), "Maliyet alarmları", ALARM_POLITIKA)


def test_deploy_readme_listbucket_kova_duzeyinde_anlatilir() -> None:
    """`s3:ListBucket` kova düzeyidir: nesne ARN'i ile verildiği iddiası yasak."""
    satir = _tablo_satiri(_metin(DEPO_README), "Günlük yayın")
    assert "s3:prefix" in satir, "yayın satırı s3:ListBucket'ın s3:prefix koşulunu yazmıyor"
    assert "arn:aws:s3:::yourkiosk-veri` **+**" in satir, "kova ARN'i ayrı yazılmamış"
    assert "/kiosk/*" not in satir, "yayın satırı hâlâ kiosk/* kapsamı yazıyor (yayın panel/*)"


def test_deploy_readme_alarm_satirinda_silme_yetkisi_var() -> None:
    satir = _tablo_satiri(_metin(DEPO_README), "Maliyet alarmları")
    politika = _eylemler(_politika(ALARM_POLITIKA))
    if "sns:DeleteTopic" in politika:
        assert "DeleteTopic" in satir, "politikada olan sns:DeleteTopic tabloda yazmıyor"
    assert "ListTopics" not in satir, "politikada olmayan sns:ListTopics tabloda yazıyor"


def test_deploy_belgeleri_var_olmayan_test_dosyasina_atif_yapmaz() -> None:
    """Belgede kanıt gösterilen her `kiosk/tests/<ad>.py` gerçekten var olmalı."""
    eksik: list[str] = []
    for belge in sorted(DEPLOY.rglob("*.md")):
        for ad in re.findall(r"kiosk/tests/([A-Za-z0-9_]+\.py)", belge.read_text(encoding="utf-8")):
            if not (DEPO / "kiosk" / "tests" / ad).exists():
                eksik.append(f"{belge.relative_to(DEPO)} → kiosk/tests/{ad}")
    assert not eksik, "var olmayan test dosyasına atıf: " + "; ".join(eksik)


# ---------------------------------------- BULGU 5: copy-object etiket yönergesi
def _politika_eylemleri(yol: Path) -> set[str]:
    veri = json.loads(yol.read_text())
    eylemler: set[str] = set()
    for ifade in veri["Statement"]:
        ham = ifade["Action"]
        eylemler |= set(ham if isinstance(ham, list) else [ham])
    return eylemler


def test_geri_donme_copy_object_etiket_yonergesi_tasir() -> None:
    """copy-object `--tagging-directive REPLACE` taşımalı.

    NEDEN: AWS varsayılanı COPY'dir ve kaynağın etiketlerini kopyalar. Yedek
    anahtarının politikası s3:PutObjectTagging İÇERMEZ (en-az-yetki), bu yüzden
    COPY etiket kopyalamaya çalışınca geri dönüş AccessDenied ile düşer —
    yani felaket anında çalışmayan bir betik.
    """
    metin = YEDEK_BETIK.read_text()
    politika = _politika_eylemleri(YEDEK_POLITIKA)

    # Gerçek çağrı ve KURU çıktısı aynı bayrağı göstermeli (tek kaynak: dizi).
    assert "KOPYA_BAYRAK=(--metadata-directive REPLACE --tagging-directive REPLACE)" in metin, (
        "copy-object bayrakları tek dizide toplanmamış; kuru çıktı ile gerçek çağrı ayrışabilir."
    )
    assert '"${KOPYA_BAYRAK[@]}"' in metin, "gerçek copy-object çağrısı KOPYA_BAYRAK kullanmıyor."
    kuru = re.search(r'echo "       --copy-source.*KOPYA_BAYRAK.*', metin)
    assert kuru, "KURU çıktısı --tagging-directive REPLACE bayrağını göstermiyor."

    if "s3:PutObjectTagging" not in politika:
        assert "--tagging-directive REPLACE" in metin, (
            "Politika etiket yazma izni vermiyor ama copy-object REPLACE istemiyor: "
            "geri dönüş AccessDenied ile düşer."
        )


def test_geri_donme_etiket_izinini_politikaya_geri_koymaz() -> None:
    """REPLACE bayrağı varken politikaya etiket izni eklemek gereksiz yetkidir."""
    politika = _politika_eylemleri(YEDEK_POLITIKA)
    metin = YEDEK_BETIK.read_text()
    if "--tagging-directive REPLACE" in metin:
        assert not (politika & {"s3:PutObjectTagging", "s3:GetObjectTagging"}), (
            "copy-object REPLACE ile etiket kopyalamıyor; politikadaki etiket izinleri "
            f"gereksiz yetki: {sorted(politika & {'s3:PutObjectTagging', 's3:GetObjectTagging'})}"
        )
