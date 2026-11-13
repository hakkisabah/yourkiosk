"""agents CLI — doctor, status, install, run."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import config, roles, systemd, worker
from .github import Github, GithubHatasi
from .roles import KARAR_BEKLE, beklenen_rol
from .state import Durum


def _ajan(cfg: dict, rol: str) -> dict:
    for a in cfg["agents"]:
        if a["role"] == rol:
            return a
    raise SystemExit(f"rol yok: {rol}")


def doctor(cfg_yolu: str | None) -> int:
    sorun = 0
    try:
        cfg = config.yukle(Path(cfg_yolu) if cfg_yolu else None)
    except config.ConfigHatasi as h:
        print(f"✗ config: {h}")
        return 2
    print(f"✓ config: {cfg['instance']} · {cfg['repo']}")
    for arac in ("node", "git"):
        if shutil.which(arac) is None:
            print(f"✗ araç yok: {arac}")
            sorun += 1
    dsh = Path(os.environ.get("DSH_CHECKOUT", str(Path.home() / "deepseek-harness")))
    if not (dsh / "apps" / "cli" / "lib" / "bin.js").is_file():
        print(f"✗ DSH checkout yok: {dsh}")
        sorun += 1
    for a in cfg["agents"]:
        t = Path(a["token_file"])
        if not t.is_file():
            print(f"✗ token yok: {t}")
            sorun += 1
        else:
            mod = t.stat().st_mode & 0o777
            if mod != 0o600:
                print(f"✗ token izni {mod:o} (0600 olmalı): {t}")
                sorun += 1
    Path(cfg["state_dir"]).mkdir(parents=True, exist_ok=True)
    print(f"✓ durum: {cfg['state_dir']}")
    return 1 if sorun else 0


def status(cfg_yolu: str | None) -> int:
    cfg = config.yukle(Path(cfg_yolu) if cfg_yolu else None)
    for a in cfg["agents"]:
        with Durum(Path(cfg["state_dir"]), a["name"]) as d:
            print(f"{a['name']:15s} {a['role']:10s} {json.dumps(d.oku(), ensure_ascii=False)}")
    return 0


def install(cfg_yolu: str | None, kuru: bool) -> int:
    cfg = config.yukle(Path(cfg_yolu) if cfg_yolu else None)
    sysd = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "systemd" / "user"
    for a in cfg["agents"]:
        ad = systemd.birim_adi(cfg["instance"], a["role"])
        kok = Path(__file__).resolve().parents[2]
        metin = systemd.servis_metni(
            cfg["instance"], a["role"],
            f"{sys.executable} -m agents.driver.cli run --role {a['role']}",
            Path(cfg["state_dir"]),
            {"AGENTS_CONFIG": str(Path(cfg_yolu).resolve()) if cfg_yolu else str(config.yapilandirma_yolu()),
             "PYTHONPATH": str(kok)},
        )
        if kuru:
            print(f"--- {ad} ---")
            print(metin)
        else:
            sysd.mkdir(parents=True, exist_ok=True)
            (sysd / ad).write_text(metin, encoding="utf-8")
            (sysd / ad).chmod(0o644)
            print(f"yazıldı: {sysd / ad}")
    return 0


def run(cfg_yolu: str | None, rol: str, kuru: bool, gorev: str | None = None) -> int:
    cfg = config.yukle(Path(cfg_yolu) if cfg_yolu else None)
    a = _ajan(cfg, rol)
    with Durum(Path(cfg["state_dir"]), a["name"]) as d:
        veri = d.oku()
        durum = veri.get("durum") or beklenen_rol(rol)
        if kuru:
            print(json.dumps({"ajan": a["name"], "rol": rol, "durum": durum,
                              "gorev": gorev}, ensure_ascii=False))
            return 0
        if rol == "developer" and gorev:
            sonuc = worker.gorev_baslat(cfg, a, gorev)
            d.yaz({"durum": KARAR_BEKLE, "rol": rol, "pr": sonuc["pr"],
                   "sha": sonuc["sha"], "dal": sonuc["dal"]})
            print(f"{a['name']}: PR #{sonuc['pr']} açıldı ({sonuc['sha'][:10]})")
            return 0
        if rol in {"reviewer", "decision"}:
            g = Github(cfg["repo"], a["token_file"])
            prlar = g.acik_prlar()
            durumlar = {int(p["number"]): g.durumlar(str(p["head"]["sha"])) for p in prlar}
            hedef = (roles.inceleme_plani(prlar, durumlar) if rol == "reviewer"
                     else roles.karar_plani(prlar, durumlar))
            if not hedef:
                print(f"{a['name']}: iş yok")
                return 0
            pr = hedef[0]
            sonuc = (worker.incele(cfg, a, pr) if rol == "reviewer"
                     else worker.karar_ver(cfg, a, pr))
            d.yaz({"durum": durum, "rol": rol, "sonuc": sonuc})
            print(f"{a['name']}: #{pr['number']} {sonuc}")
            return 0
        d.yaz({"durum": durum, "rol": rol})
        print(f"{a['name']}: {durum}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agents")
    p.add_argument("--config")
    alt = p.add_subparsers(dest="komut", required=True)
    for ad in ("doctor", "status", "install", "uninstall"):
        sp = alt.add_parser(ad)
        sp.add_argument("--kuru", action="store_true")
    r = alt.add_parser("run")
    r.add_argument("--role", required=True)
    r.add_argument("--gorev")
    r.add_argument("--kuru", action="store_true")
    s = p.parse_args(argv)
    if s.komut == "doctor":
        return doctor(s.config)
    if s.komut == "status":
        return status(s.config)
    if s.komut == "install":
        return install(s.config, s.kuru)
    if s.komut == "uninstall":
        print("uninstall: birimleri silmek için install --kuru çıktısındaki adları kullanın")
        return 0
    if s.komut == "run":
        return run(s.config, s.role, s.kuru, getattr(s, "gorev", None))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
