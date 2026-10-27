"""nobetci-kur.sh — systemd unit üretimi (profil ayrımı + düşük öncelik).

26 Ekim i5 mimarisi: nöbetçi kendi profiliyle (`hermes -p guvenlik`) ve düşük CPU önceliğiyle
çalışmalı ki Open WebUI yükü PR incelemesini aç bırakmasın. Bu sözleşme unit dosyasında görünür
olmak zorunda — yoksa "ayırdım" sanılır ama aynı gateway'de çalışmaya devam eder.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

BETIK = Path(__file__).resolve().parents[2] / "nobetci-kur.sh"


def unit_uret(*argumanlar: str, home: str) -> str:
    ortam = {**os.environ, "HOME": home}
    s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", *argumanlar],
                       capture_output=True, text=True, timeout=60, env=ortam)
    assert s.returncode == 0, s.stderr
    return s.stdout


class UnitTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.home = self.dizin.name

    def tearDown(self):
        self.dizin.cleanup()

    def test_profilsizken_ayri_profil_yazilmaz(self):
        metin = unit_uret(home=self.home)
        self.assertNotIn("NOBETCI_PROFIL=", metin)
        self.assertNotIn("--profil", metin)
        self.assertIn("--rol i5", metin)

    def test_profil_hem_ortam_hem_arguman_olarak_yazilir(self):
        metin = unit_uret("--profil", "guvenlik", home=self.home)
        self.assertIn("Environment=NOBETCI_PROFIL=guvenlik", metin)
        self.assertIn("--profil guvenlik", metin)

    def test_dusuk_oncelik_zorunlu(self):
        metin = unit_uret("--profil", "guvenlik", home=self.home)
        self.assertIn("Nice=10", metin)
        self.assertIn("CPUWeight=50", metin)

    def test_rol_adi_profil_olamaz(self):
        ortam = {**os.environ, "HOME": self.home}
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--profil", "i5"],
                           capture_output=True, text=True, timeout=60, env=ortam)
        self.assertEqual(s.returncode, 2)
        self.assertIn("rol adıyla aynı", s.stderr)

    def test_profil_degeri_birime_enjeksiyon_yapamaz(self):
        """26 Ekim i5 bulgusu: --profil doğrulanmıyordu → satır sonu birime yönerge ekliyordu."""
        kotu = ["a\nExecStartPre=/bin/touch /tmp/pwn", "guvenlik\n", "Guvenlik", "gu venlik",
                "a" * 40, "-x", "guvenlik;rm", "../../etc"]
        for deger in kotu:
            ortam = {**os.environ, "HOME": self.home}
            s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--profil", deger],
                               capture_output=True, text=True, timeout=60, env=ortam)
            self.assertEqual(s.returncode, 2, f"kabul edildi: {deger!r} → {s.stdout}")
            self.assertNotIn("ExecStartPre", s.stdout)
            self.assertIn("geçersiz --profil", s.stderr)

    def test_gecerli_profil_kabul_edilir(self):
        for deger in ("guvenlik", "guvenlik-2", "guvenlik_2", "g"):
            metin = unit_uret("--profil", deger, home=self.home)
            self.assertIn(f"--profil {deger}", metin)

    # ── BELLEK TAVANI (26 Ekim: birim cgroup'unda node OOM/core dump) ──────────────────────────
    @staticmethod
    def _ram_mb() -> int:
        for satir in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if satir.startswith("MemTotal:"):
                return int(satir.split()[1]) // 1024
        return 0

    def test_bellek_tavani_birimde_ve_makineyle_uyumlu(self):
        """Tavanlar sabit değil, KURULUM ANINDA makineden ölçülür; 4 GB'lık i5'e 16 GB tavan yazılmaz."""
        ram = self._ram_mb()
        metin = unit_uret(home=self.home)
        self.assertIn("MemoryAccounting=yes", metin)
        self.assertIn("MemoryHigh=", metin)
        self.assertIn("MemoryMax=", metin)
        self.assertIn("OOMPolicy=stop", metin)
        yuksek = int(re.search(r"^MemoryHigh=(\d+)M$", metin, re.M).group(1))
        tavan = int(re.search(r"^MemoryMax=(\d+)M$", metin, re.M).group(1))
        self.assertLess(yuksek, tavan, "MemoryHigh < MemoryMax olmalı (yumuşak eşik önce)")
        if ram > 1024:
            self.assertAlmostEqual(tavan, ram * 75 // 100, delta=2,
                                   msg="MemoryMax makine RAM'inin %75'i olmalı")
            self.assertAlmostEqual(yuksek, ram * 60 // 100, delta=2)
            self.assertLess(tavan, ram, "bellek tavanı makine RAM'ini aşamaz")

    def test_node_v8_tavani_olculu(self):
        """Node çocukları RAM'in 1/4'ü kadar V8 tavanı devralır (512–2048 arası sınırlı)."""
        ram = self._ram_mb()
        metin = unit_uret(home=self.home)
        m = re.search(r"^Environment=NODE_OPTIONS=--max-old-space-size=(\d+)$", metin, re.M)
        self.assertIsNotNone(m, "NODE_OPTIONS tavansız → V8 'FatalProcessOutOfMemory' riski")
        heap = int(m.group(1))
        self.assertGreaterEqual(heap, 512)
        self.assertLessEqual(heap, 2048)
        if ram > 2048:
            self.assertLessEqual(heap, ram, "V8 tavanı makine RAM'ini aşamaz")

    def test_cokme_dongusu_freni_var(self):
        """Restart=always tek başına çökme döngüsünü sonsuzlaştırır (her tur = token + core dump)."""
        metin = unit_uret(home=self.home)
        self.assertIn("StartLimitIntervalSec=300", metin)
        self.assertIn("StartLimitBurst=5", metin)
        self.assertIn("TasksMax=", metin)
        self.assertIn("TimeoutStopSec=", metin)

    # ── İZLENEN DAL (27 Ekim kilitlenmesi) ──────────────────────────────────────────────────
    def test_varsayilan_dal_main_birimde_gorunur(self):
        metin = unit_uret(home=self.home)
        self.assertIn("--dal main", metin)
        self.assertIn("--guncelle", metin)

    def test_dal_argumani_birime_yazilir(self):
        metin = unit_uret("--dal", "duzeltme/nobetci-fix", home=self.home)
        self.assertIn("--dal duzeltme/nobetci-fix", metin)

    def test_gecersiz_dal_reddedilir(self):
        for kotu in ("a..b", "a b", "-x", "a;rm"):
            with self.subTest(kotu=kotu):
                s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--dal", kotu],
                                   capture_output=True, text=True, timeout=60,
                                   env={**os.environ, "HOME": self.home})
                self.assertEqual(s.returncode, 2, s.stdout)
                self.assertIn("geçersiz --dal", s.stderr)

    def test_birim_metninde_backtick_yok(self):
        """Birim heredoc'u tırnaksız: backtick komut ÇALIŞTIRIR (sessiz bozulma)."""
        metin = unit_uret(home=self.home)
        for satir in metin.splitlines():
            if satir.startswith("#"):
                self.assertNotIn("`", satir, f"yorum satırında backtick: {satir}")

    def test_cokme_dongusu_sayaci_starttan_once_sifirlanir(self):
        """i5: OOM döngüsü birimi `failed` + start limiti dolu bırakır → `start` reddedilir.

        Kurulumun başarısız GÖRÜNMEMESİ için sayaç start'tan önce sıfırlanmalı.
        """
        kaynak = BETIK.read_text(encoding="utf-8")
        self.assertIn("reset-failed", kaynak)
        self.assertLess(kaynak.index("reset-failed"), kaynak.index('systemctl --user start'))


class KlonDegerKapiTesti(unittest.TestCase):
    """27 Ekim i5 bulgusu (düşük): `--klon` değeri doğrulanmadan birim METNİNE yazılıyordu →
    satır sonu taşıyan bir değer birime yeni yönerge enjekte edebiliyordu."""

    def test_satir_sonu_tasiyan_klon_reddedilir(self):
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru",
                            "--klon", "/tmp/klon\nExecStartPre=/bin/sh -c true"],
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "HOME": tempfile.mkdtemp()})
        self.assertEqual(s.returncode, 2, s.stdout + s.stderr)
        self.assertIn("geçersiz --klon", s.stderr)

    def test_goreli_klon_yolu_reddedilir(self):
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--klon", "goreli/yol"],
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "HOME": tempfile.mkdtemp()})
        self.assertEqual(s.returncode, 2)

    def test_nokta_nokta_iceren_klon_reddedilir(self):
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--klon", "/tmp/a/../../etc"],
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "HOME": tempfile.mkdtemp()})
        self.assertEqual(s.returncode, 2)


class PipefailSIGPIPETesti(unittest.TestCase):
    """`set -o pipefail` + `| head` = SESSİZ BAŞARISIZLIK.

    27 Ekim i5: `nobetci-kur.sh` son satırda `systemctl status | head -10` çalıştırıyordu; head
    okumayı bırakınca systemctl SIGPIPE (141) aldı, pipefail bunu script'in çıkış kodu yaptı →
    "=== kuruldu ===" yazdıktan SONRA "✗ birim kurulumu başarısız". Kullanıcı kurulumun
    başarısız olduğunu sandı. Kural: pipefail açıkken boruyu `head`/`tail` ile kapatan her
    KOMUT SATIRI `|| true` (veya `|| :`) ile korunur. Komut yerine koyma `$( … )` ve atamalar
    kapsam dışı (orada çıkış kodu script'i düşürmez).
    """

    KOK = Path(__file__).resolve().parents[3]

    def _betikler(self):
        for yol in sorted(self.KOK.glob("otomasyon/**/*.sh")):
            metin = yol.read_text(encoding="utf-8")
            if "pipefail" in metin:
                yield yol, metin

    def test_pipefail_acikken_head_tail_borulari_korunur(self):
        ihlaller = []
        for yol, metin in self._betikler():
            for no, satir in enumerate(metin.splitlines(), 1):
                s = satir.strip()
                if s.startswith("#") or "|" not in s:
                    continue
                if not re.search(r"\|\s*(head|tail)\b", s):
                    continue
                if "$(" in s or "|| true" in s or "|| :" in s:
                    continue
                ihlaller.append(f"{yol.relative_to(self.KOK)}:{no}: {s}")
        self.assertEqual(ihlaller, [],
                         "pipefail açıkken `| head`/`| tail` korumasız (SIGPIPE → sahte hata):\n"
                         + "\n".join(ihlaller))

    def test_kurulum_sonu_status_hatasi_kurulumu_dusurmez(self):
        kaynak = BETIK.read_text(encoding="utf-8")
        for satir in kaynak.splitlines():
            if "systemctl" in satir and re.search(r"\|\s*head\b", satir) and not satir.strip().startswith("#"):
                self.assertIn("|| true", satir, f"korunmasız boru: {satir}")


if __name__ == "__main__":
    unittest.main(verbosity=2)