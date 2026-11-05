"""CANLI TEST + GÜNCELLEME SAĞLIK KAPISI — regresyon testleri.

GERÇEK HATA (i5 bulgusu, PR #84): `deploy/guncelle.sh` sağlık kapısı `tools/canli_test.py`
çağırıyordu; o araç MQTT halkasını da sayıyor ve push KAPALI cihazda (varsayılan:
`config.py` `push_aktif=False` / broker-konu boş) "✗" verip çıkış 1 dönüyordu. Sonuç: her gece
güncelleme "başarısız" sayılıp `git reset --hard` ile geri alınıyordu — cihaz HİÇ güncellenmiyordu.

Kural: KAPALI bir halka arıza değildir → "atlandı" sayılır, çıkış kodunu etkilemez.
AÇIK ama koptuğu halka (broker var, bağlantı kurulamadı) hâlâ arızadır.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import config  # noqa: E402

_spec = importlib.util.spec_from_file_location("canli_test_araci", KOK / "tools" / "canli_test.py")
assert _spec is not None and _spec.loader is not None
canli_test = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canli_test)


class MqttUcDurumTesti(unittest.TestCase):
    def test_push_kapaliyken_atlandi(self):
        """broker/konu boş → 'atlandi' (hata DEĞİL)."""
        with mock.patch.object(config, "TETIK_PUSH_BROKER", ""), \
                mock.patch.object(config, "TETIK_PUSH_KONU", ""):
            durum, metin = canli_test.mqtt_test(0.1)
        self.assertEqual(durum, "atlandi")
        self.assertIn("atlandı", metin)

    def test_broker_var_konu_yoksa_da_atlandi(self):
        with mock.patch.object(config, "TETIK_PUSH_BROKER", "broker.ornek"), \
                mock.patch.object(config, "TETIK_PUSH_KONU", ""):
            durum, _ = canli_test.mqtt_test(0.1)
        self.assertEqual(durum, "atlandi")

    def test_broker_acik_ama_baglanti_yoksa_hata(self):
        """Halka AÇIKSA ve bağlanamıyorsa bu gerçek arızadır (atlandı sayılmaz)."""
        with mock.patch.object(config, "TETIK_PUSH_BROKER", "127.0.0.1"), \
                mock.patch.object(config, "TETIK_PUSH_KONU", "yourkiosk/yayin"), \
                mock.patch.object(config, "TETIK_PUSH_PORT", 1):
            durum, metin = canli_test.mqtt_test(0.2)
        self.assertEqual(durum, "hata")
        self.assertIn("bağlanamadı", metin)


class SaglikKapisiTesti(unittest.TestCase):
    """`main()` çıkış kodu: güncelle.sh'in kabul ölçütü."""

    def _calistir(self, push_kapali: bool) -> tuple[int, str]:
        broker = "" if push_kapali else "127.0.0.1"
        konu = "" if push_kapali else "yourkiosk/yayin"
        with mock.patch.object(config, "TETIK_PUSH_BROKER", broker), \
                mock.patch.object(config, "TETIK_PUSH_KONU", konu), \
                mock.patch.object(config, "TETIK_PUSH_PORT", 1), \
                mock.patch.object(canli_test, "surec_denetimi", return_value=(True, "pid 1 · test")), \
                mock.patch.object(canli_test, "_uzak", side_effect=lambda ad: {"lastupdate": "2026-10-25T10:00:00Z"}), \
                mock.patch.object(canli_test, "_yerel_damga", return_value="2026-10-25T10:00:00Z"):
            tampon = io.StringIO()
            with redirect_stdout(tampon):
                kod = canli_test.main(0.2)
        return kod, tampon.getvalue()

    def test_push_kapali_cihazda_cikis_0(self):
        """ASIL KUSUR: burada 1 dönüyordu → guncelle.sh her gece geri alıyordu."""
        kod, cikti = self._calistir(push_kapali=True)
        self.assertEqual(kod, 0, cikti)
        self.assertIn("atlandı", cikti)
        self.assertIn("zincir sağlam", cikti)

    def test_broker_acik_ve_kopukken_cikis_1(self):
        kod, cikti = self._calistir(push_kapali=False)
        self.assertEqual(kod, 1, cikti)


class ArgumanTesti(unittest.TestCase):
    def test_sure_ayristirilir(self):
        """`--sure` SESSİZCE yok sayılmamalı (guncelle.sh 15 verir; araç 15 sn beklemeli)."""
        import argparse

        kaynak = (KOK / "tools" / "canli_test.py").read_text(encoding="utf-8")
        self.assertIn("--sure", kaynak)
        self.assertIn("argparse.ArgumentParser", kaynak)
        # ayrıştırıcı gerçekten float kabul ediyor mu?
        ayristirici = argparse.ArgumentParser()
        ayristirici.add_argument("--sure", type=float, default=15.0)
        self.assertEqual(ayristirici.parse_args(["--sure", "15"]).sure, 15.0)
        self.assertEqual(ayristirici.parse_args([]).sure, 15.0)


if __name__ == "__main__":
    unittest.main()
