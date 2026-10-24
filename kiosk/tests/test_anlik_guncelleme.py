"""ANLIK GÜNCELLEME ZİNCİRİ — regresyon testleri.

GERÇEK HATA (kullanıcı): "her iki uygulamayı da kapatıp açmadığım sürece değişiklikler geçerli
olmuyor". İki ayrı kusur vardı:

 1. Yoklama aralığı maliyet için 1800 sn'ye çıkarıldı; MQTT push yalnız `tetikle.json` YAZIYORDU,
    okuyan zamanlayıcı 30 dakika sonra çalışıyordu → push sessizce ölüydü.
    Çözüm: `tetik_izle` (yerel mtime izleyici, AĞ YOK) 2 sn'de bir bakar.

 2. `secili_tetik` SABİT öncelik veriyordu (uzak > yerel). `durum.json` her panel kaydında
    yazıldığı için uzak tetik hep doluydu ve MQTT'nin DAHA YENİ tetiği hiç uygulanmıyordu.
    Çözüm: iki tetikten **daha yeni** olanı seç.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import durum as durum_modulu  # noqa: E402


class SeciliTetikTesti(unittest.TestCase):
    def test_yalniz_uzak(self):
        belge = {"tetik": {"zaman": "2026-10-24T10:00:00Z"}}
        self.assertEqual(durum_modulu.secili_tetik(belge, lambda: None)["zaman"], "2026-10-24T10:00:00Z")

    def test_yalniz_yerel(self):
        self.assertEqual(
            durum_modulu.secili_tetik({"lastupdate": "D"}, lambda: {"zaman": "2026-10-24T11:00:00Z"})["zaman"],
            "2026-10-24T11:00:00Z",
        )

    def test_yerel_daha_yeniyse_yerel_secillir(self):
        """ASIL KUSUR: uzak sabit öncelikliydi → MQTT tetiği hiç uygulanmıyordu."""
        belge = {"tetik": {"zaman": "2026-10-24T10:00:00Z"}}
        yerel = {"zaman": "2026-10-24T10:00:05Z"}  # 5 sn daha yeni
        self.assertEqual(durum_modulu.secili_tetik(belge, lambda: yerel)["zaman"], "2026-10-24T10:00:05Z")

    def test_uzak_daha_yeniyse_uzak_secillir(self):
        belge = {"tetik": {"zaman": "2026-10-24T10:00:09Z"}}
        yerel = {"zaman": "2026-10-24T10:00:05Z"}
        self.assertEqual(durum_modulu.secili_tetik(belge, lambda: yerel)["zaman"], "2026-10-24T10:00:09Z")

    def test_yerel_okuma_hatasi_gostermeyi_durdurmaz(self):
        def patlat():
            raise OSError("disk")

        self.assertEqual(
            durum_modulu.secili_tetik({"tetik": {"zaman": "U"}}, patlat)["zaman"], "U"
        )


class TetikIzleTesti(unittest.TestCase):
    """`PharmacyApp.tetik_izle`: yerel dosya değişince `tetik_kontrol` çağrılmalı."""

    def _nesne(self, gecici: Path):
        import pharmacy_app

        nesne = types.SimpleNamespace()
        nesne._son_yerel_imza = ""
        nesne._kok = gecici
        nesne.cagrilar = 0

        def _yerel_imza(self):
            parcalar = []
            for ad in ("tetikle.json", "lastupdate.json", "durum.json"):
                try:
                    durum = (self._kok / ad).stat()
                    parcalar.append(f"{ad}:{durum.st_mtime_ns}:{durum.st_size}")
                except OSError:
                    parcalar.append(f"{ad}:-")
            return "|".join(parcalar)

        def tetik_kontrol(self):
            self.cagrilar += 1

        nesne._yerel_imza = types.MethodType(_yerel_imza, nesne)
        nesne.tetik_izle = types.MethodType(pharmacy_app.PharmacyApp.tetik_izle, nesne)
        nesne.tetik_kontrol = types.MethodType(tetik_kontrol, nesne)
        return nesne

    def test_ilk_turda_tetiklenmez_sonra_degisimde_tetiklenir(self):
        import tempfile

        with tempfile.TemporaryDirectory() as dizin:
            kok = Path(dizin)
            nesne = self._nesne(kok)

            nesne.tetik_izle()  # ilk tur: yalnız imza kaydı
            self.assertEqual(nesne.cagrilar, 0, "ilk turda yenileme yapılmamalı")

            (kok / "tetikle.json").write_text('{"zaman":"2026-10-24T10:00:00Z"}', encoding="utf-8")
            nesne.tetik_izle()  # değişim → yenile
            self.assertEqual(nesne.cagrilar, 1, "yerel tetik değişince yenilenmeli")

            nesne.tetik_izle()  # değişim yok → tekrar tetiklenmez
            self.assertEqual(nesne.cagrilar, 1)

            (kok / "tetikle.json").write_text('{"zaman":"2026-10-24T10:00:01Z"}', encoding="utf-8")
            nesne.tetik_izle()
            self.assertEqual(nesne.cagrilar, 2)

    def test_imza_okunamazsa_cokmez(self):
        nesne = self._nesne(Path("/olmayan/klasor"))
        nesne.tetik_izle()  # istisna sızdırmamalı
        self.assertEqual(nesne.cagrilar, 0)


class UzakYoklamaTesti(unittest.TestCase):
    def test_mqtt_bagli_degilse_uzak_yoklama_gerekli(self):
        """Bağlantı kopmuşsa push mesaj getirmez → uzun yoklama UZAKTAN çekmeli."""
        from core import tarayici

        # veri UZAKTAN okunuyor (kaynak=https) ama MQTT kopuk → uzaktan çekmeli
        sahte = types.SimpleNamespace(KAYNAK="https", WEB_VERI_MODU="https")
        with mock.patch.object(tarayici, "config", sahte), mock.patch(
            "core.push.acik", return_value=True
        ), mock.patch("core.push.durum", return_value={"bagli": False, "denendi": True}):
            self.assertTrue(tarayici.uzak_yoklama_gerekli())

    def test_mqtt_bagliysa_uzak_yoklama_gerekmez(self):
        from core import tarayici

        sahte = types.SimpleNamespace(KAYNAK="https", WEB_VERI_MODU="https")
        with mock.patch.object(tarayici, "config", sahte), mock.patch(
            "core.push.acik", return_value=True
        ), mock.patch("core.push.durum", return_value={"bagli": True, "denendi": True}):
            self.assertFalse(tarayici.uzak_yoklama_gerekli())


if __name__ == "__main__":
    unittest.main()
