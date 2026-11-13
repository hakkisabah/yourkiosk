"""Geliştirici işçisi — klon, DSH, commit, push, PR."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import dsh, github, roles


class IsciHatasi(Exception):
    pass


def slug(metin: str, uzunluk: int = 40) -> str:
    s = metin.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:uzunluk].strip("-") or "gorev")


def dal_adi(instance: str, gorev: str) -> str:
    return f"agents/{slug(instance)}-{slug(gorev)}"


def _token(ajan: dict) -> str:
    try:
        t = Path(ajan["token_file"]).read_text(encoding="utf-8").strip()
    except OSError as h:
        raise IsciHatasi(f"token okunamadı: {ajan['token_file']}") from h
    if not t:
        raise IsciHatasi("token boş")
    return t


def _git_env(token: str) -> dict:
    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {token}",
        "GIT_TERMINAL_PROMPT": "0",
    })
    return env


def _git(workdir: Path, *arg: str, token: str) -> str:
    s = subprocess.run(["git", "-C", str(workdir), *arg], capture_output=True,
                       text=True, env=_git_env(token), timeout=120)
    if s.returncode != 0:
        raise IsciHatasi(f"git {arg[0]}: {s.stderr.strip()[:400]}")
    return s.stdout


def klon_hazirla(cfg: dict, ajan: dict) -> Path:
    wd = Path(cfg["workdir"])
    token = _token(ajan)
    if (wd / ".git").is_dir():
        _git(wd, "fetch", "origin", "--prune", token=token)
        return wd
    wd.parent.mkdir(parents=True, exist_ok=True)
    s = subprocess.run(
        ["git", "clone", f"https://github.com/{cfg['repo']}.git", str(wd)],
        capture_output=True, text=True, env=_git_env(token), timeout=300)
    if s.returncode != 0:
        raise IsciHatasi(f"klon: {s.stderr.strip()[:300]}")
    return wd


def _rol_metni(rol: str) -> str:
    return (Path(__file__).resolve().parents[1] / "roles" / f"{rol}.md").read_text(encoding="utf-8")


def gorev_baslat(cfg: dict, ajan: dict, gorev: str) -> dict:
    wd = klon_hazirla(cfg, ajan)
    token = _token(ajan)
    dal = dal_adi(cfg["instance"], gorev)
    _git(wd, "checkout", "-B", dal, token=token)
    once = _git(wd, "rev-parse", "HEAD", token=token).strip()
    prompt = chr(10).join([
        _rol_metni(ajan["role"]),
        "",
        "## Görev",
        gorev,
        "",
        "Değişiklikleri commit et. Push/merge YOK; sürücü yapacak.",
    ])
    kod, cikti = dsh.calistir(prompt, cfg.get("dsh_profile", "agents-dev"), wd)
    if kod != 0:
        raise IsciHatasi(f"DSH çıkış {kod}: {cikti[-500:]}")
    if _git(wd, "status", "--porcelain", token=token).strip():
        _git(wd, "add", "-A", token=token)
        _git(wd, "commit", "-m", f"agents: {gorev[:70]}", token=token)
    son = _git(wd, "rev-parse", "HEAD", token=token).strip()
    if son == once:
        raise IsciHatasi("DSH değişiklik üretmedi")
    _git(wd, "push", "-u", "origin", dal, token=token)
    g = github.Github(cfg["repo"], ajan["token_file"])
    pr = g.pr_olustur(f"agents: {gorev[:60]}", gorev, cfg["base_branch"], dal)
    return {"pr": pr.get("number"), "sha": son, "dal": dal, "workdir": str(wd)}
