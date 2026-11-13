"""Rol durum makineleri — saf planlayıcılar (ağ yok, test edilebilir)."""

from __future__ import annotations

GELISTIR = "GELISTIR"
KARAR_BEKLE = "KARAR_BEKLE"
INCELEME_BEKLE = "INCELEME_BEKLE"
BIRLESTI = "BIRLESTI"

INCELEME = "guvenlik/inceleme"
KARAR = "guvenlik/karar"


def beklenen_rol(rol: str) -> str:
    return {"developer": GELISTIR, "reviewer": INCELEME_BEKLE,
            "decision": KARAR_BEKLE}.get(rol, GELISTIR)


def gecis(durum: str, olay: str) -> str:
    if durum == GELISTIR and olay in {"push", "ret"}:
        return KARAR_BEKLE
    if durum == KARAR_BEKLE and olay in {"ret"}:
        return GELISTIR
    if durum == KARAR_BEKLE and olay == "merge":
        return GELISTIR
    if durum == BIRLESTI and olay == "is":
        return GELISTIR
    return durum


def gelistirici_plani(durum: str, pr: dict | None, durumlar: dict[str, str],
                      gorev_var: bool) -> tuple[str, dict | None]:
    """(eylem, pr) — eylem: duzelt | basla | bitti | bekle."""
    if durum == GELISTIR:
        if pr is not None and durumlar.get(INCELEME) == "failure":
            return "duzelt", pr
        if pr is None and gorev_var:
            return "basla", None
        return "bekle", pr
    if durum == KARAR_BEKLE:
        if pr is not None and durumlar.get(INCELEME) == "failure":
            return "duzelt", pr
        if pr is not None and pr.get("merged_at"):
            return "bitti", pr
        return "bekle", pr
    return "bekle", pr


def inceleme_plani(acik_prlar: list[dict], durumlar: dict[int, dict[str, str]]) -> list[dict]:
    """Yeni/değişmiş head'i olan ve kararı olmayan PR'lar."""
    hedef = []
    for pr in acik_prlar:
        no = int(pr.get("number") or 0)
        d = durumlar.get(no, {})
        if d.get(INCELEME) not in {"success", "failure"}:
            hedef.append(pr)
    return hedef


def karar_plani(acik_prlar: list[dict], durumlar: dict[int, dict[str, str]]) -> list[dict]:
    """İki onayı tamam ve kararı olmayan PR'lar."""
    hedef = []
    for pr in acik_prlar:
        no = int(pr.get("number") or 0)
        d = durumlar.get(no, {})
        if d.get(INCELEME) == "success" and d.get(KARAR) not in {"success", "failure"}:
            hedef.append(pr)
    return hedef
