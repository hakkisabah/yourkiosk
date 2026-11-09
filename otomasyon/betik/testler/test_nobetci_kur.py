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
TEMIZLENECEK = ("NOBETCI_ARAC", "DSH_CHECKOUT", "DSH_PERMISSION_MODE", "NOBETCI_PROFIL")


def temiz_ortam(home: str, **ek: str) -> dict[str, str]:
    """Test ortamı ana kabuğun DSH değişkenlerini devralmasın (7 Kasım i5 bulgusu)."""
    return {**{k: v for k, v in os.environ.items() if k not in TEMIZLENECEK},
            "HOME": home, **ek}


def unit_uret(*argumanlar: str, home: str) -> str:
    ortam = temiz_ortam(home)
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
        ortam = temiz_ortam(self.home)
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--profil", "i5"],
                           capture_output=True, text=True, timeout=60, env=ortam)
        self.assertEqual(s.returncode, 2)
        self.assertIn("rol adıyla aynı", s.stderr)

    def test_zaman_asimi_birime_yazilir(self):
        """28 Ekim ölçümü: tur başına 46 sn gerçek süre → türetilmiş 1860 sn bütçe #90'ı öldürdü."""
        metin = unit_uret(home=self.home)
        self.assertIn("--zaman-asimi 3600", metin)

    def test_zaman_asimi_ortamla_degisir(self):
        ortam = temiz_ortam(self.home, NOBETCI_ZAMAN_ASIMI="5400")
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru"],
                           capture_output=True, text=True, timeout=60, env=ortam)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("--zaman-asimi 5400", s.stdout)

    def test_gecersiz_zaman_asimi_reddedilir(self):
        for deger in ("abc", "0", "299", "7201", "60;rm -rf /"):
            ortam = temiz_ortam(self.home, NOBETCI_ZAMAN_ASIMI=deger)
            s = subprocess.run(["bash", str(BETIK), "i5", "--kuru"],
                               capture_output=True, text=True, timeout=60, env=ortam)
            self.assertEqual(s.returncode, 2, f"kabul edildi: {deger!r}")
            self.assertNotIn("--zaman-asimi 60;", s.stdout)

    def test_profil_degeri_birime_enjeksiyon_yapamaz(self):
        """26 Ekim i5 bulgusu: --profil doğrulanmıyordu → satır sonu birime yönerge ekliyordu."""
        kotu = ["a\nExecStartPre=/bin/touch /tmp/pwn", "guvenlik\n", "Guvenlik", "gu venlik",
                "a" * 40, "-x", "guvenlik;rm", "../../etc"]
        for deger in kotu:
            ortam = temiz_ortam(self.home)
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

    def test_yetki_yukseltme_kapali(self):
        """7 Kasım i5 bulgusu: birimde NoNewPrivileges yoktu → oturum içi sudo denemesi
        pam_faillock ile hesabı kilitliyordu (ajan da operatör de sudo yapamıyordu)."""
        metin = unit_uret(home=self.home)
        self.assertIn("NoNewPrivileges=true", metin)
        # PrivateTmp EKLENMEZ: karar dosyaları /tmp üzerinden operatörle paylaşılıyor.
        self.assertNotIn("PrivateTmp=true", metin)

    def test_bakim_dropininde_de_yetki_yukseltme_kapali(self):
        """Bakım betiğinin yazdığı drop-in de aynı kapıyı taşımalı (birim metni tek kaynak değil)."""
        metin = (BETIK.parents[1] / "otomasyon" / "betik" / "nobetci-bakim.sh").read_text(encoding="utf-8")
        self.assertIn("NoNewPrivileges=true", metin)
        self.assertNotIn("PrivateTmp=true", metin)

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
                                   env=temiz_ortam(self.home))
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


class DshUnitTesti(unittest.TestCase):
    """2026-11-08 DSH geçişi: birim `--arac dsh` ile headless'i seçmeli, Hermes profili aramamalı."""

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.home = self.dizin.name

    def tearDown(self):
        self.dizin.cleanup()

    def test_dsh_araci_birime_yazilir(self):
        metin = unit_uret("--arac", "dsh", home=self.home)
        self.assertIn("Environment=NOBETCI_ARAC=dsh", metin)
        self.assertIn("Environment=DSH_CHECKOUT=", metin)
        self.assertIn("Environment=DSH_PERMISSION_MODE=read-only", metin)
        self.assertIn("--arac dsh", metin)
        self.assertNotIn("NOBETCI_PROFIL=", metin)

    def test_varsayilan_hermes_korunur(self):
        metin = unit_uret(home=self.home)
        self.assertIn("Environment=NOBETCI_ARAC=hermes", metin)
        self.assertIn("--arac hermes", metin)
        self.assertNotIn("DSH_CHECKOUT=", metin)

    def test_workspace_write_reddedilir(self):
        ortam = temiz_ortam(self.home, DSH_PERMISSION_MODE="workspace-write")
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--arac", "dsh"],
                           capture_output=True, text=True, timeout=60, env=ortam)
        self.assertEqual(s.returncode, 2)
        self.assertIn("yalnız read-only", s.stderr)

    def test_dsh_profille_reddedilir(self):
        ortam = temiz_ortam(self.home)
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--arac", "dsh",
                            "--profil", "guvenlik"],
                           capture_output=True, text=True, timeout=60, env=ortam)
        self.assertEqual(s.returncode, 2)
        self.assertIn("profil yalnız Hermes", s.stderr)

    def test_gecersiz_arac_reddedilir(self):
        ortam = temiz_ortam(self.home)
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--arac", "baska"],
                           capture_output=True, text=True, timeout=60, env=ortam)
        self.assertEqual(s.returncode, 2)
        self.assertIn("geçersiz --arac", s.stderr)

    def test_dsh_checkout_kabuk_metasi_reddedilir(self):
        for kotu in ("/tmp/dsh$HOME", "/tmp/dsh space", "/tmp/dsh;rm", "/tmp/dsh`id`"):
            with self.subTest(kotu=kotu):
                ortam = {**os.environ, "HOME": self.home, "DSH_CHECKOUT": kotu}
                s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--arac", "dsh"],
                                   capture_output=True, text=True, timeout=60, env=ortam)
                self.assertEqual(s.returncode, 2, s.stdout + s.stderr)
                self.assertIn("geçersiz DSH_CHECKOUT", s.stderr)

    def test_dsh_checkout_enjeksiyonu_reddedilir(self):
        ortam = temiz_ortam(self.home,
                 DSH_CHECKOUT="/tmp/dsh\nExecStartPre=/bin/true")
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--arac", "dsh"],
                           capture_output=True, text=True, timeout=60, env=ortam)
        self.assertEqual(s.returncode, 2)
        self.assertNotIn("ExecStartPre", s.stdout)
        self.assertIn("geçersiz DSH_CHECKOUT", s.stderr)


class DshSandboxDosyaTesti(unittest.TestCase):
    """Güvenli runner ve profil depoda sürümlenmeli; user systemd/D-Bus maskeli olmalı."""

    def test_runner_user_systemd_ve_dbus_maskeler(self):
        runner = (BETIK.parents[1] / "otomasyon" / "dsh-bwrap-kiosk").read_text(encoding="utf-8")
        self.assertIn("--tmpfs /run/user", runner)
        self.assertIn("--tmpfs /run/dbus", runner)
        self.assertIn("--bind", runner)
        self.assertIn("bwrap", runner)

    def test_headless_profili_guvenli_runneri_kullanir(self):
        profil = (BETIK.parents[1] / "otomasyon" / "dsh-headless.cordis.patch.yml").read_text(encoding="utf-8")
        self.assertIn("dsh-bwrap-kiosk", profil)
        self.assertIn("runnerCommand", profil)


class BakimDshTesti(unittest.TestCase):
    """Bakım betiği etkin DSH ayarlarını birimden okuyup kuruluma geçirmeli."""

    def test_bakim_arac_ve_dsh_ayarlarini_gecirir(self):
        metin = (BETIK.parents[1] / "otomasyon" / "betik" / "nobetci-bakim.sh").read_text(encoding="utf-8")
        self.assertIn("birim_env", metin)
        self.assertIn("NOBETCI_ARAC", metin)
        self.assertIn('--arac "$ARAC"', metin)
        self.assertIn("DSH_CHECKOUT", metin)
        self.assertIn("DSH_PERMISSION_MODE", metin)
        self.assertIn("read-only", metin)


class TemizOrtamTesti(unittest.TestCase):
    """Kurulum testleri ana kabuğun NOBETCI_ARAC/DSH_* değerlerini devralmamalı."""

    def test_dsh_ortami_varsayilan_hermes_testini_bozmaz(self):
        eski = {k: os.environ.get(k) for k in TEMIZLENECEK}
        try:
            os.environ.update({"NOBETCI_ARAC": "dsh", "DSH_CHECKOUT": "/yanlis",
                               "DSH_PERMISSION_MODE": "read-only", "NOBETCI_PROFIL": "guvenlik"})
            with tempfile.TemporaryDirectory() as home:
                metin = unit_uret(home=home)
            self.assertIn("Environment=NOBETCI_ARAC=hermes", metin)
            self.assertNotIn("DSH_CHECKOUT=", metin)
        finally:
            for k, v in eski.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class KlonDegerKapiTesti(unittest.TestCase):
    """27 Ekim i5 bulgusu (düşük): `--klon` değeri doğrulanmadan birim METNİNE yazılıyordu →
    satır sonu taşıyan bir değer birime yeni yönerge enjekte edebiliyordu."""

    def test_satir_sonu_tasiyan_klon_reddedilir(self):
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru",
                            "--klon", "/tmp/klon\nExecStartPre=/bin/sh -c true"],
                           capture_output=True, text=True, timeout=60,
                           env=temiz_ortam(tempfile.mkdtemp()))
        self.assertEqual(s.returncode, 2, s.stdout + s.stderr)
        self.assertIn("geçersiz --klon", s.stderr)

    def test_goreli_klon_yolu_reddedilir(self):
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--klon", "goreli/yol"],
                           capture_output=True, text=True, timeout=60,
                           env=temiz_ortam(tempfile.mkdtemp()))
        self.assertEqual(s.returncode, 2)

    def test_nokta_nokta_iceren_klon_reddedilir(self):
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--klon", "/tmp/a/../../etc"],
                           capture_output=True, text=True, timeout=60,
                           env=temiz_ortam(tempfile.mkdtemp()))
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

class ZamanAsimiTekKaynakTesti(unittest.TestCase):
    """Varsayılan zaman aşımı TEK kaynaktan gelir: modül → servis birimi → belge."""

    def test_zaman_asimi_tek_kaynak_modul_servis_belge(self):
        """6 Kasım i5 bulgusu: nobetci.py 1860, kur.sh 3600, NOBETCI.md 1860 yazıyordu."""
        import importlib.util

        modul_yolu = BETIK.parent / "betik" / "nobetci.py"
        spec = importlib.util.spec_from_file_location("nobetci_tek_kaynak", modul_yolu)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        varsayilan = mod.VARSAYILAN_ZAMAN_ASIMI

        with tempfile.TemporaryDirectory() as home:
            birim = unit_uret(home=home)
        self.assertIn(f"--zaman-asimi {varsayilan}", birim,
                      "servis birimi modüldeki varsayılanı yazmıyor")

        belge = (BETIK.parent / "NOBETCI.md").read_text(encoding="utf-8")
        self.assertIn(f"{varsayilan} sn", belge,
                      f"NOBETCI.md {varsayilan} sn yazmıyor (modül/servis/belge ayrıştı)")
        self.assertNotIn("1860 sn (tavan", belge,
                         "belgede eski türetilmiş varsayılan (1860 sn) geri gelmiş")
        self.assertGreaterEqual(varsayilan, mod.TUR_TAVANINDAN_TUREYEN_S)


if __name__ == "__main__":
    unittest.main(verbosity=2)