"""yaz.py — PR yorum gövdesi testleri (ağ yok).

Neden: karar kapısı `kabul` (kapanış ölçütü) alanını ZORUNLU kılıyor; ama ölçüt PR yorumuna
basılmıyorsa geliştiriciye hiç ulaşmaz (26 Ekim i5 bulgusu). Aynı sınıf hata: kapı atlandığında
bunun yorumda görünmemesi.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaz  # noqa: E402


def karar(**degisiklik) -> dict:
    k = {
        "makine": "i5", "pr": 90, "sha": "a" * 40, "karar": "sorun", "onem": "orta",
        "ozet": "İki bulgu var.", "denetlenen": ["gömülü sır"],
        "bulgular": [{"dosya": "otomasyon/betik/nobetci.py", "satir": 241, "onem": "orta",
                      "aciklama": "gunluk adı çakışıyor",
                      "kabul": "gunluk_yolu ayrı alan olmalı ve test bunu kilitlemeli"}],
    }
    k.update(degisiklik)
    return k


class YorumGovdesiTesti(unittest.TestCase):
    def test_kapanis_olcutu_yorumda_gorunur(self):
        govde = yaz.yorum_govdesi(karar(), "failure")
        self.assertIn("Kapanış ölçütü", govde)
        self.assertIn("gunluk_yolu ayrı alan olmalı", govde)

    def test_kabul_yoksa_tire_basilir(self):
        b = karar()["bulgular"][0]
        b.pop("kabul")
        govde = yaz.yorum_govdesi(karar(bulgular=[b]), "failure")
        self.assertIn("| — |", govde)

    def test_i3_eksiklerinde_de_kapanis_olcutu(self):
        govde = yaz.yorum_govdesi(karar(makine="i3", eksikler=[
            {"dosya": "web/src/kiosk.ts", "satir": 12, "onem": "orta",
             "aciklama": "önbellek atlanmıyor", "kabul": "bildirim gelince zorla yenileme testi"}]), "failure")
        self.assertIn("Kapanış ölçütü", govde)
        self.assertIn("bildirim gelince zorla yenileme testi", govde)

    def test_kapi_atlandi_yorumda_uyari(self):
        govde = yaz.yorum_govdesi(karar(kapi_atlandi="kanıt katmanı çevrimdışı, elle doğrulandı"), "failure")
        self.assertIn("KARAR KAPISI ATLANDI", govde)
        self.assertIn("çevrimdışı", govde)

    def test_baslik_ve_durum_simgesi(self):
        self.assertIn("i5 — güvenlik incelemesi", yaz.yorum_govdesi(karar(), "success"))
        self.assertIn("i3 — karar", yaz.yorum_govdesi(karar(makine="i3"), "failure"))


class DurumMetniTesti(unittest.TestCase):
    def test_aciklama_140_karakteri_asmaz(self):
        durum, aciklama = yaz.durum_metni(karar(ozet="çok uzun " * 60))
        self.assertEqual(durum, "failure")
        self.assertLessEqual(len(aciklama), 140)

    def test_onay_durumu_success(self):
        self.assertEqual(yaz.durum_metni(karar(karar="onay", onem="dusuk", bulgular=[]))[0], "success")


class KapiAtlamaTesti(unittest.TestCase):
    """--kapi-atla artık ajanın tek başına kullanabileceği bir anahtar DEĞİL (26 Ekim i5 bulgusu).

    Ret yolları gerçekten koşturulur (alt süreç + --kuru; ağa çıkılmaz, günlük geçici dosyaya).
    """

    def setUp(self):
        import json as _json
        import tempfile
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.karar_yolu = self.kok / "karar.json"
        self.karar_yolu.write_text(_json.dumps(karar(), ensure_ascii=False), encoding="utf-8")
        self.log = self.kok / "kapi-red.log"
        self.yaz = Path(__file__).resolve().parents[1] / "yaz.py"
        self.token = self.kok / "yok.token"   # kanıt katmanı fail-closed → kapı geçmez

    def tearDown(self):
        self.dizin.cleanup()

    def calistir(self, *ek: str, env_anahtar: bool = False):
        import os
        import subprocess
        ortam = {**os.environ, "YAZ_KAPI_LOG": str(self.log), "HOME": str(self.kok)}
        ortam.pop("YAZ_KAPI_ATLA_ONAY", None)
        if env_anahtar:
            ortam["YAZ_KAPI_ATLA_ONAY"] = "1"
        return subprocess.run(
            [sys.executable, str(self.yaz), str(self.karar_yolu), "--kuru",
             "--token-dosya", str(self.token), *ek],
            capture_output=True, text=True, timeout=120, env=ortam,
        )

    def _karar_yaz(self, bulgular):
        import json as _json
        k = karar(bulgular=bulgular)
        self.karar_yolu.write_text(_json.dumps(k, ensure_ascii=False), encoding="utf-8")

    def test_operator_anahtari_olmadan_atlama_reddedilir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı")
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("operatör ortam anahtarı yok", s.stderr)
        self.assertIn("reddedildi: operatör anahtarı yok", self.log.read_text(encoding="utf-8"))

    def test_yuksek_bulguda_atlama_imkansiz(self):
        self._karar_yaz([{"dosya": "a.py", "satir": 1, "onem": "yuksek", "aciklama": "x",
                          "kabul": "düzeltilince kapanır"}])
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("atlanamaz", s.stderr)

    def test_kisa_gerekce_reddedilir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kısa", env_anahtar=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("gerekce", s.stderr.replace("ç", "c").replace("Ç", "C"))

    def test_operator_anahtari_ve_gerekceyle_atlanir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("KARAR KAPISI: ATLANDI", s.stdout)
        self.assertIn("KARAR KAPISI ATLANDI", s.stdout)          # PR yorumunda görünür
        self.assertIn('"olay": "ATLANDI"', self.log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
