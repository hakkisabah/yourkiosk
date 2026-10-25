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


class DurumYoluTetikTesti(unittest.TestCase):
    """`durum.json` YOLU: yalnız `tetikle.json` yazan akışlar (panel "Bildir") cihazda görünmeli.

    GERÇEK HATA (kullanıcı): tarayıcı tarafına geçerken Qt kiosk "Bildir"e tepki vermiyordu.
    Sebep: `durum.json` varsa `tetikle.json` HİÇ indirilmiyordu; panelin "Bildir" düğmesi ise
    yalnız `tetikle.json` yazıyor → tetik cihaza hiç ulaşmıyordu.
    """

    def _nesne(self, tetik: dict | None, *, getir_sonuc: bool = True):
        import pharmacy_app

        nesne = types.SimpleNamespace()
        nesne._son_komut_isareti = ""
        nesne._son_tetik = ""
        nesne._durum_tur = 0
        nesne.indirilen = 0
        nesne.yuklemeler = []

        def cihaz_kimligi():
            return "98273648723468273"

        def load_data(zorla=False):
            nesne.yuklemeler.append(bool(zorla))

        nesne.cihaz_kimligi = cihaz_kimligi
        nesne.load_data = load_data
        nesne._durum_uygula = types.MethodType(pharmacy_app.PharmacyApp._durum_uygula, nesne)
        # komut çapraz kontrolü ayrı testte ölçülür; burada yan etkisiz
        nesne.komut_kontrolleri = 0

        def _komut_capraz_kontrol(self):
            self.komut_kontrolleri += 1

        nesne._komut_capraz_kontrol = types.MethodType(_komut_capraz_kontrol, nesne)

        def _getir():
            nesne.indirilen += 1
            return getir_sonuc

        return nesne, _getir, tetik

    def test_durum_tetigi_bossa_tetikle_json_indirilir_ve_uygulanir(self):
        belge = {"zaman": "2026-10-24T10:00:00Z", "lastupdate": "2026-10-24 10:00:00", "tetik": {}}
        tetik = {"zaman": "2026-10-24T10:10:00Z", "ilceId": "", "bolgeId": "", "aciklama": "Panelden bildirildi"}
        nesne, getir, _ = self._nesne(tetik)
        konum = types.SimpleNamespace(ilce_id="I1", bolge_id="B1")
        nesne.data_handler = types.SimpleNamespace(lastupdate="2026-10-24 10:00:00", konum=konum)

        with mock.patch("core.durum.getir", return_value=belge), mock.patch(
            "core.veri_kaynagi.lastupdate_taze", return_value="2026-10-24 10:00:00"
        ), mock.patch("core.tetik.getir", side_effect=getir), mock.patch(
            "core.tetik.oku", return_value=tetik
        ), mock.patch("core.tetik.otomatik_acik", return_value=True), mock.patch(
            "core.tetik.uygulanmali", return_value=True
        ), mock.patch("core.push.durum", return_value={"bagli": False}):
            nesne._durum_uygula(belge)

        self.assertEqual(nesne.indirilen, 1, "ilk turda tetikle.json sunucudan indirilmeli")
        self.assertEqual(nesne.yuklemeler, [True], "indirilen tetik uygulanıp ekran ZORLA yenilenmeli")

    def test_durum_tetigi_varsa_da_indirme_hata_verirse_cokmez(self):
        belge = {"lastupdate": "2026-10-24 10:00:00", "tetik": {"zaman": "2026-10-24T10:09:00Z"}}
        nesne, _, _ = self._nesne(None, getir_sonuc=False)
        konum = types.SimpleNamespace(ilce_id="I1", bolge_id="B1")
        nesne.data_handler = types.SimpleNamespace(lastupdate="2026-10-24 10:00:00", konum=konum)

        with mock.patch("core.durum.getir", return_value=belge), mock.patch(
            "core.veri_kaynagi.lastupdate_taze", return_value="2026-10-24 10:00:00"
        ), mock.patch("core.tetik.getir", side_effect=OSError("ağ")), mock.patch(
            "core.tetik.oku", return_value=None
        ), mock.patch("core.tetik.otomatik_acik", return_value=True), mock.patch(
            "core.push.durum", return_value={"bagli": False}
        ):
            nesne._durum_uygula(belge)  # istisna SIZMAMALI

        self.assertTrue(nesne.yuklemeler, "durum.json tetiği yine de uygulanmalı")


class KomutCaprazKontrolTesti(unittest.TestCase):
    """`durum.json` komut İŞARETİ taşımıyorsa `komut.json` yine de indirilmeli.

    `tools/komut_gonder.py` komutu doğrudan S3'e yazıyor; `durum.json`a işaret koymuyor.
    Eski kod işaret yoksa komut dosyasını hiç indirmiyordu → uzaktan komut sessizce ölüydü.
    """

    def test_isaret_yoksa_komut_indirilir_ve_uygulanir(self):
        import pharmacy_app

        nesne = types.SimpleNamespace()
        nesne.indirilen = 0
        nesne.tazelenen = 0

        def cihaz_kimligi():
            return "98273648723468273"

        def update_display():
            nesne.tazelenen += 1

        nesne.cihaz_kimligi = cihaz_kimligi
        nesne.update_display = update_display
        nesne._komut_capraz_kontrol = types.MethodType(
            pharmacy_app.PharmacyApp._komut_capraz_kontrol, nesne
        )

        sonuc = types.SimpleNamespace(uygulama_ici=True)

        def _getir():
            nesne.indirilen += 1
            return True

        with mock.patch("core.komut.getir", side_effect=_getir), mock.patch(
            "core.komut.kontrol", return_value=(object(), sonuc)
        ), mock.patch("core.komut.sonuc_metni", return_value="ekrani-yenile → uygulama içi"):
            nesne._komut_capraz_kontrol()

        self.assertEqual(nesne.indirilen, 1, "komut.json sunucudan indirilmeli")
        self.assertEqual(nesne.tazelenen, 1, "uygulama içi komut ekranı tazelemeli")

    def test_indirme_hatasi_turu_oldurmez(self):
        import pharmacy_app

        nesne = types.SimpleNamespace(cihaz_kimligi=lambda: "X")
        nesne._komut_capraz_kontrol = types.MethodType(
            pharmacy_app.PharmacyApp._komut_capraz_kontrol, nesne
        )
        with mock.patch("core.komut.getir", side_effect=OSError("ağ")):
            nesne._komut_capraz_kontrol()  # istisna SIZMAMALI


if __name__ == "__main__":
    unittest.main()
