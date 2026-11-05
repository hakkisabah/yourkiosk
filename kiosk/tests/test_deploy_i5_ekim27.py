"""27 Ekim i5 DEPLOY bulgularının kilitleri (belge değişkenleri, CloudWatch bölgesi,
S3 yaşam döngüsü tek kaynağı, yedek sayfalaması, SNS şifreleme).

Her test ÖLÇÜLEN kusuru yeniden üretir; kusur geri gelirse KIRMIZI olur.

BULGU 2 (ORTA): `deploy/README.md` doğrulama bloğu `MQTT_CIHAZ_KULLANICI=cihaz-C1` veriyordu ama
`deploy/mosquitto/dogrula.sh` `MQTT_CIHAZ_ID` okuyor → 5 ve 7. kontroller SESSİZCE atlanıyordu.
BULGU 3 (ORTA): CloudFront 5xx alarmı `--region` verilmeden kuruluyordu; CloudFront metrikleri
yalnız `us-east-1`'de yayınlandığı için alarm ölü kalıyordu.
BULGU 4 (ORTA): depoda S3 yaşam döngüsü için ÇELİŞİK iki tanım vardı (önek kuralı kullanımdaki
görselleri siliyordu).
BULGU 7 (BİLGİ): `list-object-versions --max-items 10` + istemci tarafı süzgeç → sayfalama sınırı
süzgeçte kaybolabiliyordu.
BULGU 8 (BİLGİ): SNS konusu KMS'siz kuruluyordu; KMS desteği + kabul edilen risk belgesi.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

DEPO = Path(__file__).resolve().parents[2]
DEPLOY = DEPO / "deploy"
RED = DEPLOY / "README.md"
DOGRULA = DEPLOY / "mosquitto" / "dogrula.sh"
ALARMLAR = DEPLOY / "cloudwatch" / "alarmlar.sh"
ALARM_README = DEPLOY / "cloudwatch" / "README.md"
GERI_DONME = DEPLOY / "yedek" / "geri_donme.sh"
YASAM = DEPLOY / "s3" / "yasam-dongusu.json"

ATLANAN = ("node_modules", ".venv", ".git", "dist", ".pytest_cache", "__pycache__")


def _metin(yol: Path) -> str:
    return yol.read_text(encoding="utf-8")


# ---------------------------------------------------------------- BULGU 2
def _dogrula_degiskenleri() -> set[str]:
    return set(re.findall(r"\$\{?(MQTT_[A-Z0-9_]+)", _metin(DOGRULA)))


def _belgedeki_kod_blogu_degiskenleri() -> set[str]:
    """README'de `dogrula.sh` çağıran bash bloklarındaki MQTT_* adları (YORUMLAR hariç)."""
    bulunan: set[str] = set()
    bloklar = re.findall(r"```bash\n(.*?)```", _metin(RED), flags=re.S)
    for blok in bloklar:
        if "dogrula.sh" not in blok:
            continue
        for satir in blok.splitlines():
            if satir.lstrip().startswith("#"):
                continue
            bulunan |= set(re.findall(r"\b(MQTT_[A-Z0-9_]+)\b", satir))
    return bulunan


def test_belgedeki_mqtt_degiskenleri_betigin_okuduklarinin_alt_kumesi():
    betik = _dogrula_degiskenleri()
    belge = _belgedeki_kod_blogu_degiskenleri()
    assert belge, "README'de dogrula.sh bloğu bulunamadı — belge mi taşındı?"
    fazla = belge - betik
    assert not fazla, (
        "belge, betiğin OKUMADIĞI değişken veriyor (kontroller sessizce atlanır): "
        + ", ".join(sorted(fazla))
    )


def _belge_blogu() -> str:
    """README'deki `dogrula.sh` bloğu (yorumsuz satırlar)."""
    bloklar = re.findall(r"```bash\n(.*?)```", _metin(RED), flags=re.S)
    secili = [b for b in bloklar if "dogrula.sh" in b]
    assert secili, "README'de dogrula.sh bloğu yok"
    return "\n".join(
        satir for blok in secili for satir in blok.splitlines()
        if not satir.lstrip().startswith("#")
    )


def test_belge_cihaz_kimligini_dogru_adla_veriyor():
    blok = _belge_blogu()
    assert "MQTT_CIHAZ_KULLANICI" not in blok, (
        "README hâlâ MQTT_CIHAZ_KULLANICI kullanıyor (dogrula.sh MQTT_CIHAZ_ID okur)"
    )
    assert re.search(r"MQTT_CIHAZ_ID=C1\b", blok), (
        "README cihaz kimliğini MQTT_CIHAZ_ID=C1 olarak vermeli (önek 'cihaz-' betik ekler)"
    )
    # 5 ve 7. kontroller bu iki değişken olmadan atlanır → belge ikisini de vermeli.
    assert "MQTT_PAROLA_IZLEME" in blok and "MQTT_CIHAZ_PAROLA" in blok


def test_belge_kimlik_onegini_karistirmiyor():
    """`MQTT_CIHAZ_ID=cihaz-C1` verilirse betik `cihaz-cihaz-C1` kullanıcısı arar (sessiz atlama)."""
    metin = _metin(DOGRULA)
    assert 'KULLANICI="cihaz-$MQTT_CIHAZ_ID"' in metin, (
        "dogrula.sh kullanıcı adını artık `cihaz-<id>` diye kurmuyor — belge/test güncellenmeli"
    )


# ---------------------------------------------------------------- BULGU 3
def _sahte_aws(tmp_path: Path) -> tuple[Path, Path]:
    """`aws` yerine çağrı argümanlarını kaydeden vekil."""
    bin = tmp_path / "bin"
    bin.mkdir(exist_ok=True)
    kayit = tmp_path / "aws-cagrilari.log"
    aws = bin / "aws"
    aws.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {kayit}\n"
        "case \"$*\" in\n"
        "  *'sns create-topic'*) echo 'arn:aws:sns:eu-central-1:111111111111:yourkiosk-alarm' ;;\n"
        "  *head-object*'--query ContentLength'*) echo 42 ;;\n"
        "  *head-object*'--query ServerSideEncryption'*) echo AES256 ;;\n"
        "  *head-object*) echo '{\"ServerSideEncryption\":\"AES256\",\"ContentLength\":42}' ;;\n"
        "  *'!IsLatest'*) echo v-eski ;;\n"
        "  *\"VersionId=='v-eski'\"*) echo 42 ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    aws.chmod(0o755)
    return bin, kayit


def _alarmlar(tmp_path: Path, arguman: str, ek_env: dict | None = None) -> list[str]:
    bin, kayit = _sahte_aws(tmp_path)
    kayit.unlink(missing_ok=True)
    env = {
        **os.environ,
        "PATH": f"{bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "XDG_STATE_HOME": str(tmp_path / "durum"),
        "ARN_DOSYASI": str(tmp_path / "sns-arn"),
        "HOME": str(tmp_path),
        "BILDIRIM_EPOSTA": "test@ornek.com",
        "S3_ALARM": "1",
        "CLOUDFRONT_ID": "E1234567890ABC",
        "AUTH_MODU": "cognito",
        **(ek_env or {}),
    }
    sonuc = subprocess.run(["bash", str(ALARMLAR), arguman], env=env,
                           capture_output=True, text=True, timeout=120)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    return [s for s in kayit.read_text(encoding="utf-8").splitlines() if s.strip()]


def test_cloudfront_alarmi_us_east_1_de_kurulur(tmp_path: Path):
    cagrilar = _alarmlar(tmp_path, "")
    cf = [c for c in cagrilar if "cloudfront-5xx-orani" in c]
    assert cf, "CloudFront alarmı kurulmadı"
    assert all("--region us-east-1" in c for c in cf), (
        "CloudFront alarmı bölge verilmeden kuruluyor — metrikler yalnız us-east-1'de yayınlanır: "
        + " | ".join(cf)
    )

    fatura = [c for c in cagrilar if "fatura-aylik-esik" in c and "put-metric-alarm" in c]
    assert fatura and all("--region us-east-1" in c for c in fatura), "fatura alarmı us-east-1'de kurulmalı"

    yerel = [c for c in cagrilar if "s3-5xx-orani" in c and "put-metric-alarm" in c]
    assert yerel and all("--region" not in c for c in yerel), (
        "S3 alarmı varsayılan bölgede kurulmalı (kova bölgesi): " + " | ".join(yerel)
    )


def test_liste_ve_sil_bolge_farkinda(tmp_path: Path):
    cagrilar = _alarmlar(tmp_path, "--liste")
    global_sorgu = [c for c in cagrilar if "describe-alarms" in c and "fatura-aylik-esik" in c]
    assert global_sorgu and "--region us-east-1" in global_sorgu[0], (
        "fatura/CloudFront alarmları us-east-1'de sorgulanmıyor: " + " | ".join(global_sorgu)
    )
    yerel_sorgu = [c for c in cagrilar if "describe-alarms" in c and "s3-5xx-orani" in c]
    assert yerel_sorgu and "--region" not in yerel_sorgu[0], (
        "varsayılan bölgedeki alarmlar bölge argümanı olmadan sorgulanmalı: " + " | ".join(yerel_sorgu)
    )

    sil_cagrilari = _alarmlar(tmp_path, "--sil")
    sil = {c.split("--alarm-names")[-1].strip(): c for c in sil_cagrilari if "delete-alarms" in c}
    assert "cloudfront-5xx-orani" in sil and "--region" in sil.get("cloudfront-5xx-orani", ""), (
        "silme bölge farkında değil: " + " | ".join(sil_cagrilari)
    )
    assert "s3-5xx-orani" in sil and "--region" not in sil["s3-5xx-orani"], (
        "S3 alarmı varsayılan bölgeden silinmeli: " + " | ".join(sil_cagrilari)
    )


# ---------------------------------------------------------------- BULGU 4
def _yasam_dongusu_dosyalari() -> list[Path]:
    bulunan: list[Path] = []
    for yol in DEPO.rglob("*.json"):
        if any(p in ATLANAN for p in yol.parts):
            continue
        try:
            belge = json.loads(yol.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        kurallar = belge.get("Rules") if isinstance(belge, dict) else None
        if not isinstance(kurallar, list) or not kurallar:
            continue
        if any(any(a in k for a in ("Expiration", "NoncurrentVersionExpiration",
                                    "AbortIncompleteMultipartUpload"))
               for k in kurallar if isinstance(k, dict)):
            bulunan.append(yol.relative_to(DEPO))
    return sorted(bulunan)


def test_s3_yasam_dongusu_tek_kaynak():
    bulunan = _yasam_dongusu_dosyalari()
    assert bulunan == [Path("deploy/s3/yasam-dongusu.json")], (
        "S3 yaşam döngüsü için birden çok/yanlış tanım var (çelişki): "
        + ", ".join(str(b) for b in bulunan)
    )


def test_belgeler_var_olmayan_yasam_dongusu_dosyasina_yonlendirmiyor():
    eski = "panel/infra/s3-lifecycle.json"
    suclu = [str(y.relative_to(DEPO)) for y in DEPO.rglob("*.md")
             if not any(p in ATLANAN for p in y.parts) and eski in _metin(y)]
    assert not suclu, "belgeler kaldırılan dosyaya yönlendiriyor: " + ", ".join(suclu)


def test_gorsel_silme_kurali_etiket_kapili():
    """Önek + Expiration.Days kuralı panelde KULLANILAN görseli siler (anahtar = içerik sha'sı)."""
    belge = json.loads(_metin(YASAM))
    gorsel = [k for k in belge["Rules"] if "yayin-gorselleri" in k.get("Filter", {}).get("And", {}).get("Prefix", "")]
    assert gorsel, "görsel kuralı bulunamadı"
    for kural in gorsel:
        filtre = kural.get("Filter", {}).get("And", {})
        etiketler = filtre.get("Tags") or []
        assert any(e.get("Key") == "silinebilir" and e.get("Value") == "true" for e in etiketler), (
            f"{kural.get('ID')}: görsel silme ETİKET kapılı değil — kullanımdaki görsel silinebilir"
        )


# ---------------------------------------------------------------- BULGU 7
def _geri_donme_cagrilari(tmp_path: Path, *argumanlar: str) -> list[str]:
    bin, kayit = _sahte_aws(tmp_path)
    env = {**os.environ, "PATH": f"{bin}{os.pathsep}{os.environ.get('PATH', '')}"}
    sonuc = subprocess.run(
        ["bash", str(GERI_DONME), "--kova", "kova", "--anahtar", "kiosk/veri.json", *argumanlar],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    return [s for s in kayit.read_text(encoding="utf-8").splitlines() if s.strip()]


def test_yedek_sayfalamasi_suzgeci_kaybetmiyor(tmp_path: Path):
    cagrilar = _geri_donme_cagrilari(tmp_path, "--liste")

    listeler = [c for c in cagrilar if "list-object-versions" in c]
    assert listeler, "list-object-versions çağrısı yok"
    for cagri in listeler:
        assert "--max-items" not in cagri, (
            "istemci tarafı sayfa sınırı süzgeci kaybediyor (önek eşleşen komşu anahtarlar ilk "
            "sayfayı doldurunca sonuç BOŞ döner): " + cagri
        )
        assert "Key=='kiosk/veri.json'" in cagri, "süzgeç sunucu tarafında (--query) değil: " + cagri


def test_yedek_geri_donme_surum_secimi_de_sinirsiz(tmp_path: Path):
    cagrilar = _geri_donme_cagrilari(tmp_path)  # --surum yok → önceki sürümü kendi seçer
    listeler = [c for c in cagrilar if "list-object-versions" in c]
    assert listeler
    assert all("--max-items" not in c for c in listeler), "sürüm seçimi sayfa sınırına takılıyor"


# ---------------------------------------------------------------- BULGU 8
def test_sns_kms_destegi_ve_kabul_edilen_risk_belgesi():
    betik = _metin(ALARMLAR)
    assert "SNS_KMS_ANAHTAR" in betik and "KmsMasterKeyId" in betik, (
        "alarmlar.sh müşteri anahtarıyla (KMS) SNS konusu kurma yolunu sunmuyor"
    )
    belge = _metin(ALARM_README)
    assert "kabul edilen" in belge.lower() and "KMS" in belge, (
        "SNS şifrelemesi ya KMS anahtarıyla kurulmalı ya da kabul edilen risk olarak yazılmalı"
    )


def test_sns_kms_verilince_konu_anahtarla_kurulur(tmp_path: Path):
    cagrilar = _alarmlar(tmp_path, "", {"SNS_KMS_ANAHTAR": "alias/yourkiosk-alarm"})
    konu = [c for c in cagrilar if "sns create-topic" in c]
    assert konu and "KmsMasterKeyId=alias/yourkiosk-alarm" in konu[0], (
        "SNS_KMS_ANAHTAR verildiği hâlde create-topic anahtarla kurulmadı: " + " | ".join(konu)
    )
