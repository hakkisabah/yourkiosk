"""yaz.py — PR yorum gövdesi testleri (ağ yok).

Neden: karar kapısı `kabul` (kapanış ölçütü) alanını ZORUNLU kılıyor; ama ölçüt PR yorumuna
basılmıyorsa geliştiriciye hiç ulaşmaz (26 Ekim i5 bulgusu). Aynı sınıf hata: kapı atlandığında
bunun yorumda görünmemesi.
"""

from __future__ import annotations

import sys
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


class KapiAtlamaTesti(unittest.TestCase):
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
        self.token = self.kok / "yok.token"   # kanıt katmanı fail-closed → kapı geçmez

    def tearDown(self):
        self.dizin.cleanup()

    def calistir(self, *ek: str, env_anahtar: bool = False):
        import os
        import subprocess
        ortam = {**os.environ, "YAZ_KAPI_LOG": str(self.log), "HOME": str(self.kok)}
        ortam.pop("YAZ_KAPI_ATLA_ONAY", None)
        if env_anahtar:
            ortam["YAZ_KAPI_ATLA_ONAY"] = "1"
        return subprocess.run(
            [sys.executable, str(self.yaz), str(self.karar_yolu), "--kuru",
             "--token-dosya", str(self.token), *ek],
            capture_output=True, text=True, timeout=120, env=ortam,
        )

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
                          env_anahtar=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("atlanamaz", s.stderr)

    def test_kisa_gerekce_reddedilir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kısa", env_anahtar=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("gerekce", s.stderr.replace("ç", "c").replace("Ç", "C"))

    def test_operator_anahtari_ve_gerekceyle_atlanir(self):
        s = self.calistir("--kapi-atla", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("KARAR KAPISI: ATLANDI", s.stdout)
        self.assertIn("KARAR KAPISI ATLANDI", s.stdout)          # PR yorumunda görünür
        self.assertIn('"olay": "ATLANDI"', self.log.read_text(encoding="utf-8"))


class KanitKatmaniTesti(unittest.TestCase):
    """`--kanit-yok` artık ajanın tek başına kapatabileceği bir anahtar DEĞİL (26 Ekim i5 bulgusu).

    Eskiden bayrak `kanit=not a.kanit_yok` ile dosya:satır kanıtı denetimini tamamen kapatıyordu ve
    ajanın kendi elindeydi. Artık --kapi-atla ile aynı desen: operatör anahtarı, gerekçe, 'yüksek'
    bulgu yasağı ve her kullanımda kapi-red.log'a ATLANDI satırı. Üç ret yolu + kabul yolu koşturulur.
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

    def calistir(self, *ek: str, env_anahtar: bool = False):
        import os
        import subprocess
        ortam = {**os.environ, "YAZ_KAPI_LOG": str(self.log), "HOME": str(self.kok)}
        ortam.pop("YAZ_KAPI_ATLA_ONAY", None)
        if env_anahtar:
            ortam["YAZ_KAPI_ATLA_ONAY"] = "1"
        return subprocess.run(
            [sys.executable, str(self.yaz_py), str(self.karar_yolu), "--kuru",
             "--token-dosya", str(self.token), *ek],
            capture_output=True, text=True, timeout=120, env=ortam,
        )

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
                          env_anahtar=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("kapatılamaz", s.stderr)
        self.assertIn("--kanit-yok reddedildi: yüksek bulgu", self._log())

    def test_gerekcesiz_reddedilir(self):
        s = self.calistir("--kanit-yok", "--gerekce", "kısa", env_anahtar=True)
        self.assertEqual(s.returncode, 5, s.stdout + s.stderr)
        self.assertIn("gerekce", s.stderr.replace("ç", "c").replace("Ç", "C"))
        self.assertIn("--kanit-yok reddedildi: gerekçe yok", self._log())

    def test_operator_anahtari_ve_gerekceyle_atlanir_ve_loglanir(self):
        s = self.calistir("--kanit-yok", "--gerekce", "kanıt katmanı çevrimdışı, elle doğrulandı",
                          env_anahtar=True)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("KANIT KATMANI: ATLANDI", s.stdout)
        self.assertIn("KANIT KATMANI ATLANDI", s.stdout)       # PR yorumunda görünür
        kayit = self._log()
        self.assertIn('"olay": "ATLANDI"', kayit)
        self.assertIn("kanıt katmanı ATLANDI", kayit)


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

    def _sahte_istek(self, acik_kod: int = 200, commit_kod: int = 200, yabanci: bool = False):
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
                return 200, {"statuses": [{"context": "guvenlik/inceleme", "state": "success"}]}
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
