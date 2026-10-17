"""Kuşak animasyon çekirdeğinin (core/ticker.py) Qt'siz testleri.

Beklenen: sağdan ortaya InOutCubic ile gelir, ortada durur, aynı yumuşatmayla
soldan çıkar; oran 0.5 her zaman şeridin ortasına denk gelir.
"""

from __future__ import annotations

import pytest

from core.ticker import KusakAnimasyonu, in_out_cubic


# ----------------------------------------------------------------- yumuşatma
@pytest.mark.parametrize("p,beklenen", [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5), (-1.0, 0.0), (2.0, 1.0)])
def test_in_out_cubic_uclar(p: float, beklenen: float) -> None:
    assert in_out_cubic(p) == pytest.approx(beklenen)


def test_in_out_cubic_yavas_baslar_hizli_ortalar() -> None:
    """InOutCubic: başta ve sonda yavaş, ortada hızlı (nöbet geçişiyle aynı his)."""
    assert in_out_cubic(0.1) < 0.1  # yavaş başlangıç
    assert in_out_cubic(0.9) > 0.9  # yavaş bitiş
    adimlar = [in_out_cubic(i / 10) - in_out_cubic((i - 1) / 10) for i in range(1, 11)]
    assert max(adimlar) == pytest.approx(adimlar[4])  # en hızlı adım ortada
    assert adimlar[0] < adimlar[4] and adimlar[-1] < adimlar[4]


# --------------------------------------------------------------- aşama akışı
def test_asamalar_sirayla() -> None:
    anim = KusakAnimasyonu(giris_ms=300, durma_ms=300, cikis_ms=300, adim_ms=30)
    asamalar = [anim.ilerle().asama for _ in range(anim.toplam_adim)]
    assert asamalar == ["giris"] * 10 + ["dur"] * 10 + ["cikis"] * 10
    assert anim.dongu_tamamlandi is True  # bir tur bitti


def test_giris_ortada_biter() -> None:
    anim = KusakAnimasyonu(giris_ms=300, durma_ms=300, cikis_ms=300, adim_ms=30)
    for _ in range(anim.giris_adim):
        durum = anim.ilerle()
    assert durum.asama == "giris"
    assert durum.oran == pytest.approx(0.5, abs=1e-6)  # tam ortada duruyor


def test_durma_asamasinda_konum_degismez() -> None:
    anim = KusakAnimasyonu(giris_ms=300, durma_ms=600, cikis_ms=300, adim_ms=30)
    for _ in range(anim.giris_adim):
        anim.ilerle()
    oranlar = [anim.ilerle().oran for _ in range(anim.durma_adim)]
    assert oranlar == [0.5] * anim.durma_adim


def test_cikis_solda_biter() -> None:
    anim = KusakAnimasyonu(giris_ms=300, durma_ms=0, cikis_ms=300, adim_ms=30)
    for _ in range(anim.giris_adim + anim.cikis_adim):
        durum = anim.ilerle()
    assert durum.asama == "cikis"
    assert durum.oran == pytest.approx(1.0, abs=1e-6)


def test_sifirla_basa_doner() -> None:
    anim = KusakAnimasyonu(giris_ms=300, durma_ms=300, cikis_ms=300, adim_ms=30)
    for _ in range(5):
        anim.ilerle()
    anim.sifirla()
    assert anim.adim == 0
    assert anim.ilerle().asama == "giris"


# ------------------------------------------------------------------- konumlar
def test_oran_konumlari() -> None:
    serit, yazi = 1920, 400
    assert KusakAnimasyonu.oran_piksele(0.0, serit, yazi) == serit            # sağda, görünmez
    assert KusakAnimasyonu.oran_piksele(0.5, serit, yazi) == (serit - yazi) // 2  # ortada
    assert KusakAnimasyonu.oran_piksele(1.0, serit, yazi) == -yazi            # solda, görünmez


def test_orta_konum_seritte_ortalar() -> None:
    assert KusakAnimasyonu.orta_konum(1920, 400) == 760
    assert KusakAnimasyonu.orta_konum(300, 400) == 0  # yazı şeritten genişse 0


def test_hareket_soldan_duraksiyor_sonra_hizlaniyor() -> None:
    """Konum adımları: yavaş → hızlı → yavaş (yumuşatma konuma da yansımalı)."""
    anim = KusakAnimasyonu(giris_ms=600, durma_ms=0, cikis_ms=0, adim_ms=30)
    konumlar = [
        KusakAnimasyonu.oran_piksele(anim.ilerle().oran, 1000, 200)
        for _ in range(anim.giris_adim)
    ]
    farklar = [konumlar[0] - konumlar[1]] if len(konumlar) > 1 else []
    farklar = [abs(konumlar[i] - konumlar[i - 1]) for i in range(1, len(konumlar))]
    assert farklar[0] < farklar[len(farklar) // 2]  # ortada daha hızlı
    assert farklar[-1] < farklar[len(farklar) // 2]  # sonda yavaşlıyor


def test_adim_araligi_ve_sureler_adimlara_cevrilir() -> None:
    anim = KusakAnimasyonu(giris_ms=900, durma_ms=3000, cikis_ms=900, adim_ms=30)
    assert (anim.giris_adim, anim.durma_adim, anim.cikis_adim) == (30, 100, 30)
    assert anim.toplam_adim == 160
    assert isinstance(anim, KusakAnimasyonu)
