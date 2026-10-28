"""Prompt ve belgelerdeki betik yolları — depo köküne göre olmalı (26 Ekim i5 bulgusu).

Bulgu: `otomasyon/prompt/i5-guvenlik.md` (19, 25, 85, 91) betikleri
`~/<çalışma konumu>/yourkiosk/otomasyon/betik/...` gibi SABİT bir ev dizini köküyle çağırıyordu.
i5 makinesinde o dizin yok → prompttaki komutlar çalışmıyor, ajan ya komutu atlıyor ya da yanlış
yolda arıyor. Kilit: ağaç taraması — depodaki hiçbir metin/komut satırı betiği ev dizini köküyle
çağırmaz, promptlarda sabit çalışma kökü dizesi kalmaz.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

#: depo kökü (otomasyon/betik/testler → 3 üst dizin)
KOK = Path(__file__).resolve().parents[3]
PROMPT = KOK / "otomasyon" / "prompt"
#: Yasak dize parçalanarak yazılır: bu test dosyasının kendisi de taranıyor.
SABIT_KOK = "calisma_" + "konumun"
#: yasak desen: betiği ev dizini köküyle çağırmak (tilde ya da $HOME ile başlayan kök)
EV_DIZINI_BETIK = re.compile(r"python3\s+[~$][^\s]*otomasyon/betik/")
#: prompt içindeki göreli çağrı: `python3 otomasyon/betik/x.py`
GORELI_CAGRi = re.compile(r"python3\s+otomasyon/betik/([\w.-]+\.py)")
ATLANAN_DIZINLER = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".mypy_cache"}
METIN_UZANTILARI = {".md", ".py", ".sh", ".txt", ".service", ".json"}


def metin_dosyalari(kok: Path):
    for yol in sorted(kok.rglob("*")):
        if not yol.is_file() or yol.suffix not in METIN_UZANTILARI:
            continue
        if any(parca in ATLANAN_DIZINLER for parca in yol.parts):
            continue
        try:
            yield yol, yol.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


class BetikYollariTesti(unittest.TestCase):
    def test_promptlarda_sabit_calisma_koku_kalmaz(self):
        dosyalar = sorted(PROMPT.glob("*.md"))
        self.assertTrue(dosyalar, f"prompt dosyası bulunamadı: {PROMPT}")
        for yol, metin in ((y, y.read_text(encoding="utf-8")) for y in dosyalar):
            self.assertNotIn(SABIT_KOK, metin, f"{yol.name}: sabit çalışma kökü dizesi kaldı")

    def test_agacta_ev_dizini_koklu_betik_cagrisi_yok(self):
        suclular = []
        for yol, metin in metin_dosyalari(KOK):
            for no, satir in enumerate(metin.splitlines(), 1):
                if EV_DIZINI_BETIK.search(satir):
                    suclular.append(f"{yol.relative_to(KOK)}:{no}: {satir.strip()}")
        self.assertEqual(suclular, [], "betik yolu ev dizini köküne bağlı:\n" + "\n".join(suclular))

    def test_promptlardaki_betik_cagrilari_depo_kokune_gore(self):
        """Her `python3 otomasyon/betik/x.py` çağrısı gerçekten var olan bir dosyaya işaret eder."""
        for yol in sorted(PROMPT.glob("*.md")):
            metin = yol.read_text(encoding="utf-8")
            adlar = GORELI_CAGRi.findall(metin)
            self.assertTrue(adlar, f"{yol.name}: depo köküne göre betik çağrısı yok")
            for ad in adlar:
                self.assertTrue((KOK / "otomasyon" / "betik" / ad).is_file(),
                                f"{yol.name}: olmayan betik → otomasyon/betik/{ad}")


class SudoYasagiTesti(unittest.TestCase):
    """28 Ekim canlı bulgu: oturumdaki ajan parolasız `sudo` denedi → pam_faillock hesabı kilitledi.

    Kilit iki taraflı zarar verdi: ajan kendi yetki adımlarını yapamadı, operatör (parolayı bilen
    tek kişi) de o makineye sudo yapamaz hâle geldi. Kural bu yüzden HER iki promptta yazılı
    olmalı ve "yetki gereken adımı bulgu olarak yaz" davranışını söylemeli.
    """

    def test_her_promptta_sudo_yasagi_var(self):
        for ad in ("i5-guvenlik.md", "i3-karar.md"):
            metin = (PROMPT / ad).read_text(encoding="utf-8")
            self.assertIn("SUDO YOK", metin, f"{ad}: sudo yasağı bloğu yok")
            self.assertIn("faillock", metin, f"{ad}: kilitlenme nedeni (pam_faillock) yazılı değil")
            self.assertIn("BULGU", metin, f"{ad}: 'yetki adımını bulgu olarak yaz' kuralı yok")

    def test_sudo_yasagi_bellek_kuralindan_sonra_gelir(self):
        """Ajan promptu sırayla okur: yasak, komut örneklerinden ÖNCE durmalı."""
        metin = (PROMPT / "i5-guvenlik.md").read_text(encoding="utf-8")
        self.assertLess(metin.index("SUDO YOK"), metin.index("## Akış"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
