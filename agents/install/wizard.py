"""Kurulum sihirbazı — 1..N ajan; sabit yol yok."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def uret(instance: str, repo: str, n: int, makineler: list[str],
         token_dir: Path) -> dict:
    if n < 1:
        raise ValueError("en az 1 ajan")
    roller = ["developer"] if n == 1 else ["developer"] + ["reviewer"] * (n - 2) + ["decision"]
    ajanlar = []
    for i, rol in enumerate(roller, 1):
        ad = "gelistirici" if rol == "developer" else ("karar" if rol == "decision" else f"inceleme{i}")
        ajanlar.append({
            "name": ad, "role": rol,
            "machine": makineler[i - 1] if i - 1 < len(makineler) else "yerel",
            "token_file": str(token_dir / f"{ad}.token"),
        })
    return {"instance": instance, "repo": repo, "base_branch": "main",
            "agents": ajanlar}


def toml(veri: dict) -> str:
    s = [f'instance = "{veri["instance"]}"', f'repo = "{veri["repo"]}"',
         'base_branch = "main"', "",
         'state_dir = "${XDG_STATE_HOME}/agents/${instance}"',
         'workdir = "${XDG_STATE_HOME}/agents/${instance}/work"',
         'skills_root = "${XDG_DATA_HOME}/agents/${instance}/skills"', ""]
    for a in veri["agents"]:
        s += ["[[agents]]", f'name = "{a["name"]}"', f'role = "{a["role"]}"',
              f'machine = "{a["machine"]}"',
              f'token_file = "${{XDG_CONFIG_HOME}}/agents/${{instance}}/{a["name"]}.token"', ""]
    return chr(10).join(s)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--instance", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--makine", action="append", default=[])
    p.add_argument("--kuru", action="store_true")
    a = p.parse_args(argv)
    token_dir = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "agents" / a.instance
    metin = toml(uret(a.instance, a.repo, a.n, a.makine, token_dir))
    if a.kuru:
        print(metin)
        return 0
    hedef = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "agents" / f"{a.instance}.toml"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(metin, encoding="utf-8")
    print(f"yazıldı: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
