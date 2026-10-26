"""Belgeler sabit test SAYISI yazmaz — sayı çıktıdan okunur (26 Ekim i5 bulgusunun kilidi).

NE OLDU: aynı sınıf bulgu üç turdur tekrar ediyor. `SIRADAKI-ISLER.md` "kiosk 352 · web 108 ·
panel 104" diyordu, gerçek 519/108/104; `README.md` 319, `kiosk/README.md` 290/58,
`kiosk/GUVENLIK.md` 134, `web/README.md` 84, `web/CALISTIRMA.md` 86, `GITHUB-YUKLEME.md` 319 —
hepsi bayattı. Sayı bir kez yazılınca ilk test eklendiğinde yalan oluyor ve i5 her turda aynı
bulguyu yazıyor ("bildirdim ama değişmedi" algısının kaynağı).

KURAL: belgede "N test" yazılmaz; komut yazılır (`bash tools/test.sh`), sayı çıktıdan okunur.
Bu test kuralı makineyle uygular: izlenen `.md` dosyalarında `\d+ test` kalıbı geçemez.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]
#: "352 test", "kiosk 370+ / web 111 test", "(21 test)", "14 test" — hepsi aynı sınıf.
KALIP = re.compile(r"\b\d{2,4}\+?\s*test\b", re.IGNORECASE)


def _izlenen_belgeler() -> list[Path]:
    sonuc = subprocess.run(["git", "-C", str(KOK), "ls-files", "-z", "*.md"],
                           capture_output=True, check=True, timeout=120)
    adlar = [ad for ad in sonuc.stdout.decode("utf-8", errors="replace").split("\0") if ad]
    return [KOK / ad for ad in adlar if "node_modules" not in ad]


class BelgeTestSayisiTesti(unittest.TestCase):
    def test_belgelerde_sabit_test_sayisi_yok(self):
        ihlal = []
        for yol in _izlenen_belgeler():
            try:
                metin = yol.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for no, satir in enumerate(metin.splitlines(), 1):
                if KALIP.search(satir):
                    ihlal.append(f"{yol.relative_to(KOK)}:{no}: {satir.strip()[:120]}")
        self.assertEqual(
            ihlal, [],
            "Belgede sabit test sayısı var (bayatlar). Komutu yazın, sayıyı çıktıdan okuyun:\n"
            + "\n".join(ihlal),
        )

    def test_kural_kendini_dogrular(self):
        """Kalıp gerçekten yakalıyor mu? (test körse kural da yok sayılır)"""
        for ornek in ("319 test", "kiosk 370+ / web 111 test", "`x.test.ts` (21 test)", "14 test."):
            self.assertIsNotNone(KALIP.search(ornek), ornek)
        for temiz in ("bash tools/test.sh", "birim + güvenlik testleri", "testler yeşil"):
            self.assertIsNone(KALIP.search(temiz), temiz)


if __name__ == "__main__":
    unittest.main(verbosity=2)
