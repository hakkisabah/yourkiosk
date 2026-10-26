"""ortam-kontrol.py — makine kimliği denetimi (26 Ekim i5 bulgusunun kilidi).

Neden ayrı test: kimlik kuralı `yaz.py` içinde uygulanıyor; denetim betiği kendi kopyasını
yazarsa iki kural ayrışır ve "ortam-kontrol ✓ dedi ama yazım kimliği reddetti" durumu doğar.
Bu yüzden iki şey makineyle doğrulanır:

1. Denetim, kuralı KOPYALAMAZ — `yaz.py`'den çağırır (kaynakta ikinci bir `st_uid` denetimi yok).
2. Kimlik yok / rol uyuşmuyor / uyuşuyor: üç durumda da doğru ✓/✗ satırı ve çözüm komutu çıkar.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

BETIK_DIZINI = Path(__file__).resolve().parents[1]
ORTAM = BETIK_DIZINI / "ortam-kontrol.py"


def _yukle():
    spec = importlib.util.spec_from_file_location("ortam_kontrol_test", ORTAM)
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul  # type: ignore[return-value]


class _SahteYaz:
    """`yaz.py` yerine geçen en küçük modül: kimlik kuralının SONUCUNU enjekte eder."""

    KIMLIK_VARSAYILAN = Path("/etc/yourkiosk-makine-kimligi")

    def __init__(self, kimlik: str, neden: str = "") -> None:
        self.kimlik = kimlik
        self.neden = neden

    def makine_kimligi_denetle(self, *_a, **_k):
        return self.kimlik, self.neden


class MakineKimligiDenetimiTesti(unittest.TestCase):
    def setUp(self) -> None:
        self.ok = _yukle()
        self.ok.DENETIM = {"satir": [], "sorun": 0}

    def _metin(self) -> str:
        return "\n".join(self.ok.DENETIM["satir"])

    def test_kural_kopyalanmaz_yaz_py_den_cagrilir(self):
        """İkinci bir uid denetimi yazılırsa test kırmızıya döner (kural tek yerde)."""
        kaynak = ORTAM.read_text(encoding="utf-8")
        self.assertIn("makine_kimligi_denetle", kaynak)
        self.assertNotIn("st_uid", kaynak, "kimlik kuralı kopyalanmış: yaz.py'den çağırın")

    def test_kimlik_yoksa_kirmizi_ve_operator_komutu(self):
        self.ok.YAZ_MODUL = _SahteYaz("", "makine kimliği yok (/etc/yourkiosk-makine-kimligi)")
        self.ok.makine_kimligi_kontrolu("i5", None)
        metin = self._metin()
        self.assertRegex(metin, r"✗ makine kimliği")
        self.assertIn("sudo sh -c 'printf i5 > /etc/yourkiosk-makine-kimligi'", metin)
        self.assertIn("sudo chmod 0644 /etc/yourkiosk-makine-kimligi", metin)
        self.assertEqual(self.ok.DENETIM["sorun"], 1)

    def test_rol_uyusmuyorsa_kirmizi(self):
        """i3 olarak kurulu makinede --rol i5: kimlik uyuşmazlığı sessizce geçilemez."""
        self.ok.YAZ_MODUL = _SahteYaz("i3")
        self.ok.makine_kimligi_kontrolu("i5", None)
        metin = self._metin()
        self.assertRegex(metin, r"✗ makine kimliği")
        self.assertIn("'i3' olarak kurulu", metin)
        self.assertIn("--rol 'i5'", metin)

    def test_rol_uyusuyorsa_yesil(self):
        self.ok.YAZ_MODUL = _SahteYaz("i5")
        self.ok.makine_kimligi_kontrolu("i5", None)
        self.assertRegex(self._metin(), r"✓ makine kimliği\s*: i5")
        self.assertEqual(self.ok.DENETIM["sorun"], 0)

    def test_rol_kiosk_ve_dev_icin_kimlik_denetlenmez(self):
        """Kiosk cihazında ve geliştirici makinesinde kimlik dosyası aranmaz (kapı akışı yok)."""
        kaynak = ORTAM.read_text(encoding="utf-8")
        self.assertIn('if a.rol in ("i5", "i3"):', kaynak)
        # Çağrı, ajan rolü bloğunun İÇİNDE olmalı: kiosk/dev dallarında çalışmamalı.
        blok = kaynak.split('if a.rol in ("i5", "i3"):', 1)[1]
        self.assertIn("makine_kimligi_kontrolu(a.rol", blok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
