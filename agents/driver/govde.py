"""PR gövdesi üretimi ve kapısı — gövde zorunlu, eksikse birleştirme yok.

Gövde kalitesi arşivdeki PR #97 ile aynı çizgide tutulur: ne değişti, nasıl
doğrulandı, sır var mı. Üretici gövdeyi gerçek veriden kurar (git diff, test
çıkışı); kapı ise merge'den önce gövdeyi yeniden okuyup doğrular (fail-closed).

Kendi kendini doğrulama:

    python3 -m agents.driver.govde --kontrol pr-govdesi.md   # eksik varsa çıkış 1
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ZORUNLU = ("Ne", "Doğrulama", "Sır")

# Doğrulama bölümünde aranan makine kanıtı: "<komut> → çıkış 0".
KANIT = re.compile(r"çıkış\s+0\b")
KANIT_YOK = re.compile(r"çıkış\s+[1-9]\d*\b|BAŞARISIZ")


def bolumler(govde: str) -> dict[str, str]:
    """'## Başlık' bölümlerini {başlık: gövde} olarak döndürür (ilk tekrar kazanır)."""
    sonuc: dict[str, str] = {}
    baslik = None
    tampon: list[str] = []
    for satir in str(govde or "").splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", satir)
        if m:
            if baslik is not None and baslik not in sonuc:
                sonuc[baslik] = "\n".join(tampon).strip()
            baslik = m.group(1).strip()
            tampon = []
        elif baslik is not None:
            tampon.append(satir)
    if baslik is not None and baslik not in sonuc:
        sonuc[baslik] = "\n".join(tampon).strip()
    return sonuc


def eksikler(govde: str) -> list[str]:
    """Birleştirmeyi engelleyen eksikler; boş liste = gövde kapıdan geçti."""
    b = bolumler(govde)
    eksik: list[str] = []
    for ad in ZORUNLU:
        if ad not in b:
            eksik.append(f"bölüm yok: ## {ad}")
        elif not b[ad]:
            eksik.append(f"bölüm boş: ## {ad}")
    dogrulama = b.get("Doğrulama", "")
    if dogrulama and not KANIT.search(dogrulama):
        eksik.append("Doğrulama'da 'çıkış 0' kanıtı yok")
    if dogrulama and KANIT_YOK.search(dogrulama):
        eksik.append("Doğrulama başarısız çıkış içeriyor")
    return eksik


def _dosya_listesi(dosyalar: list[str]) -> list[str]:
    if not dosyalar:
        return ["- Değişen dosya yok (yalnız gövde/sır kontrolü)."]
    return [f"- `{d}`" for d in dosyalar]


def olustur(gorev: str, dosyalar: list[str], dogrulama: list[str], *,
            sir: str = "Yok.", neden: str | None = None,
            baslik_ozet: str | None = None) -> str:
    """Gövdeyi kur. `dogrulama` satırları gerçek test çıktısından gelmeli."""
    satirlar = ["## Ne", ""]
    if baslik_ozet:
        satirlar += [baslik_ozet.strip(), ""]
    satirlar += _dosya_listesi(dosyalar)
    if neden:
        satirlar += ["", "## Neden", "", neden.strip()]
    satirlar += ["", "## Görev", "", gorev.strip()[:2000]]
    satirlar += ["", "## Doğrulama", ""]
    satirlar += [s.rstrip() for s in (dogrulama or ["- Doğrulama çalıştırılmadı (test_command boş)."])]
    satirlar += ["", "## Sır", "", sir.strip() if sir.strip() else "Yok."]
    return "\n".join(satirlar).rstrip() + "\n"


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PR gövdesi kapısı")
    ap.add_argument("--kontrol", required=True, help="denetlenecek gövde dosyası")
    ns = ap.parse_args(argv)
    govde = Path(ns.kontrol).read_text(encoding="utf-8")
    eksik = eksikler(govde)
    if eksik:
        print("✗ gövde kapıdan geçmedi:")
        for e in eksik:
            print("  - " + e)
        return 1
    print("✓ gövde kapıdan geçti (" + ", ".join("## " + z for z in ZORUNLU) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(_main())


def gerekli(pr: dict, gorev_etiketi: str = "agents/gorev") -> bool:
    """Gövde kapısı yalnız sürücünün açtığı PR'lar için.

    İnsan PR'ları (elle açılmış dallar) bu kapıya takılmaz; onlar için tek
    koşul i5 incelemesidir. Aksi hâlde insan PR'ı hiçbir zaman birleşemezdi.
    """
    dal = str(((pr.get("head") or {}).get("ref")) or "")
    if dal.startswith("agents/"):
        return True
    etiketler = {str(e.get("name")) for e in (pr.get("labels") or []) if isinstance(e, dict)}
    return gorev_etiketi in etiketler
