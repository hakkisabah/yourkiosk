"""Etkileşimli kurulum sihirbazı — instance/repo/N ajan ve makine betikleri."""

from __future__ import annotations

import argparse
import socket
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
INSTALL = Path(__file__).resolve().parent
H = chr(36) + "{HOME}"
KAPI_ROLLERI = ("developer", "reviewer", "decision")


def sor(soru: str, varsayilan: str = "") -> str:
    deger = input(f"{soru}" + (f" [{varsayilan}]" if varsayilan else "") + ": ").strip()
    return deger or varsayilan


def roller(n: int) -> list[str]:
    if n < 1:
        raise ValueError("en az 1 ajan")
    if n == 1:
        return ["developer"]
    return ["developer"] + ["reviewer"] * (n - 2) + ["decision"]


def config_metni(instance: str, repo: str, ajanlar: list[dict]) -> str:
    s = [
        f'instance = "{instance}"',
        f'repo = "{repo}"',
        'base_branch = "main"',
        'gorev_etiketi = "agents/gorev"',
        'dsh_profile = "headless"',
        f'dsh_checkout = "{H}/deepseek-harness"',
        f'dsh_home = "{H}/.dsh"',
        f'dsh_patch = "{H}/.dsh/agents-overlay-lite.yml"',
        f'state_dir = "{H}/.local/state/agents/{instance}"',
        f'workdir = "{H}/.local/state/agents/{instance}/work"',
        f'skills_root = "{H}/.local/share/agents/{instance}/skills"',
        "",
    ]
    for a in ajanlar:
        s += ["[[agents]]", f'name = "{a["ad"]}"', f'role = "{a["rol"]}"',
              f'machine = "{a["makine"]}"',
              f'token_file = "{H}/.config/{instance}/{a["token"]}"', ""]
    return chr(10).join(s)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--instance")
    p.add_argument("--repo")
    p.add_argument("--n", type=int)
    p.add_argument("--ajan", action="append", default=[],
                   help="ad,rol,makine,token (tekrarlanabilir)")
    p.add_argument("--kuru", action="store_true")
    a = p.parse_args(argv)
    instance = a.instance or sor("Instance adı", "proje")
    repo = a.repo or sor("GitHub repo (sahip/ad)", "")
    n = a.n or int(sor("Ajan sayısı", "3"))
    makine_varsayilan = socket.gethostname()
    ajanlar = []
    if a.ajan:
        for tanim in a.ajan:
            parca = [x.strip() for x in tanim.split(",")]
            if len(parca) != 4 or parca[1] not in {"developer", "reviewer", "decision"}:
                raise SystemExit("--ajan formatı: ad,developer|reviewer|decision,makine,token")
            ajanlar.append({"ad": parca[0], "rol": parca[1], "makine": parca[2], "token": parca[3]})
        n = len(ajanlar)
    if not a.ajan:
        for i, rol in enumerate(roller(n), 1):
            varsayilan_ad = {"developer": "gelistirici", "decision": "karar"}.get(rol, f"inceleme{i}")
            ad = sor(f"{i}. ajan adı", varsayilan_ad)
            makine = sor(f"{i}. makine", makine_varsayilan)
            token = sor(f"{i}. token dosyası", f"{ad}.token")
            ajanlar.append({"ad": ad, "rol": rol, "makine": makine, "token": token})
    metin = config_metni(instance, repo, ajanlar)
    eksik = [r for r in KAPI_ROLLERI if r not in {aj["rol"] for aj in ajanlar}]
    if eksik:
        print(f"⚠ kapı rolleri eksik: {', '.join(eksik)} — bu ajanlar PR açar ama "
              "birleştirme olmaz; tam kapı için developer+reviewer+decision gerekir")
    cfg_yolu = KOK / "agents" / "config" / f"{instance}.toml"
    if a.kuru:
        print(metin)
        return 0
    cfg_yolu.parent.mkdir(parents=True, exist_ok=True)
    cfg_yolu.write_text(metin, encoding="utf-8")
    betikler = []
    for aj in ajanlar:
        cikti = INSTALL / f"agents-kur-{aj['makine']}.sh"
        subprocess.run([str(INSTALL / "uret.sh"), instance, aj["makine"], aj["rol"],
                        repo, str(cikti), aj["token"]], check=True)
        betikler.append(cikti)
    print(chr(10) + "Config: " + str(cfg_yolu))
    print("Makine betikleri:")
    for b in betikler:
        print("  " + str(b))
    print(chr(10) + "Her makinede: repo kopyala → betiği çalıştır → token 0600.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
