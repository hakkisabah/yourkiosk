"""Kuşak (kayan yazı) animasyonunun Qt'siz çekirdeği.

Nöbet listesi geçişiyle aynı his: `InOutCubic` yumuşatma ile sağdan ortaya
gelir, bir süre ortada durur, sonra aynı yumuşatmayla soldan çıkar; sıradaki
kayıt sağdan girer. Döngü böyle sürer.

Oran (0..1) şu anlama gelir:
    0.0 → tamamen sağda (şeridin sağında, görünmez)
    0.5 → yazı şeridin ORTASINDA
    1.0 → tamamen solda (görünmez)

x = şerit_genişliği - oran * (şerit_genişliği + yazı_genişliği)
"""

from __future__ import annotations

from dataclasses import dataclass

VARSAYILAN_GIRIS_MS = 900
VARSAYILAN_DURMA_MS = 3000
VARSAYILAN_CIKIS_MS = 900
VARSAYILAN_ADIM_MS = 30


def in_out_cubic(p: float) -> float:
    """QEasingCurve.Type.InOutCubic eşdeğeri (nöbet geçişiyle aynı yumuşatma)."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    if p < 0.5:
        return 4.0 * p * p * p
    return 1.0 - ((-2.0 * p) + 2.0) ** 3 / 2.0


@dataclass
class KusakAsamasi:
    asama: str  # "giris" | "dur" | "cikis"
    oran: float


class KusakAnimasyonu:
    """Zamanlayıcı adımlarıyla ilerleyen, saf (Qt'siz) animasyon durumu."""

    def __init__(
        self,
        giris_ms: int = VARSAYILAN_GIRIS_MS,
        durma_ms: int = VARSAYILAN_DURMA_MS,
        cikis_ms: int = VARSAYILAN_CIKIS_MS,
        adim_ms: int = VARSAYILAN_ADIM_MS,
    ) -> None:
        self.adim_ms = max(1, int(adim_ms))
        self.giris_adim = max(1, round(int(giris_ms) / self.adim_ms))
        self.durma_adim = max(0, round(int(durma_ms) / self.adim_ms))
        self.cikis_adim = max(1, round(int(cikis_ms) / self.adim_ms))
        self.toplam_adim = self.giris_adim + self.durma_adim + self.cikis_adim
        self.adim = 0

    # ------------------------------------------------------------------ #
    def sifirla(self) -> None:
        self.adim = 0

    @property
    def dongu_tamamlandi(self) -> bool:
        """Son adım atıldı mı (yeni bir kayda geçilmesi gerekiyor mu)?"""
        return self.adim == 0

    def ilerle(self) -> KusakAsamasi:
        """Bir adım ilerletir ve geçerli (aşama, oran) değerini döner."""
        i = self.adim
        if i < self.giris_adim:  # sağdan ortaya
            p = (i + 1) / self.giris_adim
            asama, oran = "giris", 0.5 * in_out_cubic(p)
        elif i < self.giris_adim + self.durma_adim:  # ortada bekle
            asama, oran = "dur", 0.5
        else:  # ortadan sola
            k = i - self.giris_adim - self.durma_adim
            p = (k + 1) / self.cikis_adim
            asama, oran = "cikis", 0.5 + 0.5 * in_out_cubic(p)
        self.adim = (self.adim + 1) % self.toplam_adim
        return KusakAsamasi(asama, min(1.0, max(0.0, oran)))

    # ------------------------------------------------------------------ #
    @staticmethod
    def oran_piksele(oran: float, serit_genislik: int, yazi_genislik: int) -> int:
        """Oranı yazının x konumuna çevirir (0 → sağda, 0.5 → ortada, 1 → solda)."""
        return round(serit_genislik - oran * (serit_genislik + yazi_genislik))

    @staticmethod
    def orta_konum(serit_genislik: int, yazi_genislik: int) -> int:
        """Yazının şeritte ortalandığı x konumu."""
        return max(0, (serit_genislik - yazi_genislik) // 2)
