"""Dependabot uyarılarının sessizce geri gelmesini engeller.

Neden: panel ve web derleme zinciri (vite, minimatch, glob) devDependencies
üzerinden geliyor. Dependabot bir uyarı açtığında bunu düzelten tek şey
package.json'daki `overrides` + tazelenmiş kilit dosyası; ikisi de gözle
görülmez ve `npm install` sırasında sessizce geri gelebilir. Bu test kilit
dosyalarını okuyup bilinen açık sürüm aralıklarını reddeder ve geçişli
bağımlılıklar için overrides'ın yerinde olduğunu doğrular.

Kapı felsefesi: kilit/package.json yoksa bu test SKIP OLMAZ. Dosyanın
yokluğu "bu ağaçta derleme zinciri kurulu değil" değil, "güvenlik kapısı
ölçüm yapamıyor" demektir; skip, uyarının sessizce geri gelmesine açık
kapı bırakır. Bu yüzden eksik dosya kesin başarısızlıktır.

Kaynak: GitHub Dependabot (security and quality sekmesi) + OSV — GHSA
kimlikleri ve etkilenen aralıklar aşağıdaki tabloda.
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
#  ilk güvenli sürüm, GHSA kimliği)
# Aralıklar OSV kayıtlarıyla birebir: vite GHSA-8g5g-mxqh-grgj ilk etkilenen
# 6.4.4, minimatch GHSA-g3hv-75wg-m249, glob GHSA-3g3m-2fjr-6pw4 (9.0.0–14.0.1).
UYARILAR = [
    ("minimatch", (7, 0, 0), (11, 0, 1), "11.0.1", "GHSA-g3hv-75wg-m249"),
    ("vite", (6, 4, 4), (6, 4, 5), "6.4.5", "GHSA-8g5g-mxqh-grgj"),
    ("glob", (9, 0, 0), (14, 0, 2), "14.0.2", "GHSA-3g3m-2fjr-6pw4"),
]

GHSA_DESENI = re.compile(r"^GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$")

# Geçişli gelenler: doğrudan bağımlılık değil, bu yüzden sürüm ancak
# `overrides` ile sabitlenebilir.
OVERRIDE_BEKLEYEN = ("minimatch", "glob")


def _surum(metin: str) -> tuple[int, ...]:
    """'6.4.5' / '11.0.5' / '5.0.0-beta.1' → karşılaştırılabilir demet."""
    sayilar = re.findall(r"\d+", metin.split("-")[0].split("+")[0])
    return tuple(int(s) for s in sayilar[:3])


def _kilit_verisi(ad: str, kilitler: dict[str, Path] | None = None) -> dict:
    """Kilidi okur; dosya yoksa SKIP değil, kesin başarısızlık."""
    yol = (kilitler or KILITLER)[ad]
    assert yol.exists(), (
        f"{yol} yok — güvenlik kapısı ölçüm yapamıyor. Kilit dosyası "
        "kurulmadan bu denetim atlanamaz: `npm install --include=dev` ile "
        "kilidi üret, dosyayı silme."
    )
    return json.loads(yol.read_text())


def _paket_json(ad: str, kilitler: dict[str, Path] | None = None) -> dict:
    """package.json'ı okur; dosya yoksa SKIP değil, kesin başarısızlık."""
    yol = ((kilitler or KILITLER)[ad]).parent / "package.json"
    assert yol.exists(), (
        f"{yol} yok — overrides denetimi ölçüm yapamıyor; skip bu kapıyı "
        "sessizce kapatır."
    )
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


def _ihlaller(kilit: dict, agac: str) -> list[str]:
    """Kilitteki açık sürümleri insan-okunur satırlar olarak döndürür."""
    ihlaller = []
    for paket, alt, ust, guvenli, ghsa in UYARILAR:
        for yol, surum in _kurulu_surumler(kilit, paket):
            v = _surum(surum)
            if alt <= v < ust:
                ihlaller.append(
                    f"{agac}: {yol} = {surum} — açık aralıkta "
                    f"(ilk güvenli {guvenli}, {ghsa})"
                )
    return ihlaller


@pytest.mark.parametrize("agac", sorted(KILITLER))
def test_kilit_dosyasinda_bilinen_acik_surum_yok(agac: str):
    kilit = _kilit_verisi(agac)
    ihlaller = _ihlaller(kilit, agac)
    assert not ihlaller, (
        "Bilinen açık sürüm kilitli:\n  "
        + "\n  ".join(ihlaller)
        + "\nÇözüm: package.json `overrides` güncelle + `npm install --include=dev`."
    )


@pytest.mark.parametrize("agac", sorted(KILITLER))
def test_gecisli_bagimlilik_overrides_ile_sabitlenmis(agac: str):
    veri = _paket_json(agac)
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
    veri = _paket_json("panel")
    istenen = veri.get("devDependencies", {}).get("vite", "")
    assert istenen, "panel/package.json içinde vite devDependency yok"
    assert _surum(istenen) >= (6, 4, 5), (
        f"panel vite isteği {istenen} — en az ^6.4.5 olmalı (GHSA-8g5g-mxqh-grgj)"
    )


def test_uyari_tablosu_kimlik_ve_aralik_tutarli():
    """Tablo satırları izlenebilir olmalı: GHSA kimliği + tutarlı aralık."""
    for paket, alt, ust, guvenli, ghsa in UYARILAR:
        assert GHSA_DESENI.match(ghsa), (
            f"{paket} satırında GHSA kimliği değil serbest metin var: {ghsa!r} "
            "— izlenebilirlik için OSV kimliği yazılmalı (ör. GHSA-3g3m-2fjr-6pw4)."
        )
        assert _surum(guvenli) == ust, (
            f"{paket}: ilk güvenli sürüm {guvenli} ile etkilenen üst sınır {ust} "
            "aynı olmalı (aralık [alt, üst) ve düzeltme üst sınırda)."
        )
        assert _surum(guvenli) >= alt, (
            f"{paket}: ilk güvenli sürüm {guvenli} etkilenen alt sınırın altında."
        )


def test_kilit_dosyasi_yoksa_kapi_kirmizi(tmp_path: Path):
    """Kilit dosyası yoksa test SKIP değil FAIL etmeli.

    Regresyon: `_kilit_verisi` eskiden atlama çağrısı yapıyordu; kilit
    dosyası silinen bir ağaçta güvenlik kapısı sessizce kapanıyordu.
    """
    sahte = {"panel": tmp_path / "panel" / "package-lock.json"}

    def _beklenen_hata(cagri, desen: str) -> None:
        try:
            cagri()
        except AssertionError as hata:
            assert re.search(desen, str(hata)), hata
        except BaseException as hata:  # atlama çağrısı dahil: kapı kapanamaz
            pytest.fail(
                f"eksik dosyada beklenen AssertionError değil {type(hata).__name__} "
                f"geldi: {hata!r}"
            )

    _beklenen_hata(lambda: _kilit_verisi("panel", sahte), "güvenlik kapısı ölçüm yapamıyor")
    _beklenen_hata(lambda: _paket_json("panel", sahte), "overrides denetimi ölçüm yapamıyor")


def test_modul_hic_skip_etmiyor():
    """Bu modülün tek işi kapıyı açık tutmak; atlama çağrısı kapıyı kapatır."""
    yasak = "pytest" + ".skip"
    kaynak = Path(__file__).read_text()
    assert yasak not in kaynak, (
        f"{Path(__file__).name} içinde {yasak} var — eksik dosya/ağaç durumunda "
        "güvenlik kapısı sessizce atlanır, uyarı geri gelse kimse görmez."
    )


def test_sahte_kilitte_acik_surum_yakalaniyor(tmp_path: Path):
    """Denetim mantığı sahte ağaçta da açık sürümü yakalıyor (kapı canlı)."""
    kilit = {
        "packages": {
            "node_modules/vite": {"version": "6.4.4"},
            "node_modules/minimatch": {"version": "11.0.5"},
            "node_modules/glob": {"version": "13.0.6"},
        }
    }
    ihlaller = _ihlaller(kilit, "sahte")
    assert len(ihlaller) == 2, ihlaller
    assert any("vite = 6.4.4" in s for s in ihlaller)
    assert any("glob = 13.0.6" in s for s in ihlaller)
    assert not any("minimatch" in s for s in ihlaller)
