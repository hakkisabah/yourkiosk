"""Rol durum makineleri — ağ yok; saf geçişler test edilebilir."""

from __future__ import annotations

GELISTIR = "GELISTIR"
KARAR_BEKLE = "KARAR_BEKLE"
INCELEME_BEKLE = "INCELEME_BEKLE"
BIRLESTI = "BIRLESTI"

DURUMLAR = (GELISTIR, KARAR_BEKLE, INCELEME_BEKLE, BIRLESTI)


def gecis(durum: str, olay: str) -> str:
    """Basit kural: GitHub gerçeği -> sonraki durum."""
    if durum == GELISTIR and olay in {"push", "ret"}:
        return KARAR_BEKLE
    if durum == KARAR_BEKLE and olay == "ret":
        return GELISTIR
    if durum == KARAR_BEKLE and olay == "merge":
        return GELISTIR
    if durum == INCELEME_BEKLE and olay == "yeni_head":
        return INCELEME_BEKLE
    if durum == BIRLESTI and olay == "is":
        return GELISTIR
    return durum


def beklenen_rol(rol: str) -> str:
    return {
        "developer": GELISTIR,
        "reviewer": INCELEME_BEKLE,
        "decision": KARAR_BEKLE,
    }.get(rol, GELISTIR)
