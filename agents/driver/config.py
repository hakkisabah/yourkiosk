"""Instance yapılandırması — sabit yol yok, env/XDG tabanlı."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DEGISKEN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigHatasi(Exception):
    pass


def _genislet(deger: str, instance: str) -> str:
    def yer(m):
        ad = m.group(1)
        if ad == "instance":
            return instance
        return os.environ.get(ad, "")
    return DEGISKEN.sub(yer, deger)


def yapilandirma_yolu(arg: str | None = None) -> Path:
    if arg:
        return Path(arg).expanduser()
    if os.environ.get("AGENTS_CONFIG"):
        return Path(os.environ["AGENTS_CONFIG"]).expanduser()
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return xdg / "agents" / "instance.toml"


def yukle(yol: Path | None = None) -> dict:
    p = yol or yapilandirma_yolu()
    if not p.is_file():
        raise ConfigHatasi(f"config yok: {p}")
    ham = p.read_text(encoding="utf-8")
    if p.suffix == ".toml":
        veri = tomllib.loads(ham)
    elif yaml is not None:
        veri = yaml.safe_load(ham) or {}
    else:
        raise ConfigHatasi(f"{p.suffix} için PyYAML gerekli; .toml kullanın")
    if not isinstance(veri, dict):
        raise ConfigHatasi("config kökü eşleme olmalı")
    instance = str(veri.get("instance") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", instance):
        raise ConfigHatasi("instance adı 1-64 karakter [A-Za-z0-9._-] olmalı")
    veri["instance"] = instance
    for anahtar in ("repo", "base_branch"):
        if not str(veri.get(anahtar) or "").strip():
            raise ConfigHatasi(f"{anahtar} zorunlu")
    ajanlar = veri.get("agents")
    if not isinstance(ajanlar, list) or not ajanlar:
        raise ConfigHatasi("en az bir ajan gerekli")
    for a in ajanlar:
        for alan in ("name", "role", "machine", "token_file"):
            if not str(a.get(alan) or "").strip():
                raise ConfigHatasi(f"ajan alanı eksik: {alan}")
        a["token_file"] = _genislet(str(a["token_file"]), instance)
    xdg_state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    veri["state_dir"] = _genislet(str(veri.get("state_dir") or xdg_state / "agents" / instance), instance)
    veri["workdir"] = _genislet(str(veri.get("workdir") or Path(veri["state_dir"]) / "work"), instance)
    veri["skills_root"] = _genislet(str(veri.get("skills_root") or xdg_data / "agents" / instance / "skills"), instance)
    return veri


def sabit_yol_denetle(kok: Path) -> list[str]:
    """Kod/docs içinde sabit ev/proje adı arayan test için."""
    yasak = ("/" + "home/", "your" + "kiosk", "otonom" + "-tik", "otonom" + "_bekci")
    bulgular = []
    for p in kok.rglob("*"):
        if not p.is_file() or p.suffix not in {".py", ".sh", ".md", ".yml"}:
            continue
        for i, satir in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for y in yasak:
                if y in satir:
                    bulgular.append(f"{p}:{i}:{y}")
    return bulgular
