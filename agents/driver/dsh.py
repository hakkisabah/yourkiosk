"""DSH headless çağrısı — sınırlı çıktı, sabit yol yok."""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

AZAMI_CIKTI = 2 * 1024 * 1024


class DshHatasi(Exception):
    pass


def dsh_checkout() -> Path:
    return Path(os.environ.get("DSH_CHECKOUT", str(Path.home() / "deepseek-harness")))


def komut(profil: str, izin: str | None = None, patch: str | None = None) -> list[str]:
    k = ["node", str(dsh_checkout() / "apps" / "cli" / "lib" / "bin.js"),
         "--profile", profil]
    if patch:
        k += ["--patch", str(Path(patch).resolve())]
    if izin:
        k += ["--permission-mode", izin]
    k += ["--approval-policy", "never"]
    return k + ["-"]


def _oku(boru, kutu, ad, pid):
    if boru is None:
        kutu[ad] = ""
        return
    parcalar, toplam = [], 0
    while True:
        try:
            p = boru.read(65536)
        except (OSError, ValueError):
            break
        if not p:
            break
        toplam += len(p)
        if toplam > AZAMI_CIKTI:
            parcalar.append(p[:max(0, AZAMI_CIKTI - (toplam - len(p)))])
            try:
                os.killpg(os.getpgid(pid), 15)
            except OSError:
                pass
            break
        parcalar.append(p)
    kutu[ad] = "".join(parcalar)


def calistir(prompt: str, profil: str, cwd: Path, izin: str | None = None,
             dsh_home: str | None = None, patch: str | None = None,
             repo: Path | None = None) -> tuple[int, str]:
    if not Path(komut(profil, izin, patch)[1]).is_file():
        raise DshHatasi(f"DSH bulunamadı: {komut(profil, izin, patch)[1]}")
    ortam = dict(os.environ)
    if repo is not None:
        ortam["AGENTS_REPO"] = str(repo)
    if dsh_home:
        ortam["DSH_HOME"] = str(dsh_home)
        env_yolu = Path(dsh_home) / ".env"
        if env_yolu.is_file():
            for satir in env_yolu.read_text(encoding="utf-8").splitlines():
                if "=" in satir and not satir.strip().startswith("#"):
                    k, v = satir.split("=", 1)
                    ortam.setdefault(k.strip(), v.strip())
    s = subprocess.Popen(komut(profil, izin, patch), cwd=str(cwd), env=ortam,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    kutu: dict[str, str] = {}
    t1 = threading.Thread(target=_oku, args=(s.stdout, kutu, "out", s.pid), daemon=True)
    t2 = threading.Thread(target=_oku, args=(s.stderr, kutu, "err", s.pid), daemon=True)
    t1.start(); t2.start()
    try:
        s.stdin.write(prompt)
        s.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    s.wait()
    t1.join(10); t2.join(10)
    return s.returncode, kutu.get("out", "") + kutu.get("err", "")
