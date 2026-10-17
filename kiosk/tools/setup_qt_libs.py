#!/usr/bin/env python3
"""Qt çalışma zamanı bağımlılıklarını proje içine aşamalı indirir (root'suz).

NEDEN: Bu geliştirme makinesinde `libGL.so.1`, `libX11.so.6`, `libxkbcommon.so.0`,
`libfontconfig.so.1` gibi Qt'nin ihtiyaç duyduğu sistem kütüphaneleri kurulu değil ve
root erişimi yok. Betik, gereken Arch paketlerini indirir, `.qt-libs/lib` altına açar ve
`ldd` çıktısındaki "not found" girdileri bitene kadar bunu tekrarlar.

KULLANIM
    python3 scripts/setup_qt_libs.py            # eksikleri tamamla
    LD_LIBRARY_PATH=.qt-libs/lib .venv/bin/python main.py --windowed

Üretim cihazında (pacman ile kurulu Qt) bu betiğe gerek yoktur.

NOT: Yalnızca QtCore/QtGui/QtWidgets ve QPA/görsel eklentileri için gereken kütüphaneler
hedeflenir; QtQml/QtQuick/QtSql/QtTextToSpeech gibi kullanılmayan modüllerin bağımlılıkları
bilerek atlanır (saldırı yüzeyini küçük tutmak için).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
STAGE = PROJECT / ".qt-libs" / "lib"
PKGCACHE = PROJECT / ".cache" / "qtpkgs"
MIRROR = "https://geo.mirror.pkgbuild.com"
REPO_JSON = "https://archlinux.org/packages/{repo}/{arch}/{pkg}/json/"

#: lib adı -> Arch paketi
LIB2PKG = {
    "libGL.so.1": "libglvnd", "libEGL.so.1": "libglvnd", "libGLdispatch.so.0": "libglvnd",
    "libGLX.so.0": "libglvnd", "libOpenGL.so.0": "libglvnd", "libGLESv2.so.2": "libglvnd",
    "libX11.so.6": "libx11", "libX11-xcb.so.1": "libx11",
    "libxcb.so.1": "libxcb", "libxcb-render.so.0": "libxcb", "libxcb-shm.so.0": "libxcb",
    "libxcb-randr.so.0": "libxcb", "libxcb-sync.so.1": "libxcb", "libxcb-shape.so.0": "libxcb",
    "libxcb-xfixes.so.0": "libxcb", "libxcb-xkb.so.1": "libxcb", "libxcb-glx.so.0": "libxcb",
    "libxcb-util.so.1": "xcb-util", "libxcb-image.so.0": "xcb-util-image",
    "libxcb-keysyms.so.1": "xcb-util-keysyms", "libxcb-render-util.so.0": "xcb-util-renderutil",
    "libxcb-icccm.so.4": "xcb-util-wm", "libxcb-cursor.so.0": "xcb-util-cursor",
    "libxkbcommon.so.0": "libxkbcommon", "libxkbcommon-x11.so.0": "libxkbcommon-x11",
    "libfontconfig.so.1": "fontconfig", "libfreetype.so.6": "freetype2",
    "libpulse.so.0": "libpulse", "libpcsclite.so.1": "pcsclite",
    "libwayland-client.so.0": "wayland", "libwayland-cursor.so.0": "wayland",
    "libwayland-egl.so.1": "wayland",
    "libXau.so.6": "libxau", "libXdmcp.so.6": "libxdmcp", "libXext.so.6": "libxext",
    "libXrandr.so.2": "libxrandr", "libXrender.so.1": "libxrender",
    "libexpat.so.1": "expat", "libbz2.so.1.0": "bzip2", "libpng16.so.16": "libpng",
    "libz.so.1": "zlib", "libbrotlidec.so.1": "brotli", "libbrotlicommon.so.1": "brotli",
    "libharfbuzz.so.0": "harfbuzz", "libgraphite2.so.3": "graphite",
    "libglib-2.0.so.0": "glib2", "libgobject-2.0.so.0": "glib2", "libgmodule-2.0.so.0": "glib2",
    "libpcre2-8.so.0": "pcre2", "libffi.so.8": "libffi",
}
SKIP_PREFIXES = ("libc.so", "libm.so", "libdl.so", "libpthread.so", "librt.so", "ld-linux",
                 "libgcc_s.so", "libstdc++.so", "libicu", "libatk", "libcairo", "libgtk",
                 "libgdk", "libpango", "libmysqlclient", "libpq", "libodbc", "libclntsh",
                 "libfbclient", "libmimerapi", "libspeechd", "libdrm", "libgbm", "libcups",
                 "libxml2", "libsystemd", "libmount", "libblkid", "libuuid", "libzstd",
                 "libdbus")


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def fetch_pkg(pkg: str) -> bool:
    PKGCACHE.mkdir(parents=True, exist_ok=True)
    filename = None
    repo_used = ""
    for repo in ("extra", "core"):
        try:
            with urllib.request.urlopen(
                REPO_JSON.format(repo=repo, arch="x86_64", pkg=pkg), timeout=30
            ) as response:
                data = json.loads(response.read().decode())
            filename, repo_used = data["filename"], repo
            break
        except Exception:
            continue
    if not filename:
        print(f"  !! {pkg}: paket bilgisi alınamadı")
        return False
    archive = PKGCACHE / filename
    if not archive.exists():
        url = f"{MIRROR}/{repo_used}/os/x86_64/{filename}"
        result = sh(["curl", "-sSL", "-o", str(archive), "-w", "%{http_code}", url])
        if result.stdout.strip() != "200":
            print(f"  !! {pkg}: indirilemedi ({url})")
            return False
    extract = PKGCACHE / f"x_{pkg}"
    shutil.rmtree(extract, ignore_errors=True)
    extract.mkdir(parents=True, exist_ok=True)
    if sh(["bsdtar", "-xf", str(archive), "-C", str(extract)]).returncode != 0:
        print(f"  !! {pkg}: arşiv açılamadı")
        return False
    STAGE.mkdir(parents=True, exist_ok=True)
    source = extract / "usr" / "lib"
    count = 0
    if source.is_dir():
        for entry in source.iterdir():
            target = STAGE / entry.name
            if entry.is_symlink():
                if not target.exists():
                    os.symlink(os.readlink(entry), target)
            elif entry.is_file():
                shutil.copy2(entry, target)
            count += 1
    shutil.rmtree(extract, ignore_errors=True)
    print(f"  ++ {pkg} ({repo_used}, {count} dosya)")
    return True


def targets() -> list[str]:
    files: list[str] = []
    venv = PROJECT / ".venv" / "lib"
    for root, _dirs, names in os.walk(venv):
        if "site-packages/PyQt6" not in root.replace(os.sep, "/"):
            continue
        for name in names:
            if ".so" in name:
                files.append(os.path.join(root, name))
    if STAGE.is_dir():
        files += [str(STAGE / f) for f in os.listdir(STAGE) if ".so" in f]
    return files


def missing_libs() -> set[str]:
    missing: set[str] = set()
    for path in targets():
        for line in sh(["ldd", path]).stdout.splitlines():
            line = line.strip()
            if "=> not found" in line:
                missing.add(line.split("=>")[0].strip())
    return {lib for lib in missing if not lib.startswith(SKIP_PREFIXES)}


def main() -> int:
    if not (PROJECT / ".venv").exists():
        print("önce sanal ortam kurun: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt")
        return 2
    cozulen: set[str] = set()
    for tur in range(1, 12):
        eksik = missing_libs() - cozulen
        print(f"[tur {tur}] eksik kütüphane: {len(eksik)}")
        if not eksik:
            print(f"tamam. Qt bağımlılıkları: {STAGE}")
            print(f"kullanın: LD_LIBRARY_PATH={STAGE} .venv/bin/python main.py --windowed")
            return 0
        ilerleme = False
        for lib in sorted(eksik):
            pkg = LIB2PKG.get(lib) or LIB2PKG.get(lib.split(".so")[0] + ".so")
            if pkg is None:
                print(f"  ?? {lib}: eşleşme yok (kullanılmayan modül bağımlılığı olabilir)")
                cozulen.add(lib)
                continue
            if fetch_pkg(pkg):
                ilerleme = True
            cozulen.add(lib)
        if not ilerleme:
            print("ilerleme yok, duruluyor")
            return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
