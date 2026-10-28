"""DEPO HİJYENİ — sembolik bağ / derleme çıktısı sızıntısı (26 Ekim i5 bulgusunun kilidi).

NE OLDU: #86 head'i depoya `web/dist` adında, hedefi `/home/hakki/evrim_otonom/yourkiosk/web/dist`
olan 120000 modlu bir girdi ekledi. İki hata birleşti:

  1. `.gitignore` kuralı `web/dist/` (sondaki `/`) yalnız **dizini** yok sayar; adı `dist` olan
     bir dosya/sembolik bağ kuralı atlar.
  2. Böyle bir bağ depoya girerse temiz klonda ve Docker imajında derlenmiş arayüzü **kırar**
     (hedef yol yalnız o makinede var) — kiosk beyaz ekran verir.

Kilit (makineyle doğrulanır, iki bağımsız yol):
  · izlenen hiçbir girdi 120000 (sembolik bağ) olmamalı, olursa hedefi depo DIŞINA çıkmamalı;
  · `web/dist` ve `panel/dist` izlenmemeli ve `git check-ignore` ile gerçekten yok sayılmalı
    ( `.gitignore` yeniden `/` eklenirse bu test kırmızıya döner).
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]


def _git(*argumanlar: str) -> str:
    sonuc = subprocess.run(["git", "-C", str(KOK), *argumanlar],
                           capture_output=True, text=True, timeout=120, check=False)
    if sonuc.returncode != 0:
        raise AssertionError(f"git {' '.join(argumanlar)} başarısız: {sonuc.stderr.strip()}")
    return sonuc.stdout


class DepoHijyeniTesti(unittest.TestCase):
    def test_izlenen_sembolik_bag_yok_ya_da_depo_icinde(self):
        """120000 modlu girdi varsa hedefi depo içinde kalmalı (mutlak yol yasak)."""
        ihlal = []
        for satir in _git("ls-files", "-s", "-z").split("\0"):
            if not satir.strip():
                continue
            ustbilgi, ad = satir.split("\t", 1)
            mod = ustbilgi.split()[0]
            if mod != "120000":
                continue
            hedef = (KOK / ad).readlink()
            if hedef.is_absolute():
                ihlal.append(f"{ad} → {hedef} (MUTLAK yol: temiz klonda kırılır)")
                continue
            cozulmus = (KOK / ad).parent / hedef
            try:
                cozulmus.resolve().relative_to(KOK.resolve())
            except ValueError:
                ihlal.append(f"{ad} → {hedef} (depo dışına çıkıyor)")
        self.assertEqual(ihlal, [], "izlenen sembolik bağ(lar) güvensiz:\n" + "\n".join(ihlal))

    def test_derleme_ciktisi_izlenmiyor(self):
        izlenen = set(_git("ls-files", "-z").split("\0"))
        for ad in ("web/dist", "panel/dist", "web/node_modules", "panel/node_modules"):
            self.assertNotIn(ad, izlenen, f"{ad} depoya izlenmiş — derleme çıktısı depoya girmez")

    def test_gitignore_sondaki_slash_ile_kacirmiyor(self):
        """`web/dist/` biçimine dönülürse (dizine özel kural) test kırmızıya döner."""
        for ad in ("web/dist", "panel/dist"):
            cikti = subprocess.run(["git", "-C", str(KOK), "check-ignore", "-v", "--no-index", ad],
                                   capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(cikti.returncode, 0,
                             f"{ad} yok sayılmıyor (kural: {ad}/ biçiminde olabilir)")
            self.assertIn(ad, cikti.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
