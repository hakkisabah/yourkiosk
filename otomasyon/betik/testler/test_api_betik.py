"""api-sunucu-sertlestir.sh — kontrol noktaları (26 Ekim i5 bulgularının kilidi).

Üç hata sınıfı makineyle doğrulanır:
1. `--dinle` beyaz listesi: yanlış/yazım hatalı adres sessizce kabul edilmez.
2. `0.0.0.0` yalnız açık `--kabul-et-lan` ile yazılır (uç = terminal yetkili ajan).
3. Anahtar hiçbir zaman bir komut satırı argümanına konmaz (argv sızıntısı).
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

BETIK = Path(__file__).resolve().parents[1] / "api-sunucu-sertlestir.sh"


class DinleBeyazListeTesti(unittest.TestCase):
    def calistir(self, *argumanlar):
        return subprocess.run(["bash", str(BETIK), *argumanlar],
                              capture_output=True, text=True, timeout=60)

    def test_gecersiz_dinle_reddedilir(self):
        for adres in ("0.0.0.0/0", "192.168.1.5", "localhost", "172.17.0.1/16"):
            s = self.calistir("--dinle", adres, "--kuru")
            self.assertEqual(s.returncode, 2, f"{adres} kabul edildi: {s.stdout}{s.stderr}")
            self.assertIn("geçersiz --dinle", s.stderr)

    def test_lan_icin_acik_onay_gerekir(self):
        s = self.calistir("--dinle", "0.0.0.0", "--kuru")
        self.assertEqual(s.returncode, 2)
        self.assertIn("--kabul-et-lan", s.stderr)

    def test_izinli_adresler_gecer(self):
        for adres in ("127.0.0.1", "172.17.0.1", "172.18.0.1"):
            s = self.calistir("--dinle", adres, "--kuru")
            self.assertEqual(s.returncode, 0, f"{adres}: {s.stdout}{s.stderr}")
            self.assertIn(adres, s.stdout)


class AnahtarSizintisiTesti(unittest.TestCase):
    def test_anahtar_argv_ile_yazilmaz(self):
        ham = BETIK.read_text(encoding="utf-8")
        # Yorumları ayıkla: kural KOD için, açıklama metni değil.
        kod = "\n".join(s for s in ham.splitlines() if not s.lstrip().startswith("#"))
        # Değer doğrudan config set'e verilmemeli (argv → /proc/<pid>/cmdline).
        self.assertNotIn('config set API_SERVER_KEY', kod)
        self.assertNotIn('cfg_set API_SERVER_KEY', kod)
        # Anahtar .env'e python ile, yalnız YOL argümanları geçerek yazılmalı.
        self.assertIn("anahtari_env_yaz", kod)

    def test_env_yazici_gercekten_calisiyor(self):
        # Betikteki python gövdesini ayrı çalıştırıp .env'i gerçekten güncellediğini gör.
        import re
        import tempfile
        icerik = BETIK.read_text(encoding="utf-8")
        govde = re.search(r"<<'PY'\n(.*?)\nPY\n", icerik, re.S)
        self.assertIsNotNone(govde, "gömülü python gövdesi bulunamadı")
        assert govde is not None
        kod = govde.group(1)
        with tempfile.TemporaryDirectory() as dizin:
            env = Path(dizin) / ".env"
            env.write_text("BASKA=1\nAPI_SERVER_KEY=eski\nSON=2\n", encoding="utf-8")
            anahtar = Path(dizin) / "api-server.key"
            anahtar.write_text("y" * 64 + "\n", encoding="utf-8")
            s = subprocess.run(["python3", "-", str(env), str(anahtar)], input=kod,
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(s.returncode, 0, s.stderr)
            satirlar = env.read_text(encoding="utf-8").splitlines()
            self.assertIn("API_SERVER_KEY=" + "y" * 64, satirlar)
            self.assertIn("BASKA=1", satirlar)   # diğer satırlar korunur
            self.assertEqual(len(satirlar), 3)   # satır çoğaltmaz
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
