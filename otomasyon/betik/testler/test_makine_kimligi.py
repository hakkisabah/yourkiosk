"""Makine kimliği eşlemesi ve operatör betiği — yayınlanmış ağaçta bulunmalı.

Neden bu test var (gerçek arıza): `otomasyon/betik/makine-kimligi-kur.sh` uzun süre
yalnız bir çalışma dalında kaldı. Operatöre verilen belgelenmiş komut
(`git show FETCH_HEAD:otomasyon/betik/makine-kimligi-kur.sh > /tmp/mk.sh`) bu yüzden
`fatal: path ... does not exist in 'FETCH_HEAD'` ile patladı; operatör betiği hiç
çalıştıramadı. Aynı sınıf hata: i3 kaydı eşleme dosyasında olmadığı için iki onay
kapısı (i5 + i3) çözülemedi ve PR birleştirme kilitlendi.

Kilit: eşleme dosyası yayınlanmış ağaçta olacak, geçerli olacak, iki kapı rolünü de
(i5, i3) içerecek ve operatör betiği depoda bulunacak. Ham machine-id depoya asla
yazılmaz — yalnız ayrımlı sha256 özeti.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]
ESLEME = KOK / "otomasyon" / "makine-kimlikleri.json"
BETIK = KOK / "otomasyon" / "betik" / "makine-kimligi-kur.sh"
#: İki onay kapısının rolleri. İkisi de kayıtlı değilse birleştirme kapısı çözülemez.
KAPI_ROLLERI = ("i5", "i3")
OZET_RE = re.compile(r"^[0-9a-f]{64}$")


class MakineKimligiTestleri(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(ESLEME.is_file(), f"eşleme dosyası yok: {ESLEME}")
        self.veri = json.loads(ESLEME.read_text(encoding="utf-8"))

    def test_esleme_sozluk(self) -> None:
        self.assertIsInstance(self.veri, dict)
        self.assertTrue(self.veri, "eşleme boş")

    def test_her_kayit_gecerli(self) -> None:
        for rol, kayit in self.veri.items():
            with self.subTest(rol=rol):
                self.assertIsInstance(kayit, dict)
                ozet = str(kayit.get("kimlik_ozet", "")).strip().lower()
                self.assertRegex(ozet, OZET_RE, f"{rol}: kimlik_ozet 64 haneli sha256 olmalı")
                self.assertTrue(str(kayit.get("hostname", "")).strip(), f"{rol}: hostname boş")

    def test_kapi_rolleri_kayitli(self) -> None:
        """İki onay kapısının rolü de eşlemede olmalı (yoksa merge kapısı kapanır)."""
        eksik = [r for r in KAPI_ROLLERI if r not in self.veri]
        self.assertEqual([], eksik, f"eşlemede eksik kapı rolü: {eksik}")

    def test_ozet_benzersiz(self) -> None:
        """İki rol aynı makineye işaret edemez: tek makine kendini iki kapı ilan edemez."""
        ozetler = [str(k.get("kimlik_ozet", "")).strip().lower() for k in self.veri.values()]
        self.assertEqual(len(ozetler), len(set(ozetler)), "aynı kimlik_ozet iki role yazılmış")

    def test_operator_betigi_depoda(self) -> None:
        """Belgelenmiş operatör komutu betiği yayınlanmış ağaçtan okuyabilmeli."""
        self.assertTrue(BETIK.is_file(), f"operatör betiği eksik: {BETIK}")
        self.assertTrue(BETIK.stat().st_mode & 0o111, "betik çalıştırılabilir değil")

    def test_ham_machine_id_depoda_yok(self) -> None:
        """Depo herkese açık: ham machine-id (32 hex) yazılmamalı, yalnız ayrımlı özet."""
        ham = re.compile(r"\b[0-9a-f]{32}\b")
        for rol, kayit in self.veri.items():
            for deger in kayit.values():
                with self.subTest(rol=rol):
                    self.assertIsNone(ham.search(str(deger)), f"{rol}: ham machine-id sızmış")


if __name__ == "__main__":
    unittest.main()
