"""nobetci.isler() — adil kuyruk (en eski PR önce) regresyon testi.

Neden bu test var: 25 Ekim'de #83 (10:08) ve #84 (10:45) saatlerce `guvenlik/inceleme` durumu
OLMADAN bekledi, çünkü `isler()` GitHub'ın "yeniden eskiye" döndürdüğü listeyi olduğu gibi alıp
`limit` uyguluyor ve tek PR işleniyordu → her yeni PR kuyruğun başına geçiyordu. Bu testler
sıralamanın ve `limit`in sırasını kilitler: sıralama ÖNCE, dilimleme SONRA.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nobetci  # noqa: E402


def iso(dakika_once: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=dakika_once)).strftime("%Y-%m-%dT%H:%M:%SZ")


def pr(no: int, yas_dk: int, draft: bool = False, etiketler=(), sha: str = "") -> dict:
    return {
        "number": no,
        "draft": draft,
        "title": f"PR {no}",
        "created_at": iso(yas_dk),
        "updated_at": iso(yas_dk),
        "head": {"sha": sha or f"{no:040d}"},
        "labels": [{"name": e} for e in etiketler],
    }


class SahteGithub(nobetci.Github):
    """Yalnız `al()` taklidi: PR listesi + commit durumları (ağ ve dosya yok)."""

    def __init__(self, prlar: list[dict], durumlar: dict[str, dict[str, str]] | None = None):
        self.depo = "hakkisabah/yourkiosk"
        self.prlar = prlar
        self.durumlar = durumlar or {}
        self.cagrilar: list[str] = []

    def al(self, yol: str):
        self.cagrilar.append(yol)
        if yol.startswith("/repos/") and "/pulls?" in yol:
            return 200, self.prlar
        if "/status" in yol:
            sha = yol.split("/commits/")[1].split("/")[0]
            return 200, {"statuses": [{"context": k, "state": v}
                                      for k, v in self.durumlar.get(sha, {}).items()]}
        return 404, None


class AdilKuyrukTesti(unittest.TestCase):
    def test_en_eski_pr_once(self):
        # GitHub yeniden-eskiye döndürür: 88 (0 dk), 86 (30 dk), 84 (600 dk), 83 (640 dk)
        gh = SahteGithub([pr(88, 0), pr(86, 30), pr(84, 600), pr(83, 640)])
        sira = [i["pr"] for i in nobetci.isler(gh, "i5", 8)]
        self.assertEqual(sira, [83, 84, 86, 88])

    def test_limit_siralama_sonrasi_uygulanir(self):
        # limit=2 → EN ESKİ iki PR; yeni PR'lar kuyruğun başına geçemez
        gh = SahteGithub([pr(88, 0), pr(87, 5), pr(84, 600), pr(83, 640)])
        sira = [i["pr"] for i in nobetci.isler(gh, "i5", 2)]
        self.assertEqual(sira, [83, 84])

    def test_liste_tek_istekte_tumunu_ister(self):
        # per_page=limit olursa yeni PR'lar eskileri görünmez kılar → 100 sabit
        gh = SahteGithub([pr(83, 640)])
        nobetci.isler(gh, "i5", 1)
        self.assertIn("per_page=100", gh.cagrilar[0])

    def test_yas_dk_dogru_hesaplanir(self):
        kayit = nobetci.isler(SahteGithub([pr(83, 640)]), "i5", 8)[0]
        self.assertGreaterEqual(kayit["yas_dk"], 639)
        self.assertLessEqual(kayit["yas_dk"], 641)

    def test_taslak_atlanir(self):
        gh = SahteGithub([pr(90, 1, draft=True), pr(83, 640)])
        self.assertEqual([i["pr"] for i in nobetci.isler(gh, "i5", 8)], [83])

    def test_i5_onaylanmis_pr_istenmez(self):
        sha = f"{86:040d}"
        gh = SahteGithub([pr(86, 30)], {sha: {"guvenlik/inceleme": "success"}})
        self.assertEqual(nobetci.isler(gh, "i5", 8), [])

    def test_i5_ayni_sha_yeniden_incelenmez(self):
        # iş 1 kez yapıldı: "sorun" yazılmış + aynı sha. Yeniden incelemek boş oturum üretir;
        # sıra geliştiricide (yeni commit atınca sha değişir, PR tekrar girer).
        sha = f"{84:040d}"
        gh = SahteGithub([pr(84, 600, etiketler=["guvenlik/sorun"])],
                         {sha: {"guvenlik/inceleme": "failure"}})
        self.assertEqual(nobetci.isler(gh, "i5", 8), [])

    def test_i5_yeni_commit_gelince_yeniden_incelenir(self):
        # aynı PR numarası, YENİ sha (düzeltme geldi) → durum yok → yeniden incele
        eski, yeni = f"{84:040d}", f"{85:040d}"
        gh = SahteGithub([pr(84, 600, sha=yeni)], {eski: {"guvenlik/inceleme": "failure"}})
        self.assertEqual([i["pr"] for i in nobetci.isler(gh, "i5", 8)], [84])

    def test_i3_ayni_sha_ikinci_karar_yazmaz(self):
        # 25 Ekim: i3 aynı head'e (cc4e4b81) üç tur üst üste "düzeltme" yazdı.
        sha = f"{89:040d}"
        gh = SahteGithub([pr(89, 120, etiketler=["duzeltme/gerekli"])],
                         {sha: {"guvenlik/inceleme": "success", "guvenlik/karar": "failure"}})
        self.assertEqual(nobetci.isler(gh, "i3", 8), [])

    def test_i3_yalniz_i5_onayli_ve_kararsiz_prlari_alir(self):
        onayli_kararsiz, onayli_kararli, onaysiz = f"{83:040d}", f"{84:040d}", f"{88:040d}"
        gh = SahteGithub(
            [pr(88, 0), pr(84, 600, etiketler=["guvenlik/onay"]), pr(83, 640)],
            {
                onayli_kararsiz: {"guvenlik/inceleme": "success"},
                onayli_kararli: {"guvenlik/inceleme": "success", "guvenlik/karar": "success"},
                onaysiz: {},
            },
        )
        self.assertEqual([i["pr"] for i in nobetci.isler(gh, "i3", 8)], [83])

    def test_bos_liste(self):
        self.assertEqual(nobetci.isler(SahteGithub([]), "i5", 8), [])


class AclikTesti(unittest.TestCase):
    def test_yas_dk_bozuk_girdi_sifir_doner(self):
        self.assertEqual(nobetci.yas_dk(None), 0)
        self.assertEqual(nobetci.yas_dk("bozuk"), 0)


class GorevMetniTesti(unittest.TestCase):
    def test_sira_ve_yas_yazilir(self):
        metin = nobetci.gorev_metni("i5", Path("/depo"), [{"pr": 83, "sha": "a" * 40, "baslik": "x",
                                                          "inceleme": None, "karar": None,
                                                          "yas_dk": 640}])
        self.assertIn("#83", metin)
        self.assertIn("10 saattir açık", metin)
        self.assertIn("bu sırayı DEĞİŞTİRME", metin)


if __name__ == "__main__":
    unittest.main(verbosity=2)
