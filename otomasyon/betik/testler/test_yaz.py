"""yaz.py — PR yorum gövdesi testleri (ağ yok).

Neden: karar kapısı `kabul` (kapanış ölçütü) alanını ZORUNLU kılıyor; ama ölçüt PR yorumuna
basılmıyorsa geliştiriciye hiç ulaşmaz (26 Ekim i5 bulgusu). Aynı sınıf hata: kapı atlandığında
bunun yorumda görünmemesi.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import karar_dogrula as kd  # noqa: E402
import yaz  # noqa: E402


def karar(**degisiklik) -> dict:
    k = {
        "makine": "i5", "pr": 90, "sha": "a" * 40, "karar": "sorun", "onem": "orta",
        "ozet": "İki bulgu var.", "denetlenen": ["gömülü sır"],
        "bulgular": [{"dosya": "otomasyon/betik/nobetci.py", "satir": 241, "onem": "orta",
                      "aciklama": "gunluk adı çakışıyor",
                      "kabul": "gunluk_yolu ayrı alan olmalı ve test bunu kilitlemeli"}],
    }
    k.update(degisiklik)
    return k


def dogru_karar() -> dict:
    """Karar kapısından GERÇEKTEN geçen karar — kabul yolunu test edebilmek için.

    (Kanıt katmanı --kanit-yok ile kapalı olduğundan ağ kontrolü yapılmaz; şema/kapsam/tutarlılık
    denetimleri gerçek kapıdan geçer.)
    """
    return {
        "makine": "i5", "pr": 90, "sha": "a" * 40, "karar": "sorun", "onem": "orta",
        "ozet": "Dört yol fail-open bırakıyordu; üçü kapıyı, biri yayın yolunu etkiliyor.",
        "bulgular": [{"dosya": "otomasyon/betik/yaz.py", "satir": 231, "onem": "orta",
                      "aciklama": "yabancı-commit denetimi API hatasında boş liste dönüyor.",
                      "kabul": "200 dışı kodda birlestir() False döner ve testte kilitlidir."}],
        "denetlenen": list(kd.DENETIM_ALANLARI),
        "not": "Geliştiriciye: testler sahte istek kullanır.",
    }


class YorumGovdesiTesti(unittest.TestCase):
    def test_kapanis_olcutu_yorumda_gorunur(self):
        govde = yaz.yorum_govdesi(karar(), "failure")
        self.assertIn("Kapanış ölçütü", govde)
        self.assertIn("gunluk_yolu ayrı alan olmalı", govde)

    def test_kabul_yoksa_tire_basilir(self):
        b = karar()["bulgular"][0]
        b.pop("kabul")
        govde = yaz.yorum_govdesi(karar(bulgular=[b]), "failure")
        self.assertIn("| — |", govde)

    def test_i3_eksiklerinde_de_kapanis_olcutu(self):
        govde = yaz.yorum_govdesi(karar(makine="i3", eksikler=[
            {"dosya": "web/src/kiosk.ts", "satir": 12, "onem": "orta",
             "aciklama": "önbellek atlanmıyor", "kabul": "bildirim gelince zorla yenileme testi"}]), "failure")
        self.assertIn("Kapanış ölçütü", govde)
        self.assertIn("bildirim gelince zorla yenileme testi", govde)

    def test_kapi_atlandi_yorumda_uyari(self):
        govde = yaz.yorum_govdesi(karar(kapi_atlandi="kanıt katmanı çevrimdışı, elle doğrulandı"), "failure")
        self.assertIn("KARAR KAPISI ATLANDI", govde)
        self.assertIn("çevrimdışı", govde)

    def test_baslik_ve_durum_simgesi(self):
        self.assertIn("i5 — güvenlik incelemesi", yaz.yorum_govdesi(karar(), "success"))
        self.assertIn("i3 — karar", yaz.yorum_govdesi(karar(makine="i3"), "failure"))


class DurumMetniTesti(unittest.TestCase):
    def test_aciklama_140_karakteri_asmaz(self):
        durum, aciklama = yaz.durum_metni(karar(ozet="çok uzun " * 60))
        self.assertEqual(durum, "failure")
        self.assertLessEqual(len(aciklama), 140)

    def test_onay_durumu_success(self):
        self.assertEqual(yaz.durum_metni(karar(karar="onay", onem="dusuk", bulgular=[]))[0], "success")

    def test_aciklama_inceleme_surumu_damgali(self):
        """Karar (sha + inceleme sürümü) çiftine bağlı: damga AÇIKLAMANIN BAŞINDA olmalı.

        Damga sonda olsaydı 140 karakterlik kırpma onu kesebilir, karar "sürümsüz" kalır ve
        nöbetçi PR'ı bayat sayıp her turda yeniden incelerdi (sonsuz oturum).
        """
        _, aciklama = yaz.durum_metni(karar(ozet="çok uzun " * 60))
        self.assertTrue(aciklama.startswith("[v"), aciklama)
        self.assertRegex(aciklama, r"^\[v[0-9A-Za-z._-]{1,16}\] ")
        self.assertIn(f"[v{yaz.INCELEME_SURUMU}]", aciklama)

    def test_yaz_ve_nobetci_ayni_surumu_hesaplar(self):
        """İki betik farklı sürüm taşırsa yazılan damga hiçbir zaman güncel olmazdı (sonsuz tur)."""
        import nobetci  # aynı dizin, sys.path testte eklenmiş olmalı
        self.assertEqual(yaz.INCELEME_SURUMU, nobetci.INCELEME_SURUMU)
        self.assertEqual(yaz.inceleme_surumu(), nobetci.inceleme_surumu())


class _BiletDestekli(unittest.TestCase):
    """Ortak koşum: ortam anahtarı + operatör bileti senaryoları (alt süreç, ağ yok).

    `uid_taklit=True` uid denetimini FONKSİYON enjeksiyonuyla "root say" yapar
    (`yaz.bilet_sahibi_denetimi`). Bu bir ortam değişkeni DEĞİL: üretimdeki CLI hiçbir ortam
    değişkeniyle bu denetimi gevşetmez — root olmayan kullanıcı yalnız testte bu sarmalayıcıyla
    kabul yolunu koşturabilir (tasarım gerekçesi commit mesajında).
    """

    kok: Path
    log: Path
    yaz_py: Path
    karar_yolu: Path
    token: Path

    def bilet_olustur(self, *, yas_sn: float = 0.0, mod: int = 0o644) -> Path:
        import os as _os
        import time
        yol = self.kok / "kapi-atla.bilet"
        yol.write_text("", encoding="utf-8")
        _os.chmod(yol, mod)
        if yas_sn:
            eski = time.time() - yas_sn
            _os.utime(yol, (eski, eski))
        return yol

    def kimlik_olustur(self, icerik: str = "i5", *, mod: int = 0o644) -> Path:
        """Makine kimliği dosyası (üretimde /etc altında ROOT sahipli; testte geçici dizinde)."""
        import os as _os
        yol = self.kok / "makine-kimligi"
        yol.write_text(icerik, encoding="utf-8")
        _os.chmod(yol, mod)
        return yol

    def calistir(self, *ek: str, env_anahtar: bool = False, bilet=None, uid_taklit: bool = False,
                 dizin_gercek: bool = False, kimlik: str | None = "i5",
                 kimlik_dosyasi=None, kimlik_sahip_taklit: bool = True,
                 kapi_log_env=None):
        import os
        import subprocess
        ortam = {**os.environ, "HOME": str(self.kok)}
        for ad in ("YAZ_KAPI_ATLA_ONAY", "YAZ_KAPI_ATLA_BILET", "YAZ_KAPI_LOG"):
            ortam.pop(ad, None)
        if env_anahtar:
            ortam["YAZ_KAPI_ATLA_ONAY"] = "1"
        # 26 Ekim i5 bulgusu: bilet YOLU artık ortam değişkeniyle verilemez (ajan `/proc/1/stat`
        # gösterip iki faktörlü korumayı tek faktöre düşürüyordu). Test yolu MODÜL özniteliğiyle
        # enjekte eder; üretim CLI'ında böyle bir anahtar yoktur.
        #
        # 26 Ekim i5 bulgusu (2): kapı günlüğü yolu da `YAZ_KAPI_LOG` ile taşınabiliyordu →
        # ajan `/dev/null` verip izi siliyordu. Bu yüzden günlük yolu da MODÜL özniteliğiyle
        # enjekte edilir; `kapi_log_env` yalnız "ortam değişkeni YOK SAYILIR" testi içindir.
        onsoz = [
            # 26 Ekim i5 bulgusu (7): alt süreçle koşan testler kanıt katmanını da KAPATIR.
            # Önceki hâlde alt süreç gerçek api.github.com'a çıkıyordu (ağ yoksa yavaş/yanıltıcı
            # "head okunamadı (HTTP …)" satırları üretiyordu). `_api` sahte ile değiştirilir:
            # ağa hiç çıkılmaz, kanıt katmanı fail-closed davranışını AYNEN korur (HTTP 0).
            "import karar_dogrula as _kd; _kd._api = lambda *a, **k: (0, None)",
            f"import pathlib; yaz.KAPI_LOG = pathlib.Path({str(self.log)!r})",
        ]
        if kapi_log_env:
            ortam["YAZ_KAPI_LOG"] = str(kapi_log_env)
        # 26 Ekim i5 bulgusu (3): makine kimliği karar dosyasından değil ROOT sahipli dosyadan
        # okunur. Test kendi geçici kimlik dosyasını enjekte eder ve root sahiplik denetimini
        # yalnız bu koşum için "root say" yapar (bilet denetiminden AYRI fonksiyon).
        if kimlik is not None:
            yol = Path(kimlik_dosyasi) if kimlik_dosyasi is not None else self.kimlik_olustur(kimlik)
            onsoz.append(f"yaz.KIMLIK_VARSAYILAN = pathlib.Path({str(yol)!r})")
            if kimlik_sahip_taklit:
                onsoz.append("yaz.kimlik_sahibi_denetimi = lambda st: True")
                onsoz.append("yaz.kimlik_dizini_denetimi = lambda st: True")
        else:
            # "kimlik YOK" senaryosu: birincil dosya kadar YEDEK kaynak da (machine-id + eşleme)
            # kapalı olmalı — yoksa test makinenin gerçek /etc/machine-id'siyle kimlik bulur ve
            # senaryo sessizce başka bir şeyi ölçer (27 Ekim i5 bulgusu: 3 test kırmızıydı).
            onsoz.append(f"import pathlib; yaz.KIMLIK_VARSAYILAN = pathlib.Path({str(self.kok / 'kimlik-yok')!r})")
            onsoz.append(f"yaz.MAKINE_ID_YOLU = pathlib.Path({str(self.kok / 'machine-id-yok')!r})")
        if bilet is not None:
            onsoz.append(f"import pathlib; yaz.BILET_VARSAYILAN = pathlib.Path({str(bilet)!r})")
        if uid_taklit:
            onsoz.append("yaz.bilet_sahibi_denetimi = lambda st: True")
            if not dizin_gercek:
                onsoz.append("yaz.bilet_dizini_denetimi = lambda st: True")
        if onsoz:
            ortam["PYTHONPATH"] = str(self.yaz_py.parent)
            komut = [sys.executable, "-c",
                     "import sys, yaz; " + "; ".join(onsoz) + "; raise SystemExit(yaz.main())",
                     str(self.karar_yolu), "--kuru", "--token-dosya", str(self.token), *ek]
        else:
            komut = [sys.executable, str(self.yaz_py), str(self.karar_yolu), "--kuru",
                     "--token-dosya", str(self.token), *ek]
        return subprocess.run(komut, capture_output=True, text=True, timeout=120, env=ortam)


class KapiAtlamaTesti(_BiletDestekli):
    """--kapi-atla artık ajanın tek başına kullanabileceği bir anahtar DEĞİL (26 Ekim i5 bulgusu).

    Ret yolları gerçekten koşturulur (alt süreç + --kuru; ağa çıkılmaz, günlük geçici dosyaya).
    """

    def setUp(self):
        import json as _json
        import tempfile
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.karar_yolu = self.kok / "karar.json"
        self.karar_yolu.write_text(_json.dumps(karar(), ensure_ascii=False), encoding="utf-8")
        self.log = self.kok / "kapi-red.log"
        self.yaz = Path(__file__).resolve().parents[1] / "yaz.py"
        self.yaz_py = self.yaz
        self.token = self.kok / "yok.token"   # kanıt katmanı fail-closed → kapı geçmez

    def tearDown(self):
        self.dizin.cleanup()

    def _karar_yaz(self, bulgular):
        import json as _json
        k = karar(bulgular=bulgular)
        self.karar_yolu.write_text(_json.dumps(k, ensure_ascii=False), encoding="utf-8")

    def test_operator_anahtari_olmadan_atlama_reddedilir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı")
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("operatör ortam anahtarı yok", s.stderr)
        self.assertIn("reddedildi: operatör anahtarı yok", self.log.read_text(encoding="utf-8"))

    def test_yuksek_bulguda_atlama_imkansiz(self):
        self._karar_yaz([{"dosya": "a.py", "satir": 1, "onem": "yuksek", "aciklama": "x",
                          "kabul": "düzeltilince kapanır"}])
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True, bilet=self.bilet_olustur(), uid_taklit=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("atlanamaz", s.stderr)

    def test_kisa_gerekce_reddedilir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kısa", env_anahtar=True,
                          bilet=self.bilet_olustur(), uid_taklit=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("gerekce", s.stderr.replace("ç", "c").replace("Ç", "C"))

    def test_yalniz_ortam_anahtari_yetmez(self):
        """26 Ekim i5 bulgusu: anahtar tek başına yetiyordu; ajan onu kendi kabuğundan verebiliyor."""
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("operatör bileti", s.stderr)
        self.assertIn("bilet yok", s.stderr)
        self.assertIn("--kapi-atla reddedildi: operatör bileti geçersiz", self.log.read_text(encoding="utf-8"))

    def test_root_olmayan_bilet_reddedilir(self):
        """Bilet var ama root sahipli DEĞİL: ajanın kendi ürettiği dosya işe yaramaz."""
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True, bilet=self.bilet_olustur())
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("root sahipli değil", s.stderr)
        self.assertIn("root sahipli değil", self.log.read_text(encoding="utf-8"))

    def test_bilet_yolu_ortam_degiskeniyle_tasinamaz(self):
        """26 Ekim i5 bulgusu (uçtan uca): `YAZ_KAPI_ATLA_BILET=/proc/1/stat` bilet saymamalı.

        Eski kodda yol ortam değişkeninden geliyordu → root sahipli, dünya-okur `/proc/1/stat`
        denetimden geçip iki faktörlü korumayı tek faktöre (ortam anahtarı) düşürüyordu.
        """
        import os
        ortam_once = os.environ.get("YAZ_KAPI_ATLA_BILET")
        os.environ["YAZ_KAPI_ATLA_BILET"] = "/proc/1/stat"
        try:
            s = self.calistir("--kapi-atla", "--gerekce",
                              "kanıt katmanı çevrimdışı, elle doğrulandı", env_anahtar=True)
        finally:
            if ortam_once is None:
                os.environ.pop("YAZ_KAPI_ATLA_BILET", None)
            else:
                os.environ["YAZ_KAPI_ATLA_BILET"] = ortam_once
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("/run/yourkiosk-kapi-atla.bilet", s.stderr,
                      "ortam değişkeni yolu değiştirmemeli")
        self.assertIn("--kapi-atla reddedildi", self.log.read_text(encoding="utf-8"))

    def test_bayat_bilet_reddedilir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True, bilet=self.bilet_olustur(yas_sn=3600), uid_taklit=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("bayat", s.stderr)
        self.assertIn("TTL", self.log.read_text(encoding="utf-8"))

    def test_operator_anahtari_bilet_ve_gerekceyle_atlanir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True, bilet=self.bilet_olustur(), uid_taklit=True)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("KARAR KAPISI: ATLANDI", s.stdout)
        self.assertIn("KARAR KAPISI ATLANDI", s.stdout)          # PR yorumunda görünür
        self.assertIn('"olay": "ATLANDI"', self.log.read_text(encoding="utf-8"))


class KanitKatmaniTesti(_BiletDestekli):
    """`--kanit-yok` artık ajanın tek başına kapatabileceği bir anahtar DEĞİL (26 Ekim i5 bulgusu).

    Eskiden bayrak `kanit=not a.kanit_yok` ile dosya:satır kanıtı denetimini tamamen kapatıyordu ve
    ajanın kendi elindeydi. Artık --kapi-atla ile aynı desen: operatör anahtarı + operatör bileti,
    gerekçe, 'yüksek' bulgu yasağı ve her kullanımda kapi-red.log'a ATLANDI satırı.
    """

    def setUp(self):
        import json as _json
        import tempfile
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.karar_yolu = self.kok / "karar.json"
        self.log = self.kok / "kapi-red.log"
        self.yaz_py = Path(__file__).resolve().parents[1] / "yaz.py"
        self.token = self.kok / "yok.token"        # ağa çıkılmaz, kanıt katmanı zaten kapalı
        self._karar_yaz(dogru_karar())

    def tearDown(self):
        self.dizin.cleanup()

    def _karar_yaz(self, k: dict) -> None:
        import json as _json
        self.karar_yolu.write_text(_json.dumps(k, ensure_ascii=False), encoding="utf-8")

    def _log(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_operator_anahtari_olmadan_reddedilir(self):
        s = self.calistir("--kanit-yok", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı")
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("operatör ortam anahtarı yok", s.stderr)
        self.assertIn("--kanit-yok reddedildi: operatör anahtarı yok", self._log())

    def test_yuksek_bulguda_kullanilamaz(self):
        k = dogru_karar()
        k["bulgular"] = [{**k["bulgular"][0], "onem": "yuksek"}]
        self._karar_yaz(k)
        s = self.calistir("--kanit-yok", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True, bilet=self.bilet_olustur(), uid_taklit=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("kapatılamaz", s.stderr)
        self.assertIn("--kanit-yok reddedildi: yüksek bulgu", self._log())

    def test_gerekcesiz_reddedilir(self):
        s = self.calistir("--kanit-yok", "--gerekce", "kısa", env_anahtar=True,
                          bilet=self.bilet_olustur(), uid_taklit=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("gerekce", s.stderr.replace("ç", "c").replace("Ç", "C"))
        self.assertIn("--kanit-yok reddedildi: gerekçe yok", self._log())

    def test_yalniz_ortam_anahtari_yetmez(self):
        s = self.calistir("--kanit-yok", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("operatör bileti", s.stderr)
        self.assertIn("--kanit-yok reddedildi: operatör bileti geçersiz", self._log())

    def test_operator_anahtari_bilet_ve_gerekceyle_atlanir_ve_loglanir(self):
        s = self.calistir("--kanit-yok", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True, bilet=self.bilet_olustur(), uid_taklit=True)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("KANIT KATMANI: ATLANDI", s.stdout)
        self.assertIn("KANIT KATMANI ATLANDI", s.stdout)       # PR yorumunda görünür
        kayit = self._log()
        self.assertIn('"olay": "ATLANDI"', kayit)
        self.assertIn("kanıt katmanı ATLANDI", kayit)


class BiletDenetimiTesti(unittest.TestCase):
    """Operatör bileti birim testleri — uid denetimi FONKSİYON olarak enjekte edilir.

    Root olmayan kullanıcı gerçek bilet üretemez; bu yüzden "root say" davranışı ortam değişkeniyle
    DEĞİL, `bilet_denetle(..., sahip_denetimi=...)` ile verilir (üretim CLI'ında böyle bir anahtar yok).
    """

    def setUp(self):
        import tempfile
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)

    def tearDown(self):
        self.dizin.cleanup()

    def _bilet(self, mod: int = 0o644, yas_sn: float = 0.0) -> Path:
        import os
        import time
        yol = self.kok / "bilet"
        yol.write_text("", encoding="utf-8")
        os.chmod(yol, mod)
        if yas_sn:
            eski = time.time() - yas_sn
            os.utime(yol, (eski, eski))
        return yol

    def _denetle(self, yol, **ek):
        """Test enjeksiyonu: sahiplik ve DİZİN denetimleri fonksiyon olarak "güvenli" sayılır.

        Gerçek `/run` dizini root sahipli; geçici test dizini değil — bu yüzden testler bu iki
        denetimi enjekte eder. Ortam değişkeniyle gevşetilebilen bir anahtar YOKTUR.
        """
        return yaz.bilet_denetle(yol, sahip_denetimi=lambda st: True,
                                 dizin_denetimi=lambda st: True, **ek)

    def test_bilet_yoksa_reddedilir(self):
        gecerli, neden = yaz.bilet_denetle(self.kok / "yok.bilet")
        self.assertFalse(gecerli)
        self.assertIn("bilet yok", neden)

    def test_root_olmayan_bilet_reddedilir(self):
        # Enjeksiyon YOK: gerçek uid denetimi (test kullanıcısı root değil).
        gecerli, neden = yaz.bilet_denetle(self._bilet())
        self.assertFalse(gecerli)
        self.assertIn("root sahipli değil", neden)

    def test_dunya_okur_olmayan_bilet_reddedilir(self):
        gecerli, neden = self._denetle(self._bilet(mod=0o600))
        self.assertFalse(gecerli)
        self.assertIn("dünya-okur değil", neden)

    def test_dunya_yazilabilir_bilet_reddedilir(self):
        gecerli, neden = self._denetle(self._bilet(mod=0o666))
        self.assertFalse(gecerli)
        self.assertIn("yazılabilir", neden)

    def test_bayat_bilet_reddedilir(self):
        gecerli, neden = self._denetle(self._bilet(yas_sn=3600))
        self.assertFalse(gecerli)
        self.assertIn("bayat", neden)
        self.assertIn("TTL", neden)

    def test_gecerli_bilet_kabul_edilir(self):
        gecerli, neden = self._denetle(self._bilet())
        self.assertTrue(gecerli, neden)

    def test_sembolik_bag_bilet_sayilmaz(self):
        import os
        hedef = self._bilet()
        bag = self.kok / "bag"
        os.symlink(hedef, bag)
        gecerli, neden = self._denetle(bag)
        self.assertFalse(gecerli)
        self.assertIn("normal dosya değil", neden)

    # ── 26 Ekim i5 bulgusu: bilet yolu ortam değişkeniyle taşınamaz ───────────────────────────
    def test_sanal_dosya_sistemi_bilet_sayilmaz(self):
        """`/proc/1/stat` root sahipli + dünya-okur + 0644 görünür → eski denetimden GEÇİYORDU."""
        for yol in (Path("/proc/1/stat"), Path("/sys/kernel/mm/transparent_hugepage/enabled"),
                    Path("/dev/null")):
            gecerli, neden = yaz.bilet_denetle(yol, sahip_denetimi=lambda st: True,
                                               dizin_denetimi=lambda st: True)
            self.assertFalse(gecerli, str(yol))
            self.assertIn("sanal dosya sisteminde", neden, str(yol))

    def test_guvensiz_dizindeki_bilet_reddedilir(self):
        """Bilet dosyası sağlam olsa da üst dizini yazılabilirse aynı kullanıcı onu yeniden koyar."""
        gecerli, neden = yaz.bilet_denetle(self._bilet(), sahip_denetimi=lambda st: True)
        self.assertFalse(gecerli, "geçici dizin root sahipli değil → reddedilmeliydi")
        self.assertIn("bilet dizini güvenli değil", neden)

    def test_bilet_yolu_ortam_degiskeniyle_degismez(self):
        import os
        self.assertEqual(str(yaz.bilet_yolu()), "/run/yourkiosk-kapi-atla.bilet")
        os.environ["YAZ_KAPI_ATLA_BILET"] = "/proc/1/stat"
        try:
            self.assertEqual(str(yaz.bilet_yolu()), "/run/yourkiosk-kapi-atla.bilet",
                             "YAZ_KAPI_ATLA_BILET yolu DEĞİŞTİRMEMELİ (i5 bulgusu)")
            gecerli, neden = yaz.bilet_denetle()
            self.assertFalse(gecerli)
            self.assertIn("/run/yourkiosk-kapi-atla.bilet", neden)
        finally:
            os.environ.pop("YAZ_KAPI_ATLA_BILET", None)


class HeadOkunamazsaKapiTesti(unittest.TestCase):
    """26 Ekim i5 bulgusu: kanıt katmanı head'i okuyamazsa (429/403/0) sha tazeliği denetlenmiyordu.

    `_api` taklit edilir; `yaz.main()` gerçek kapıdan geçirilir ve ret kapi-red.log'a yazılır.
    """

    def test_head_429_karari_reddeder_ve_loglar(self):
        import json
        import os
        import tempfile
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as dizin:
            kok = Path(dizin)
            karar_yolu = kok / "karar.json"
            karar_yolu.write_text(json.dumps(dogru_karar(), ensure_ascii=False), encoding="utf-8")
            token = kok / "t.token"
            token.write_text("x" * 40, encoding="utf-8")
            log = kok / "kapi-red.log"
            kimlik = kok / "makine-kimligi"
            kimlik.write_text("i5", encoding="utf-8")

            def api(yol, _token, _depo):
                if "/files" in yol:
                    return 429, None
                if yol.startswith("/pulls/"):
                    return 429, None
                raise AssertionError(f"beklenmeyen istek: {yol}")

            argv = [str(Path(__file__).resolve().parents[1] / "yaz.py"), str(karar_yolu),
                    "--token-dosya", str(token)]
            with mock.patch.object(kd, "_api", api), \
                 mock.patch.object(yaz, "KAPI_LOG", log), \
                 mock.patch.object(yaz, "KIMLIK_VARSAYILAN", kimlik), \
                 mock.patch.object(yaz, "kimlik_sahibi_denetimi", lambda st: True), \
                 mock.patch.object(yaz, "kimlik_dizini_denetimi", lambda st: True), \
                 mock.patch.object(sys, "argv", argv), \
                 mock.patch.dict(os.environ, {"YAZ_KAPI_LOG": str(log)}):
                kod = yaz.main()
            self.assertEqual(kod, 5)
            kayit = log.read_text(encoding="utf-8")
            self.assertIn("head okunamadı (HTTP 429)", kayit)
            self.assertIn("kanıt tazeliği doğrulanamadı", kayit)


class YabanciCommitDenetimiTesti(unittest.TestCase):
    """Birleştirme kapısı fail-closed: API 200 dışı kod → birleştirme YOK, gerekçe 'denetlenemedi'.

    26 Ekim i5 bulgusu: `_yabanci_commitler` 429/403/0 dönen çağrıda boş liste dönüyordu, yani
    yabancı-commit denetimi sessizce atlanıyordu. İstekler taklit edilir (gerçek ağ yok).
    """

    SHA = "b" * 40
    DEPO = "hakkisabah/yourkiosk"

    def setUp(self):
        self._gercek = yaz.istek
        self.addCleanup(lambda: setattr(yaz, "istek", self._gercek))

    def _sahte_istek(self, acik_kod: int = 200, commit_kod: int = 200, yabanci: bool = False,
                     kontroller=None):
        def sahte(yol, token, yontem="GET", govde=None):
            if "/pulls?state=open" in yol:
                if acik_kod != 200:
                    return acik_kod, {"message": f"HTTP {acik_kod}"}
                return 200, ([{"number": 88, "head": {"sha": "c" * 40}}] if yabanci else [])
            if yol.endswith("/commits?per_page=100"):
                if commit_kod != 200:
                    return commit_kod, {"message": f"HTTP {commit_kod}"}
                return 200, [{"sha": "c" * 40}] if yabanci else [{"sha": self.SHA}]
            if yol == f"/repos/{self.DEPO}/pulls/90":
                return 200, {"number": 90, "state": "open", "draft": False, "title": "t",
                             "head": {"sha": self.SHA}, "labels": [], "mergeable_state": "clean"}
            if yol.endswith("/status"):
                return 200, {"statuses": kontroller if kontroller is not None else [
                    {"context": "guvenlik/inceleme", "state": "success"},
                    {"context": "guvenlik/karar", "state": "success"},
                ]}
            raise AssertionError(f"beklenmeyen istek: {yol}")
        yaz.istek = sahte

    def _birlestir(self):
        return yaz.birlestir(self.DEPO, "sahte-token", 90, self.SHA, kuru=True)

    def test_acik_pr_listesi_429_denetim_kapanir(self):
        self._sahte_istek(acik_kod=429)
        uygun, mesaj = self._birlestir()
        self.assertFalse(uygun, mesaj)
        self.assertIn("denetlenemedi (HTTP 429)", mesaj)
        self.assertIn("yabancı commit denetimi yapılamadı", mesaj)

    def test_pr_commit_listesi_403_denetim_kapanir(self):
        self._sahte_istek(commit_kod=403, yabanci=True)
        uygun, mesaj = self._birlestir()
        self.assertFalse(uygun, mesaj)
        self.assertIn("denetlenemedi (HTTP 403)", mesaj)

    def test_ag_hatasi_denetim_kapanir(self):
        self._sahte_istek(acik_kod=0)
        uygun, mesaj = self._birlestir()
        self.assertFalse(uygun, mesaj)
        self.assertIn("denetlenemedi (HTTP 0)", mesaj)

    def test_temiz_dal_birlestirilebilir(self):
        self._sahte_istek(yabanci=False)
        uygun, mesaj = self._birlestir()
        self.assertTrue(uygun, mesaj)

    def test_yabanci_commit_yine_engellenir(self):
        self._sahte_istek(yabanci=True)
        uygun, mesaj = self._birlestir()
        self.assertFalse(uygun, mesaj)
        self.assertIn("#88", mesaj)

    # ── çift onay VARSAYILAN (26 Ekim i5 bulgusu) ──────────────────────────────────────────
    def test_kontroller_yalniz_karar_iceriyorken_birlestirme_yok(self):
        """İkinci kapı varsayılan olarak ARANIR: yalnız `guvenlik/karar` varsa birleştirme yok."""
        self._sahte_istek(kontroller=[{"context": "guvenlik/karar", "state": "success"}])
        uygun, mesaj = self._birlestir()
        self.assertFalse(uygun, mesaj)
        self.assertIn("çift onay tamam değil", mesaj)
        self.assertIn("guvenlik/inceleme", mesaj)

    def test_kontroller_yalniz_inceleme_iceriyorken_birlestirme_yok(self):
        self._sahte_istek(kontroller=[{"context": "guvenlik/inceleme", "state": "success"}])
        uygun, mesaj = self._birlestir()
        self.assertFalse(uygun, mesaj)
        self.assertIn("guvenlik/karar", mesaj)

    def test_cift_onay_varsayilan_acik(self):
        """İmza: cift_onay parametresinin VARSAYILANI True (çağıran unutsa da ikinci kapı aranır)."""
        import inspect
        self.assertIs(inspect.signature(yaz.birlestir).parameters["cift_onay"].default, True)

    def test_tek_onay_gerekcesiz_reddedilir(self):
        """--tek-onay açık bir istisnadır: yazılı gerekçe olmadan çalışmaz (ağa hiç çıkılmaz)."""
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d)
            karar_yolu = kok / "karar.json"
            karar_yolu.write_text(json.dumps(karar(), ensure_ascii=False), encoding="utf-8")
            s = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] / "yaz.py"),
                 str(karar_yolu), "--kuru", "--birlestir", "--tek-onay"],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(s.returncode, 2, s.stdout + s.stderr)
            self.assertIn("--tek-onay için --gerekce", s.stderr)


class YuksekBulguKapisiTesti(unittest.TestCase):
    """27 Ekim i5 bulgusu: `--kanit-yok`/`--kapi-atla` yalnız `bulgular` alanını tarıyordu.

    i3 kararlarında aynı liste `eksikler` adıyla geliyor → 'yüksek' önemde bir bulgu varken iki
    kaçış yolu da sessizce geçebiliyordu. Kapı artık üç alanı birlikte tarar.
    """

    def test_bulgular_alaninda_yuksek(self):
        karar = {"bulgular": [{"onem": "yuksek", "aciklama": "x"}]}
        self.assertEqual(len(yaz._yuksek_bulgular(karar)), 1)

    def test_eksikler_alaninda_yuksek(self):
        karar = {"eksikler": [{"onem": "yüksek", "aciklama": "x"}]}
        self.assertEqual(len(yaz._yuksek_bulgular(karar)), 1)

    def test_sorunlar_alaninda_kritik(self):
        karar = {"sorunlar": [{"onem": "kritik", "aciklama": "x"}]}
        self.assertEqual(len(yaz._yuksek_bulgular(karar)), 1)

    def test_dusuk_ve_orta_sayilmaz(self):
        karar = {"bulgular": [{"onem": "dusuk"}, {"onem": "orta"}],
                 "eksikler": [{"onem": "orta"}]}
        self.assertEqual(yaz._yuksek_bulgular(karar), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class MakineKimligiTesti(_BiletDestekli):
    """26 Ekim i5 bulgusu: kimlik karar dosyasının KENDİ `makine` alanından geliyordu.

    i5 oturumu karar dosyasına "makine": "i3" yazıp `guvenlik/inceleme` + `guvenlik/karar`
    kontrollerini tek başına geçirebiliyordu. Artık kimlik operatörün kurduğu ROOT sahipli
    dosyadan okunur; beyan uyuşmazsa yazım reddedilir (çıkış 5).
    """

    def setUp(self):
        import json as _json
        import tempfile
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.karar_yolu = self.kok / "karar.json"
        self.karar_yolu.write_text(_json.dumps(dogru_karar(), ensure_ascii=False), encoding="utf-8")
        self.log = self.kok / "kapi-red.log"
        self.yaz = Path(__file__).resolve().parents[1] / "yaz.py"
        self.yaz_py = self.yaz
        self.token = self.kok / "yok.token"

    def tearDown(self):
        self.dizin.cleanup()

    def test_kimlik_dosyasi_yoksa_yazim_reddedilir(self):
        s = self.calistir(kimlik=None)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("MAKİNE KİMLİĞİ REDDEDİLDİ", s.stderr)
        # Hem birincil dosya (enjekte edilen yol) hem yedek kaynak (machine-id) kapalı olmalı
        self.assertIn("kimlik-yok", s.stderr)
        self.assertIn("machine-id yok", s.stderr)
        self.assertIn("makine kimliği geçersiz", self.log.read_text(encoding="utf-8"))

    def test_beyan_ile_kimlik_uyusmazsa_reddedilir(self):
        """i5 oturumu 'i3' yazarsa: karar dosyası ile makine kimliği çelişir → çıkış 5."""
        import json as _json
        k = dogru_karar()
        k["makine"] = "i3"
        k["eksikler"] = k.pop("bulgular")
        self.karar_yolu.write_text(_json.dumps(k, ensure_ascii=False), encoding="utf-8")
        s = self.calistir(kimlik="i5")
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("KİMLİK UYUŞMAZLIĞI", s.stderr)
        self.assertIn("kimlik uyuşmazlığı", self.log.read_text(encoding="utf-8"))

    def test_i5_kimligiyle_birlestirme_reddedilir(self):
        """Birleştirme karar makinesine (i3) aittir; i5 kimliği --birlestir kullanamaz."""
        s = self.calistir("--birlestir", kimlik="i5")
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("--birlestir REDDEDİLDİ", s.stderr)
        self.assertIn("--birlestir reddedildi: kimlik 'i5'", self.log.read_text(encoding="utf-8"))

    def test_root_sahipli_olmayan_kimlik_reddedilir(self):
        """Ajanın kendi yazdığı kimlik dosyası (uid ≠ 0) kabul edilmez."""
        s = self.calistir(kimlik="i5", kimlik_sahip_taklit=False)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("root sahipli değil", s.stderr)

    def test_tek_onay_operator_izi_ister(self):
        """27 Ekim i5 bulgusu (orta): `--tek-onay` ikinci zorunlu kontrolü tamamen kaldırıyordu.

        Artık `--kapi-atla` ile AYNI kapı: operatör anahtarı + bilet yoksa çıkış 5, birleştirme
        isteği hiç atılmaz.
        """
        self.assertNotIn("YAZ_KAPI_ATLA_ONAY", os.environ)
        # --birlestir yalnız KARAR makinesinde (i3) anlamlı → karar ve kimlik i3
        k = dogru_karar()
        k["makine"] = "i3"
        k["eksikler"] = k.pop("bulgular")
        self.karar_yolu.write_text(json.dumps(k), encoding="utf-8")
        s = self.calistir("--birlestir", "--tek-onay", "--gerekce",
                          "iki kapi tek makinede birlesti, operator onayi var", kimlik="i3")
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("--tek-onay REDDEDİLDİ", s.stderr)
        self.assertIn("--tek-onay reddedildi", self.log.read_text(encoding="utf-8"))

    def test_kimlik_dosyasi_ortam_degiskeniyle_tasinamaz(self):
        """Üretimde kimlik yolunu taşıyan bir ortam anahtarı YOKTUR (bilet dersi)."""
        import os
        import subprocess
        ortam = {**os.environ, "HOME": str(self.kok),
                 "YAZ_MAKINE_KIMLIGI": str(self.kimlik_olustur("i3")),
                 "YAZ_KIMLIK_DOSYASI": str(self.kimlik_olustur("i3"))}
        s = subprocess.run([sys.executable, str(self.yaz), str(self.karar_yolu), "--kuru",
                            "--token-dosya", str(self.token)],
                           capture_output=True, text=True, timeout=120, env=ortam)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("MAKİNE KİMLİĞİ REDDEDİLDİ", s.stderr)

    def test_kapi_log_yolu_ortam_degiskeniyle_tasinamaz(self):
        """`YAZ_KAPI_LOG=/dev/null` kapı izini silememeli: kayıt VARSAYILAN dosyaya yazılır."""
        s = self.calistir(kimlik=None, kapi_log_env="/dev/null")
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("makine kimliği geçersiz", self.log.read_text(encoding="utf-8"))

    def test_kimlik_cozucu_islevi_dogru_icerik_okur(self):
        yol = self.kimlik_olustur("I3\n")
        kimlik, neden = yaz.makine_kimligi_denetle(yol, sahip_denetimi=lambda st: True,
                                                   dizin_denetimi=lambda st: True)
        self.assertEqual((kimlik, neden), ("i3", ""))
        bozuk = self.kok / "bozuk-kimlik"
        bozuk.write_text("i9", encoding="utf-8")
        kimlik, neden = yaz.makine_kimligi_denetle(bozuk, sahip_denetimi=lambda st: True,
                                                   dizin_denetimi=lambda st: True)
        self.assertEqual(kimlik, "")
        self.assertIn("tanınmıyor", neden)
