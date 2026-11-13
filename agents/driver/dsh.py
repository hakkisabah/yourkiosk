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


def komut(profil: str) -> list[str]:
    return ["node", str(dsh_checkout() / "apps" / "cli" / "lib" / "bin.js"),
            "--profile", profil, "-"]


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


def calistir(prompt: str, profil: str, cwd: Path) -> tuple[int, str]:
    if not Path(komut(profil)[1]).is_file():
        raise DshHatasi(f"DSH bulunamadı: {komut(profil)[1]}")
    s = subprocess.Popen(komut(profil), cwd=str(cwd), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
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
