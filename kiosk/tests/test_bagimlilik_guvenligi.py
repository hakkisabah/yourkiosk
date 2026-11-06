"""Dependabot uyarılarının sessizce geri gelmesini engeller.

Neden: panel ve web derleme zinciri (vite, minimatch, glob) devDependencies
üzerinden geliyor. Dependabot bir uyarı açtığında bunu düzelten tek şey
package.json'daki `overrides` + tazelenmiş kilit dosyası; ikisi de gözle
görülmez ve `npm install` sırasında sessizce geri gelebilir. Bu test kilit
dosyalarını okuyup bilinen açık sürüm aralıklarını reddeder ve geçişli
bağımlılıklar için overrides'ın yerinde olduğunu doğrular.

Kaynak: GitHub Dependabot (security and quality sekmesi) — GHSA kimlikleri
aşağıdaki tabloda.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
KILITLER = {
    "panel": KOK / "panel" / "package-lock.json",
    "web": KOK / "web" / "package-lock.json",
}

# (paket, etkilenen aralık alt sınırı (dahil), etkilenen üst sınır (hariç),
#  ilk güvenli sürüm, GHSA)
UYARILAR = [
    ("minimatch", (7, 0, 0), (11, 0, 1), "11.0.1", "GHSA-g3hv-75wg-m249"),
    ("vite", (6, 0, 0), (6, 4, 5), "6.4.5", "GHSA-8g5g-mxqh-grgj"),
    ("glob", (9, 0, 0), (14, 0, 2), "14.0.2", "npm audit: AbortSignal atlama"),
]

# Geçişli gelenler: doğrudan bağımlılık değil, bu yüzden sürüm ancak
# `overrides` ile sabitlenebilir.
OVERRIDE_BEKLEYEN = ("minimatch", "glob")


def _surum(metin: str) -> tuple[int, ...]:
    """'6.4.5' / '11.0.5' / '5.0.0-beta.1' → karşılaştırılabilir demet."""
    sayilar = re.findall(r"\d+", metin.split("-")[0].split("+")[0])
    return tuple(int(s) for s in sayilar[:3])


def _kilit_verisi(ad: str) -> dict:
    yol = KILITLER[ad]
    if not yol.exists():
        pytest.skip(f"{yol} yok (bu ağaçta derleme zinciri kurulu değil)")
    return json.loads(yol.read_text())


def _kurulu_surumler(kilit: dict, paket: str) -> list[tuple[str, str]]:
    """Kilitteki TÜM <paket> kopyaları: (yol, sürüm)."""
    sonuc = []
    for yol, kayit in kilit.get("packages", {}).items():
        if not yol:
            continue
        ad = yol.rsplit("node_modules/", 1)[-1]
        if ad == paket and kayit.get("version"):
            sonuc.append((yol, kayit["version"]))
    return sonuc


@pytest.mark.parametrize("agac", sorted(KILITLER))
def test_kilit_dosyasinda_bilinen_acik_surum_yok(agac: str):
    kilit = _kilit_verisi(agac)
    ihlaller = []
    for paket, alt, ust, guvenli, ghsa in UYARILAR:
        for yol, surum in _kurulu_surumler(kilit, paket):
            v = _surum(surum)
            if alt <= v < ust:
                ihlaller.append(
                    f"{agac}: {yol} = {surum} — açık aralıkta "
                    f"(ilk güvenli {guvenli}, {ghsa})"
                )
    assert not ihlaller, (
        "Bilinen açık sürüm kilitli:\n  "
        + "\n  ".join(ihlaller)
        + "\nÇözüm: package.json `overrides` güncelle + `npm install --include=dev`."
    )


@pytest.mark.parametrize("agac", sorted(KILITLER))
def test_gecisli_bagimlilik_overrides_ile_sabitlenmis(agac: str):
    yol = KILITLER[agac].parent / "package.json"
    if not yol.exists():
        pytest.skip(f"{yol} yok")
    veri = json.loads(yol.read_text())
    overrides = veri.get("overrides") or {}
    eksik = [p for p in OVERRIDE_BEKLEYEN if p not in overrides]
    assert not eksik, (
        f"{agac}/package.json overrides içinde {eksik} yok; bu paketler geçişli "
        "geldiği için sürüm yalnız overrides ile sabitlenebilir."
    )
    for paket in OVERRIDE_BEKLEYEN:
        deger = overrides[paket]
        ilk_guvenli = next(g for p, _a, _u, g, _h in UYARILAR if p == paket)
        assert _surum(deger) >= _surum(ilk_guvenli), (
            f"{agac}: overrides[{paket}] = {deger} < ilk güvenli {ilk_guvenli}"
        )


def test_panel_vite_guvenli_surume_sabitlenmis():
    """Dependabot #9: panel vite 6.4.4 (server.fs.deny atlatma)."""
    yol = KILITLER["panel"].parent / "package.json"
    if not yol.exists():
        pytest.skip("panel ağacı yok")
    veri = json.loads(yol.read_text())
    istenen = veri.get("devDependencies", {}).get("vite", "")
    assert istenen, "panel/package.json içinde vite devDependency yok"
    assert _surum(istenen) >= (6, 4, 5), (
        f"panel vite isteği {istenen} — en az ^6.4.5 olmalı (GHSA-8g5g-mxqh-grgj)"
    )
