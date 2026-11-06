"""Deploy betiklerinin güvenlik sözleşmeleri — metin değil, YAPI denetlenir.

Kapsam (26 Ekim i5 bulguları):
  · `cihaz-ekle.sh` ACL'i ÖNGÖRÜLEBİLİR ada root olarak yazmamalı (broker süreci o dizine
    sembolik bağ koyabiliyor → keyfî dosya ezme). mktemp + atomik `mv` beklenir.
  · `cihaz-ekle.sh` depoda YÜRÜTÜLEBİLİR olmalı (100755). 100644 iken `./cihaz-ekle.sh C1`
    "Permission denied" veriyordu; belgeler ise tam bu biçimi söylüyordu.
  · `kur.sh` içinde `max_connections -1` (sınırsız) OLMAMALI: kimlik doğrulaması bağlantı
    kabulünden sonra yapıldığı için tek kaynak binlerce TLS el sıkışması açıp broker'ı düşürebilir.
  · (S3 yaşam döngüsü kuralı PR #84'te — bu dal yalnız MQTT/deploy betiklerini getirir.)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

DEPO = Path(__file__).resolve().parents[2]
MOSQUITTO = DEPO / "deploy" / "mosquitto"


def _oku(yol: Path) -> str:
    return yol.read_text(encoding="utf-8")


def _yorumlar_haric(satirlar: list[str]) -> list[str]:
    return [s for s in satirlar if s.strip() and not s.strip().startswith("#")]


def test_acl_yazimi_ongorulebilir_yol_kullanmaz():
    metin = _oku(MOSQUITTO / "cihaz-ekle.sh")
    kacak = [s.strip() for s in _yorumlar_haric(metin.splitlines())
             if ".yeni" in s or "$ACL.yeni" in s]
    assert not kacak, f"öngörülebilir geçici dosya adı (sembolik bağ riski): {kacak}"
    assert "mktemp" in metin, "ACL atomik yazım için mktemp kullanılmıyor"
    assert "mv -f" in metin, "ACL atomik taşınmıyor (yarım kalan dosya broker'ı kilitler)"


def test_cihaz_ekle_yurutulebilir():
    """Depoda 100755 olmalı: `git ls-files -s` modu doğrudan gösterir."""
    sonuc = subprocess.run(
        ["git", "-C", str(DEPO), "ls-files", "-s", "deploy/mosquitto/cihaz-ekle.sh"],
        capture_output=True, text=True, check=False,
    )
    if sonuc.returncode != 0 or not sonuc.stdout.strip():
        return  # git yok (arşiv) → mod denetlenemez; sessiz yanlış kırmızı üretme
    mod = sonuc.stdout.split()[0]
    assert mod == "100755", f"cihaz-ekle.sh modu {mod} — yürütülemez (./cihaz-ekle.sh C1 çalışmaz)"


def test_mosquitto_max_connections_sinirsiz_degil():
    metin = _oku(MOSQUITTO / "kur.sh")
    kullanilan = [s.strip() for s in _yorumlar_haric(metin.splitlines())
                  if s.strip().startswith("max_connections")]
    assert kullanilan, "kur.sh max_connections tanımlamıyor (varsayılan sınırsız olabilir)"
    for satir in kullanilan:
        deger = satir.split()[-1]
        assert deger != "-1", "max_connections -1 (sınırsız): bağlantı seliyle filo düşebilir"
        assert int(deger) >= 600, f"max_connections {deger} filo için çok düşük"
