"""bwrap argümanları — sabit yol yok, fail-closed."""

from __future__ import annotations

from pathlib import Path


def bwrap_argumanlari(repo: Path, mod: str, shadow_home: Path,
                      dsh_checkout: Path | None = None) -> list[str]:
    if mod not in {"read-only", "workspace-write"}:
        raise ValueError(f"geçersiz mod: {mod}")
    a = [
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--tmpfs", "/run",
        "--unshare-net",
        "--unshare-pid",
        "--die-with-parent",
        "--bind", str(shadow_home), str(Path.home()),
    ]
    if mod == "workspace-write":
        a += ["--bind", str(repo), str(repo)]
    else:
        a += ["--ro-bind", str(repo), str(repo)]
    if dsh_checkout is not None:
        a += ["--ro-bind", str(dsh_checkout), str(dsh_checkout)]
    a += ["--"]
    return a
